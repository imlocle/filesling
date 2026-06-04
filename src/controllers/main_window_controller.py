from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, List, Optional

from paramiko import SFTPClient
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.config.settings import Settings
from src.controllers.transfer_controller import ManualTransferController
from src.models.errors import (
    AuthenticationError,
    ConnectionLostError,
    FileAccessError,
    FileDeletionError,
    SSHConnectionError,
)
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import (
    CONN_TYPE_ADB,
    CONN_TYPE_IOS,
    CONN_TYPE_KEY,
    CONN_TYPE_SSH,
    DEFAULT_ADB_BASE_DIR,
    DIALOG_CONNECTION_ERROR,
    DIALOG_CONNECTION_FAILED,
    DIALOG_CONNECTION_LOST,
    DIALOG_CREATION_FAILED,
    DIALOG_DELETION_FAILED,
    DIALOG_FILE_ALREADY_EXISTS,
    DIALOG_FOLDER_EXISTS,
    DIALOG_MOVE_FAILED,
)
from src.utils.logging_signal import logger
from src.utils.theme import apply_theme
from src.views.settings_window import SettingsWindow

if TYPE_CHECKING:
    from src.views.main_window import MainWindow  # noqa: F401


class MainWindowController:
    """
    Controller for MainWindow.

    Handles:
    - Connection management
    - Manual transfers (via ManualTransferController)
    - UI coordination
    - Settings management
    - File operations (delete, rename, move, create folder)
    """

    def __init__(
        self,
        view: "MainWindow",
        connection_manager: ConnectionManagerService,
    ) -> None:
        self.view = view
        self.settings: Settings = view.settings
        self.connection_manager = connection_manager

        # Create specialized controllers
        self.manual_transfer = ManualTransferController(
            self.settings, self.connection_manager, parent=view
        )
        self._queue_signals_connected = False

        # Connect controller signals to UI updates
        self._connect_controller_signals()

        self.selected_item: Optional[str] = None
        self._current_queue_index: int = -1

        # Connection health monitoring
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._check_connection_health)
        self._health_timer.start(15000)  # Check every 15 seconds
        self._last_latency: float = -1.0

    def _connect_controller_signals(self) -> None:
        """Connect controller signals to UI updates."""
        # Manual transfer signals
        self.manual_transfer.transfer_started.connect(self._on_manual_transfer_started)
        self.manual_transfer.transfer_completed.connect(
            self._on_manual_transfer_completed
        )
        self.manual_transfer.transfer_failed.connect(self._on_manual_transfer_failed)
        self.manual_transfer.transfer_progress.connect(self._on_transfer_progress)
        self.manual_transfer.transfer_method_changed.connect(
            self._on_transfer_method_changed
        )
        self.manual_transfer.queue_changed.connect(self._on_queue_changed)

        # Queue widget signals
        self._connect_queue_signals()

    def _connect_queue_signals(self) -> None:
        """Connect transfer queue UI signals once the widget exists."""
        if self._queue_signals_connected or not hasattr(self.view, "transfer_queue"):
            return
        self.view.transfer_queue.cancel_transfer.connect(self._on_cancel_transfer)
        self._queue_signals_connected = True

    def initialize_transfer_queue(self) -> None:
        """Connect queue UI controls and restore persisted uploads."""
        if not hasattr(self.view, "transfer_queue"):
            return

        queue = self.view.transfer_queue
        self._connect_queue_signals()

        restored = self.manual_transfer.restore_persisted_queue()
        for transfer in restored:
            queue.add_transfer(
                transfer.display_name,
                transfer.total_bytes,
                transfer.remote_destination,
            )

        if restored:
            QTimer.singleShot(500, self.manual_transfer.start_processing)

    # --------------------------------------------------------------
    #  SIGNAL HANDLERS
    # --------------------------------------------------------------
    def _on_manual_transfer_started(self, path: str) -> None:
        """Handle manual transfer started — mark current item as in-progress."""
        # Mark the first pending item as in-progress
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            for i, item in enumerate(queue._items):
                if item.status.value == "pending":
                    queue.set_in_progress(i)
                    self._current_queue_index = i
                    break

        # Update dock badge
        self._update_dock_badge()

    def _on_manual_transfer_completed(self, path: str) -> None:
        """Handle manual transfer completed — mark item as done."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            self.view.transfer_queue.set_completed(self._current_queue_index)
            self._current_queue_index = -1
        self.refresh_explorers()

        # Update dock badge
        self._update_dock_badge()

        # Send macOS notification
        if self.settings.config.notify_on_transfer_complete:
            from src.services.notification_service import notify_transfer_complete

            filename = os.path.basename(path)
            notify_transfer_complete(
                filename,
                action="uploaded",
                sound=self.settings.config.notify_sound,
            )

    def _on_manual_transfer_failed(self, path: str, error: str) -> None:
        """Handle manual transfer failed — mark item as failed."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            short_error = error.split("\n")[0][:80]
            self.view.transfer_queue.set_failed(self._current_queue_index, short_error)
            self._current_queue_index = -1

        # Update dock badge
        self._update_dock_badge()

        # Send macOS notification
        if self.settings.config.notify_on_transfer_complete:
            from src.services.notification_service import notify_transfer_failed

            filename = os.path.basename(path)
            notify_transfer_failed(filename, error.split("\n")[0][:60])

    def _on_transfer_progress(self, percentage: int) -> None:
        """Handle transfer progress update."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            # Convert percentage back to bytes for the queue widget
            queue = self.view.transfer_queue
            if self._current_queue_index < len(queue._items):
                item = queue._items[self._current_queue_index]
                transferred = int(item.total_bytes * percentage / 100)
                queue.update_progress(self._current_queue_index, transferred, 0)

    def _on_transfer_method_changed(self, method: str) -> None:
        """Handle transfer method change (e.g. rsync fallback to SFTP)."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            queue = self.view.transfer_queue
            if self._current_queue_index < len(queue._items):
                queue._items[self._current_queue_index].transfer_method = method
                queue._item_widgets[self._current_queue_index]._update_method_dot()

    def _on_queue_changed(self, total: int) -> None:
        """Handle transfer queue size change — update dock badge."""
        self._update_dock_badge()

    def _on_cancel_transfer(self, pending_index: int) -> None:
        """Handle cancel request from queue widget."""
        self.manual_transfer.cancel_queued_item(pending_index)

    def _update_dock_badge(self) -> None:
        """Update the Dock icon badge with pending transfer count."""
        from src.services.notification_service import set_dock_badge

        pending = self.manual_transfer.queue_size()
        active = 1 if self.manual_transfer.is_busy() else 0
        set_dock_badge(pending + active)

    def _check_connection_health(self) -> None:
        """Periodic connection health check with auto-reconnect."""
        from src.services.adb_client import ADBClient
        from src.services.ios_client import IOSClient

        # Skip health check for ADB/iOS connections (stateless USB)
        if self.view.remote_explorer.sftp and isinstance(
            self.view.remote_explorer.sftp, (ADBClient, IOSClient)
        ):
            return

        # Skip if not connected
        if not self.connection_manager.is_connected():
            return

        # Skip reconnect if a transfer is in progress (avoid disrupting sessions)
        if self.manual_transfer.is_busy():
            return

        # Check if connection is alive
        if self.connection_manager.check_alive():
            # Measure latency
            latency = self.connection_manager.measure_latency()
            self._last_latency = latency
            self._update_connection_status_with_latency(latency)
        else:
            # Connection dropped — attempt auto-reconnect
            logger.warn("Connection: Lost — attempting reconnect...")
            self.view.connection_status_label.setText("● Reconnecting...")
            self.view.connection_status_label.setObjectName("connection_warning")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )

            if self.connection_manager.reconnect():
                # Rebind SFTP to explorer
                if self.connection_manager.sftp_client:
                    self.view.remote_explorer.set_sftp(
                        self.connection_manager.sftp_client
                    )
                    self.view.remote_explorer.refresh()

                server_name = ""
                server_config = self.settings.get_server(
                    self.settings.config.current_server_id
                )
                if server_config:
                    server_name = server_config.get("name", "")

                if server_name:
                    self.view.connection_status_label.setText(
                        f"● Connected: {server_name}"
                    )
                else:
                    self.view.connection_status_label.setText(
                        f"● Connected: {self.settings.host}"
                    )
                self.view.connection_status_label.setObjectName("connection_connected")
                self.view.connection_status_label.style().polish(
                    self.view.connection_status_label
                )
                logger.success("Connection: Reconnected")
            else:
                self.view.connection_status_label.setText("● Disconnected")
                self.view.connection_status_label.setObjectName(
                    "connection_disconnected"
                )
                self.view.connection_status_label.style().polish(
                    self.view.connection_status_label
                )
                logger.error("Connection: Reconnect failed")

    def _update_connection_status_with_latency(self, latency: float) -> None:
        """Update the status bar with latency info and color-coded quality."""
        label = self.view.connection_status_label
        current_text = label.text()

        # Strip any existing latency suffix
        if " (" in current_text:
            base_text = current_text.split(" (")[0]
        else:
            base_text = current_text

        if latency >= 0:
            label.setText(f"{base_text} ({latency:.0f}ms)")
            # Color code: green < 100ms, orange 100-300ms, red > 300ms
            if latency < 100:
                label.setObjectName("connection_connected")
            elif latency < 300:
                label.setObjectName("connection_warning")
            else:
                label.setObjectName("connection_slow")
            label.style().polish(label)

    # --------------------------------------------------------------
    #  CONNECTION MANAGEMENT
    # --------------------------------------------------------------
    def _get_initial_explorer_path(self, root_path: str) -> str:
        """Choose the first path shown after connecting to the current server."""
        return self.settings.get_default_bookmark() or root_path

    def connect(self) -> None:
        """Establish connection to remote server with error handling."""
        # Check if this is an ADB (USB) connection
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH) if server_config else "ssh"
        )

        if connection_type == CONN_TYPE_ADB:
            self._connect_adb(server_config)  # type: ignore
            return

        if connection_type == CONN_TYPE_IOS:
            self._connect_ios(server_config)  # type: ignore
            return

        self._connect_ssh()

    def _connect_adb(self, server_config: dict) -> None:
        """Connect to an Android device via ADB (USB or WiFi)."""
        from src.services.adb_client import (
            ADBClient,
            connect_wifi,
            get_adb_path,
            get_connected_devices,
        )

        # Check if ADB is installed
        try:
            get_adb_path()
        except IOError:
            self._prompt_install_adb()
            return

        device_id = server_config.get("device_id")
        device_name = server_config.get("name", "Android Device")
        root_path = server_config.get("remote_base_dir", DEFAULT_ADB_BASE_DIR)
        wifi_ip = server_config.get("wifi_ip")

        # If WiFi IP is configured, try wireless connect first
        if wifi_ip:
            logger.info(f"ADB: Attempting WiFi connection to {wifi_ip}...")
            connect_wifi(wifi_ip)

        # Check for connected devices
        devices = get_connected_devices()
        if not devices:
            self.view.connection_status_label.setText("● No device found")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            logger.error("ADB: No Android device connected")
            return

        # Use specified device or first available
        if device_id:
            matching = [d for d in devices if d["id"] == device_id]
            if not matching:
                logger.warn(f"ADB: Device {device_id} not found, using first available")
                device_id = devices[0]["id"]
        else:
            device_id = devices[0]["id"]

        try:
            client = ADBClient(device_id)
            # Test connection by listing root
            client.listdir(root_path)

            # Success — bind to explorer
            conn_label = "WiFi" if wifi_ip and ":" in (device_id or "") else "USB"
            self.view.connection_status_label.setText(
                f"● Connected: {device_name} ({conn_label})"
            )
            self.view.connection_status_label.setObjectName("connection_connected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )

            start_path = self._get_initial_explorer_path(root_path)
            self.view.remote_explorer.root_path = root_path
            self.view.remote_explorer.set_sftp(client)
            self.view.remote_explorer.refresh(start_path)

            logger.success(f"Connected: {device_name} (USB)")

        except Exception as e:
            self.view.connection_status_label.setText("● ADB Error")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            logger.error(f"ADB connection failed: {e}")

    def _connect_ios(self, server_config: dict) -> None:
        """Connect to an iPhone/iPad via USB (AFC protocol)."""
        from src.services.ios_client import IOSClient, get_connected_ios_devices

        device_id = server_config.get("device_id")
        device_name = server_config.get("name", "iPhone")
        root_path = server_config.get("remote_base_dir", "/DCIM")

        # Check for connected devices
        devices = get_connected_ios_devices()
        if not devices:
            self.view.connection_status_label.setText("● No iPhone found")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            logger.error("iOS: No device connected via USB")
            QMessageBox.warning(
                self.view,
                "No iPhone Found",
                "No iPhone or iPad detected.\n\n"
                "Make sure the device is:\n"
                "• Plugged in via USB\n"
                "• Unlocked\n"
                "• Trusted (tap 'Trust This Computer' on the device)\n\n"
                "If pymobiledevice3 is not installed, run:\n"
                "pip install pymobiledevice3",
            )
            return

        # Use specified device or first available
        if device_id:
            matching = [d for d in devices if d["id"] == device_id]
            if not matching:
                logger.warn(f"iOS: Device {device_id} not found, using first available")
                device_id = devices[0]["id"]
        else:
            device_id = devices[0]["id"]

        try:
            client = IOSClient(device_id)
            # Test connection by listing root
            client.listdir(root_path)

            # Success — bind to explorer
            self.view.connection_status_label.setText(
                f"● Connected: {device_name} (iPhone)"
            )
            self.view.connection_status_label.setObjectName("connection_connected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )

            start_path = self._get_initial_explorer_path(root_path)
            self.view.remote_explorer.root_path = root_path
            self.view.remote_explorer.set_sftp(client)
            self.view.remote_explorer.refresh(start_path)

            logger.success(f"Connected: {device_name} (iPhone)")

        except Exception as e:
            self.view.connection_status_label.setText("● iOS Error")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            logger.error(f"iOS connection failed: {e}")
            QMessageBox.critical(
                self.view,
                "iOS Connection Error",
                f"Failed to connect to iPhone:\n\n{e}\n\n"
                "Make sure pymobiledevice3 is installed:\n"
                "pip install pymobiledevice3",
            )

    def _prompt_install_adb(self) -> None:
        """Show dialog to help user install ADB."""
        import shutil
        import webbrowser

        has_brew = shutil.which("brew") is not None

        msg = QMessageBox(self.view)
        msg.setWindowTitle("ADB Not Found")
        msg.setText(
            "ADB (Android Debug Bridge) is required to connect to Android devices.\n\n"
            "It is not currently installed on this Mac."
        )

        if has_brew:
            msg.setInformativeText("Install it via Homebrew?")
            install_btn = msg.addButton(
                "Install via Homebrew", QMessageBox.ButtonRole.AcceptRole
            )
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()

            if msg.clickedButton() == install_btn:
                self._install_adb_via_brew()
        else:
            msg.setInformativeText(
                "You can download it from Google's Android Platform Tools page."
            )
            download_btn = msg.addButton(
                "Open Download Page", QMessageBox.ButtonRole.AcceptRole
            )
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()

            if msg.clickedButton() == download_btn:
                webbrowser.open(
                    "https://developer.android.com/tools/releases/platform-tools"
                )

    def _install_adb_via_brew(self) -> None:
        """Run brew install android-platform-tools with progress feedback."""
        import subprocess

        logger.info("Installing ADB via Homebrew...")
        self.view.connection_status_label.setText("● Installing ADB...")

        try:
            result = subprocess.run(
                ["brew", "install", "android-platform-tools"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.success(
                    "ADB installed successfully. Connect your device and try again."
                )
                QMessageBox.information(
                    self.view,
                    "ADB Installed",
                    "ADB was installed successfully.\n\n"
                    "Connect your Android device via USB and try connecting again.",
                )
            else:
                logger.error(f"Homebrew install failed: {result.stderr}")
                QMessageBox.critical(
                    self.view,
                    "Installation Failed",
                    f"Failed to install ADB:\n{result.stderr[:200]}",
                )
        except subprocess.TimeoutExpired:
            logger.error("ADB installation timed out")
            QMessageBox.critical(
                self.view,
                "Installation Timeout",
                "The installation took too long. Try running manually:\n\n"
                "brew install android-platform-tools",
            )
        except Exception as e:
            logger.error(f"ADB installation error: {e}")

        self.view.connection_status_label.setText("● Disconnected")

    def _connect_ssh(self) -> None:
        """Establish SSH/SFTP connection."""
        try:
            if not self.connection_manager.connect():
                self.view.connection_status_label.setText("● Disconnected")
                self.view.connection_status_label.setObjectName(
                    "connection_disconnected"
                )
                self.view.connection_status_label.style().polish(
                    self.view.connection_status_label
                )
                self.view.handle_connection_failure()
                return

            # Connection successful - reset attempt counter
            self.view.connection_attempts = 0

            server_name = ""
            server_config = self.settings.get_server(
                self.settings.config.current_server_id
            )
            if server_config:
                server_name = server_config.get("name", "")

            if server_name:
                self.view.connection_status_label.setText(
                    f"● Connected: {server_name} ({self.settings.host})"
                )
            else:
                self.view.connection_status_label.setText(
                    f"● Connected: {self.settings.host}"
                )
            self.view.connection_status_label.setObjectName("connection_connected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )

            # bind sftp to remote explorer
            if self.connection_manager.sftp_client:
                start_path = self._get_initial_explorer_path(
                    self.settings.remote_base_dir
                )
                self.view.remote_explorer.root_path = self.settings.remote_base_dir
                self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
                self.view.remote_explorer.refresh(start_path)

        except AuthenticationError as e:
            self.view.connection_status_label.setText("● Authentication Failed")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            QMessageBox.critical(
                self.view,
                "Authentication Error",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()
        except FileAccessError as e:
            self.view.connection_status_label.setText("● SSH Key Error")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            QMessageBox.critical(
                self.view,
                "SSH Key Error",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()
        except SSHConnectionError as e:
            self.view.connection_status_label.setText("● Connection Failed")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            QMessageBox.warning(
                self.view,
                DIALOG_CONNECTION_FAILED,
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()
        except Exception as e:
            self.view.connection_status_label.setText("● Error")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            logger.error(f"Unexpected connection error: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_CONNECTION_ERROR,
                f"An unexpected error occurred:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()

    def handle_remote_explorer_failure(self, error_msg: str) -> None:
        """Handle remote explorer errors by attempting to reconnect."""
        logger.error(f"Explorer Error: {error_msg}")
        ok = self.connection_manager.connect()
        if ok and self.connection_manager.sftp_client:
            self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
            self.view.remote_explorer.refresh(self.settings.remote_base_dir)
        else:
            self.view.connection_status_label.setText("● Disconnected")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.setStyle(
                self.view.connection_status_label.style()
            )
            logger.error("Cannot recover connection.")

    # --------------------------------------------------------------
    #  EXPLORER OPS
    # --------------------------------------------------------------
    def refresh_explorers(self) -> None:
        """Refresh the remote file explorer."""
        # If explorer has an active connection (SSH or ADB), just refresh
        if self.view.remote_explorer.sftp:
            self.view.remote_explorer.refresh()
        elif (
            self.connection_manager.is_connected()
            and self.connection_manager.sftp_client
        ):
            self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
            self.view.remote_explorer.refresh()
        else:
            # Don't spam errors; just reflect disconnected state
            self.view.connection_status_label.setText("● Disconnected")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.setStyle(
                self.view.connection_status_label.style()
            )

    def handle_selection_changed(self, path: str) -> None:
        """Handle selection change in explorer."""
        self.selected_item = path or None
        self.view.delete_btn.setEnabled(bool(self.selected_item))

    # --------------------------------------------------------------
    #  DELETE
    # --------------------------------------------------------------
    def delete_selected_item(self) -> None:
        """Delete all selected items in the explorer."""
        items = self.view.remote_explorer.tree_widget.selectedItems()
        if not items:
            return

        paths = [
            os.path.join(self.view.remote_explorer.current_path, item.text(0))
            for item in items
        ]

        if len(paths) == 1:
            self.delete_item(paths[0])
        else:
            self._delete_multiple(paths)

    def delete_items(self, paths: list) -> None:
        """Delete multiple items from a list of paths (triggered by context menu)."""
        if not paths:
            return
        if len(paths) == 1:
            self.delete_item(paths[0])
        else:
            self._delete_multiple(paths)

    def _delete_multiple(self, paths: list) -> None:
        """Delete multiple paths with a single confirmation dialog."""
        reply = QMessageBox.question(
            self.view,
            "Delete",
            f"Are you sure you want to delete {len(paths)} items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for path in paths:
            try:
                is_remote = path.startswith(self.settings.remote_base_dir)
                if is_remote:
                    self._delete_remote(path)
                else:
                    self._delete_local(path)
                logger.trash(f"Deleted: {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"Delete failed: {os.path.basename(path)}: {e}")

        self.view.remote_explorer.refresh()

    def delete_item(self, path: str) -> None:
        """
        Delete a file or folder with proper error handling.

        Args:
            path: Path to file or folder to delete
        """
        basename = os.path.basename(path)
        is_remote = path.startswith(self.settings.remote_base_dir)

        reply = QMessageBox.question(
            self.view,
            "Delete",
            f"Are you sure you want to delete:\n{basename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if is_remote:
                self._delete_remote(path)
                self.view.remote_explorer.refresh()
            else:
                self._delete_local(path)

            logger.trash(f"Deletion: {os.path.basename(path)}: Deleted")

            # Record in history
            self.manual_transfer.history.add(
                filename=os.path.basename(path),
                action="delete",
                source=path,
                server_name=self.settings.config.current_server_id,
            )

        except ConnectionLostError as e:
            logger.error(f"Delete failed: Connection lost: {e}")
            QMessageBox.warning(
                self.view,
                DIALOG_CONNECTION_LOST,
                f"Connection was lost during deletion.\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            # Try to reconnect
            self.connect()
        except FileDeletionError as e:
            logger.error(f"Delete failed: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_DELETION_FAILED,
                f"{e.message}\n\nPath: {e.path}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_DELETION_FAILED,
                f"An unexpected error occurred:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _is_remote_dir(self, path: str) -> bool:
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            return False
        try:
            from stat import S_ISDIR

            return S_ISDIR(sftp.stat(path).st_mode)
        except Exception:
            return False

    def _delete_remote(self, path: str) -> None:
        """
        Delete remote file or directory.

        Args:
            path: Remote path to delete

        Raises:
            ConnectionLostError: If connection is lost
            FileDeletionError: If deletion fails
        """
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            raise ConnectionLostError("No connection available")

        try:
            # For ADB, rmdir handles both files and directories (rm -rf)
            from src.services.adb_client import ADBClient

            if isinstance(sftp, ADBClient):
                sftp.rmdir(path)
                return

            if self._is_remote_dir(path):
                self._delete_remote_dir(path, sftp)
            else:
                sftp.remove(path)
        except IOError as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during remote deletion", details=str(e)
                )
            raise FileDeletionError(
                "Failed to delete remote item", path=path, details=str(e)
            )
        except Exception as e:
            raise FileDeletionError(
                "Unexpected error during remote deletion", path=path, details=str(e)
            )

    def _delete_remote_dir(self, path: str, sftp: SFTPClient) -> None:
        """
        Recursively delete remote directory.

        Args:
            path: Remote directory path
            sftp: SFTP client

        Raises:
            ConnectionLostError: If connection is lost
            FileDeletionError: If deletion fails
        """
        try:
            for item in sftp.listdir(path):
                item_path = os.path.join(path, os.path.basename(item)).replace(
                    "\\", "/"
                )
                if self._is_remote_dir(item_path):
                    self._delete_remote_dir(item_path, sftp)
                else:
                    sftp.remove(item_path)
            sftp.rmdir(path)
        except IOError as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during directory deletion", details=str(e)
                )
            raise FileDeletionError(
                "Failed to delete remote directory", path=path, details=str(e)
            )

    def _delete_local(self, path: str) -> None:
        """
        Delete local file or directory.

        Args:
            path: Local path to delete

        Raises:
            FileDeletionError: If deletion fails
        """
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except PermissionError:
            raise FileDeletionError(
                "Permission denied",
                path=path,
                details="You don't have permission to delete this item",
            )
        except FileNotFoundError:
            raise FileDeletionError(
                "File not found",
                path=path,
                details="The file may have already been deleted",
            )
        except Exception as e:
            raise FileDeletionError(
                "Failed to delete local item", path=path, details=str(e)
            )

    # --------------------------------------------------------------
    #  RENAME
    # --------------------------------------------------------------
    def rename_item(self, old_path: str) -> None:
        """
        Rename a file or folder using inline editing in the explorer.

        Args:
            old_path: Current path of item to rename
        """
        explorer = self.view.remote_explorer
        basename = os.path.basename(old_path)

        # Find the tree item matching this path
        for i in range(explorer.tree_widget.topLevelItemCount()):
            item = explorer.tree_widget.topLevelItem(i)
            if item and item.text(0) == basename:
                explorer._start_inline_rename(item, 0)
                return

    # --------------------------------------------------------------
    #  DOWNLOAD
    # --------------------------------------------------------------
    def download_item(self, remote_path: str) -> None:
        """
        Download a file or folder from the remote to the configured download directory.
        """
        self._download_paths([remote_path])

    def download_items(self, remote_paths: List[str]) -> None:
        """
        Download multiple files/folders from the remote to the configured download
        directory. Each item is queued as a separate download in the transfer queue.
        """
        if not remote_paths:
            return
        self._download_paths(remote_paths)

    def _download_paths(self, remote_paths: List[str]) -> None:
        """
        Internal method to download one or more remote paths.
        Handles duplicate detection, queue display, and worker creation.
        """
        from src.workers.download_worker import DownloadWorker

        # Reset retry counter for new download
        self._download_attempts = 0

        # Use per-server download directory if configured, else global
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        local_dir = (
            server_config.get("download_directory")
            if server_config and server_config.get("download_directory")
            else self.settings.download_directory
        )
        os.makedirs(local_dir, exist_ok=True)

        # Check for duplicates and let user decide
        paths_to_download = []
        for remote_path in remote_paths:
            filename = os.path.basename(remote_path)
            local_path = os.path.join(local_dir, filename)
            if os.path.exists(local_path):
                if len(remote_paths) == 1:
                    reply = QMessageBox.question(
                        self.view,
                        DIALOG_FILE_ALREADY_EXISTS,
                        f"'{filename}' already exists in your download folder."
                        "\n\nOverwrite it?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        logger.info(f"Download: Skipped (already exists): {filename}")
                        return
                else:
                    # For multi-download, skip duplicates with a log
                    logger.info(f"Download: Skipping (already exists): {filename}")
                    continue
            paths_to_download.append(remote_path)

        if not paths_to_download:
            logger.info("Download: All files already exist locally, nothing to do")
            return

        # Get connection
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            logger.error("Download: No connection available")
            return

        # Calculate total bytes for progress
        total_bytes = 0
        for remote_path in paths_to_download:
            try:
                st = sftp.stat(remote_path)
                if st.st_size:
                    total_bytes += st.st_size
            except (IOError, OSError):
                pass

        # Display name
        if len(paths_to_download) == 1:
            display_name = f"⬇ {os.path.basename(paths_to_download[0])}"
        else:
            names = [os.path.basename(p) for p in paths_to_download[:3]]
            display_name = f"⬇ {', '.join(names)}"
            if len(paths_to_download) > 3:
                display_name += f" (+{len(paths_to_download) - 3} more)"

        # Add to visual queue
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            method = self.manual_transfer.get_transfer_method()
            index = queue.add_transfer(display_name, total_bytes, local_dir, method)
            queue.set_in_progress(index)
            self._download_queue_index = index

        # Get SFTP session for download
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )

        if connection_type == CONN_TYPE_ADB:
            download_sftp = sftp
        else:
            try:
                download_sftp = self.connection_manager.open_sftp_session()
                if download_sftp is None:
                    logger.error("Download: Could not open SFTP session")
                    if hasattr(self, "_download_queue_index"):
                        self.view.transfer_queue.set_failed(
                            self._download_queue_index, "Could not open SFTP session"
                        )
                    return
            except Exception as e:
                logger.error(f"Download: Failed to open session: {e}")
                if hasattr(self, "_download_queue_index"):
                    self.view.transfer_queue.set_failed(
                        self._download_queue_index, str(e)
                    )
                return

        # Create thread and worker
        from PySide6.QtCore import QThread

        self._download_thread = QThread(self.view)
        self._download_worker = DownloadWorker(
            sftp=download_sftp,
            remote_paths=paths_to_download,
            local_destination=local_dir,
            total_bytes=total_bytes,
        )
        self._download_worker.moveToThread(self._download_thread)

        # Connect signals
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_thread.finished.connect(self._complete_download)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_worker.error.connect(self._on_download_error_store)
        self._download_worker.error.connect(self._download_thread.quit)

        # Start
        self._download_thread.start()
        self._download_remote_paths = paths_to_download
        self._download_local_dir = local_dir
        self._download_total_bytes = total_bytes
        if len(paths_to_download) == 1:
            logger.download(f"Download: {os.path.basename(paths_to_download[0])}")
        else:
            logger.download(f"Download: {len(paths_to_download)} items")
        logger.info(f"Saving to: {local_dir}")

    def _on_download_progress(self, percent: int) -> None:
        """Handle download progress update."""
        if hasattr(self, "_download_queue_index") and hasattr(
            self.view, "transfer_queue"
        ):
            queue = self.view.transfer_queue
            index = self._download_queue_index
            if 0 <= index < len(queue._items):
                item = queue._items[index]
                item.transferred_bytes = int(item.total_bytes * percent / 100)

    def _on_download_error_store(self, error_msg: str) -> None:
        """Store error from worker thread (will be read on main thread)."""
        self._download_error_msg = error_msg

    def _complete_download(self) -> None:
        """Handle download completion or failure (runs on main thread via thread.finished)."""
        error_msg = getattr(self, "_download_error_msg", None)

        if error_msg:
            # Check if we should retry
            attempts = getattr(self, "_download_attempts", 0)
            if attempts < 3:
                self._download_attempts = attempts + 1
                self._download_error_msg = None
                logger.warn(
                    f"Download: Retry {self._download_attempts}/3: "
                    f"{error_msg.split(chr(10))[0][:60]}"
                )
                self._cleanup_download()
                # Re-trigger download after a short delay
                QTimer.singleShot(1000, self._retry_download)
                return

            # All retries exhausted — mark as failed
            if hasattr(self, "_download_queue_index") and hasattr(
                self.view, "transfer_queue"
            ):
                self.view.transfer_queue.set_failed(
                    self._download_queue_index, error_msg
                )
            self._download_error_msg = None

            # Send failure notification
            if self.settings.config.notify_on_transfer_complete:
                from src.services.notification_service import notify_transfer_failed

                remote_paths = getattr(self, "_download_remote_paths", [])
                if remote_paths:
                    filename = os.path.basename(remote_paths[0])
                    notify_transfer_failed(filename, error_msg.split("\n")[0][:60])
        else:
            # Download succeeded
            self._download_attempts = 0
            if hasattr(self, "_download_queue_index") and hasattr(
                self.view, "transfer_queue"
            ):
                self.view.transfer_queue.set_completed(self._download_queue_index)

            # Record in activity history
            remote_paths = getattr(self, "_download_remote_paths", [])
            local_dir = getattr(self, "_download_local_dir", "")
            total_bytes = getattr(self, "_download_total_bytes", 0)

            if remote_paths and local_dir:
                per_file_bytes = total_bytes // len(remote_paths) if remote_paths else 0
                last_local_path = None
                for remote_path in remote_paths:
                    filename = os.path.basename(remote_path)
                    last_local_path = os.path.join(local_dir, filename)
                    self.manual_transfer.history.add(
                        filename=filename,
                        action="download",
                        source=remote_path,
                        destination=local_dir,
                        size_bytes=per_file_bytes,
                        server_name=self.settings.config.current_server_id,
                    )

                # Reveal in Finder (if enabled in settings)
                if (
                    self.settings.config.reveal_in_finder_after_download
                    and last_local_path
                ):
                    self._reveal_in_finder(last_local_path)

                # Send success notification
                if self.settings.config.notify_on_transfer_complete:
                    from src.services.notification_service import (
                        notify_batch_complete,
                        notify_transfer_complete,
                    )

                    use_sound = self.settings.config.notify_sound
                    if len(remote_paths) == 1:
                        notify_transfer_complete(
                            os.path.basename(remote_paths[0]),
                            action="downloaded",
                            sound=use_sound,
                        )
                    else:
                        notify_batch_complete(
                            len(remote_paths),
                            action="downloaded",
                            sound=use_sound,
                        )

        # Update dock badge
        self._update_dock_badge()

        # Cleanup thread/worker
        self._cleanup_download()

    def _retry_download(self) -> None:
        """Retry a failed download using stored parameters."""
        remote_paths = getattr(self, "_download_remote_paths", [])
        local_dir = getattr(self, "_download_local_dir", "")
        total_bytes = getattr(self, "_download_total_bytes", 0)

        if not remote_paths or not local_dir:
            return

        from src.workers.download_worker import DownloadWorker

        sftp = self.view.remote_explorer.sftp
        if not sftp:
            return

        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )

        if connection_type == CONN_TYPE_ADB:
            download_sftp = sftp
        else:
            try:
                download_sftp = self.connection_manager.open_sftp_session()
                if download_sftp is None:
                    return
            except Exception:
                return

        from PySide6.QtCore import QThread

        self._download_thread = QThread(self.view)
        self._download_worker = DownloadWorker(
            sftp=download_sftp,
            remote_paths=remote_paths,
            local_destination=local_dir,
            total_bytes=total_bytes,
        )
        self._download_worker.moveToThread(self._download_thread)

        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_thread.finished.connect(self._complete_download)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_worker.error.connect(self._on_download_error_store)
        self._download_worker.error.connect(self._download_thread.quit)

        self._download_thread.start()

    def _reveal_in_finder(self, path: str) -> None:
        """Reveal a file in Finder (macOS)."""
        import subprocess

        try:
            subprocess.run(["open", "-R", path], check=False)
        except Exception:
            pass

    def _cleanup_download(self) -> None:
        """Clean up download worker and thread after thread has stopped."""
        if hasattr(self, "_download_worker") and self._download_worker:
            self._download_worker.deleteLater()
            self._download_worker = None
        if hasattr(self, "_download_thread") and self._download_thread:
            self._download_thread.deleteLater()
            self._download_thread = None

    # --------------------------------------------------------------
    #  CREATE FOLDER
    # --------------------------------------------------------------
    def create_folder(self, folder_path: str) -> None:
        """
        Create a new folder.

        Args:
            folder_path: Full path to the new folder to create
        """
        is_remote = folder_path.startswith(self.settings.remote_base_dir)

        try:
            if is_remote:
                sftp = self.view.remote_explorer.sftp
                if not sftp:
                    raise RuntimeError("No connection available")
                sftp.mkdir(folder_path)
                self.view.remote_explorer.refresh()
            else:
                os.makedirs(folder_path, exist_ok=True)

            logger.success(f"Folder: {os.path.basename(folder_path)}: Created")
        except FileExistsError:
            logger.warn(f"Folder already exists: {folder_path}")
            QMessageBox.warning(
                self.view,
                DIALOG_FOLDER_EXISTS,
                "A folder with this name already exists.",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_CREATION_FAILED,
                f"Failed to create folder:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    # --------------------------------------------------------------
    #  MOVE ITEM
    # --------------------------------------------------------------
    def move_item(self, src_path: str, dest_path: str) -> None:
        """
        Move a file or folder to a new location.

        Args:
            src_path: Current path of item to move
            dest_path: Destination path for the item
        """
        self._move_single(src_path, dest_path, confirm=True)

    def move_items(self, moves: List[tuple]) -> None:
        """
        Move multiple files/folders to new locations with a single confirmation.

        Args:
            moves: List of (src_path, dest_path) tuples
        """
        if not moves:
            return

        if len(moves) == 1:
            self._move_single(moves[0][0], moves[0][1], confirm=True)
            return

        # Single confirmation for all moves
        dest_dir = os.path.dirname(moves[0][1])
        confirm = QMessageBox.question(
            self.view,
            "Move Items",
            f"Move {len(moves)} items to:\n{dest_dir}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        for src_path, dest_path in moves:
            self._move_single(src_path, dest_path, confirm=False)

        self.view.remote_explorer.refresh()

    def _move_single(self, src_path: str, dest_path: str, confirm: bool = True) -> None:
        """
        Move a single file or folder.

        Args:
            src_path: Current path of item to move
            dest_path: Destination path for the item
            confirm: Whether to show a confirmation dialog
        """
        is_remote = src_path.startswith(self.settings.remote_base_dir)

        # Validate that source and destination are in the same filesystem
        if is_remote != dest_path.startswith(self.settings.remote_base_dir):
            logger.error("Cannot move between local and remote filesystems")
            QMessageBox.critical(
                self.view,
                DIALOG_MOVE_FAILED,
                "Cannot move between local and remote filesystems.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Prevent moving into itself or its subdirectories
        if dest_path.startswith(src_path + os.sep) or src_path == dest_path:
            logger.error("Cannot move item into itself")
            QMessageBox.critical(
                self.view,
                DIALOG_MOVE_FAILED,
                "Cannot move an item into itself or its subdirectories.",
                QMessageBox.StandardButton.Ok,
            )
            return

        if confirm:
            basename = os.path.basename(src_path)
            reply = QMessageBox.question(
                self.view,
                "Move Item",
                f"Move '{basename}' to:\n{dest_path}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            if is_remote:
                sftp = self.view.remote_explorer.sftp
                if not sftp:
                    raise RuntimeError("No connection available")
                sftp.rename(src_path, dest_path)
                if confirm:
                    self.view.remote_explorer.refresh()
            else:
                # Create destination directory if it doesn't exist
                dest_dir = os.path.dirname(dest_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src_path, dest_path)

            logger.success(
                f"Moved: {os.path.basename(src_path)}: To {os.path.basename(dest_path)}"
            )

            # Record in history
            self.manual_transfer.history.add(
                filename=os.path.basename(src_path),
                action="move",
                source=src_path,
                destination=dest_path,
                server_name=self.settings.config.current_server_id,
            )
        except FileExistsError:
            logger.warn(f"Destination already exists: {dest_path}")
            QMessageBox.warning(
                self.view,
                DIALOG_MOVE_FAILED,
                "An item with that name already exists at the destination.",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Move failed: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_MOVE_FAILED,
                f"Failed to move item:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    # --------------------------------------------------------------
    #  SETTINGS
    # --------------------------------------------------------------
    def open_settings(self) -> None:
        settings_window = SettingsWindow(self.settings)
        if settings_window.exec() == QDialog.DialogCode.Accepted:
            # Reload settings since the singleton was reset during save
            self.settings = Settings()
            self.view.settings = self.settings
            self.manual_transfer.settings = self.settings
            app = QApplication.instance()
            if app:
                apply_theme(app, self.settings.config.theme_mode)  # type: ignore
            self.refresh_explorers()

    # --------------------------------------------------------------
    #  SHUTDOWN
    # --------------------------------------------------------------
    def shutdown(self) -> None:
        """Clean shutdown of connections."""
        self._health_timer.stop()
        try:
            self.connection_manager.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
