from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Optional

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
        view,
        connection_manager: ConnectionManagerService,
    ):
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

    def _connect_controller_signals(self) -> None:
        """Connect controller signals to UI updates."""
        # Manual transfer signals
        self.manual_transfer.transfer_started.connect(self._on_manual_transfer_started)
        self.manual_transfer.transfer_completed.connect(
            self._on_manual_transfer_completed
        )
        self.manual_transfer.transfer_failed.connect(self._on_manual_transfer_failed)
        self.manual_transfer.transfer_progress.connect(self._on_transfer_progress)
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
            queue.add_transfer(transfer.display_name, transfer.total_bytes)

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

    def _on_manual_transfer_completed(self, path: str) -> None:
        """Handle manual transfer completed — mark item as done."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            self.view.transfer_queue.set_completed(self._current_queue_index)
            self._current_queue_index = -1
        self.refresh_explorers()

    def _on_manual_transfer_failed(self, path: str, error: str) -> None:
        """Handle manual transfer failed — mark item as failed."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            short_error = error.split("\n")[0][:80]
            self.view.transfer_queue.set_failed(self._current_queue_index, short_error)
            self._current_queue_index = -1

    def _on_transfer_progress(self, percentage: int) -> None:
        """Handle transfer progress update."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            # Convert percentage back to bytes for the queue widget
            queue = self.view.transfer_queue
            if self._current_queue_index < len(queue._items):
                item = queue._items[self._current_queue_index]
                transferred = int(item.total_bytes * percentage / 100)
                queue.update_progress(self._current_queue_index, transferred, 0)

    def _on_queue_changed(self, total: int) -> None:
        """Handle transfer queue size change — add items to visual queue."""
        pass  # Queue widget is updated directly via add_transfer

    def _on_cancel_transfer(self, pending_index: int) -> None:
        """Handle cancel request from queue widget."""
        self.manual_transfer.cancel_queued_item(pending_index)

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

        self._connect_ssh()

    def _connect_adb(self, server_config: dict) -> None:
        """Connect to an Android device via ADB."""
        from src.services.adb_client import ADBClient, get_adb_path, get_connected_devices

        # Check if ADB is installed
        try:
            get_adb_path()
        except IOError:
            self._prompt_install_adb()
            return

        device_id = server_config.get("device_id")
        device_name = server_config.get("name", "Android Device")
        root_path = server_config.get("remote_base_dir", DEFAULT_ADB_BASE_DIR)

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
            self.view.connection_status_label.setText(
                f"● Connected: {device_name} (USB)"
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

    def handle_file_open(self, path: str) -> None:
        """Handle file open event from explorer."""
        logger.info(f"📂 Opened file: {path}")

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
            # Multi-delete confirmation
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
        from src.workers.download_worker import DownloadWorker

        # Use configured download directory
        local_dir = self.settings.download_directory
        os.makedirs(local_dir, exist_ok=True)

        # Check for duplicate locally
        filename = os.path.basename(remote_path)
        local_path = os.path.join(local_dir, filename)
        if os.path.exists(local_path):
            reply = QMessageBox.question(
                self.view,
                DIALOG_FILE_ALREADY_EXISTS,
                f"'{filename}' already exists in your download folder.\n\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                logger.info(f"Download: Skipped (already exists): {filename}")
                return

        # Get file size for progress
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            logger.error("Download: No connection available")
            return

        total_bytes = 0
        try:
            st = sftp.stat(remote_path)
            if st.st_size:
                total_bytes = st.st_size
        except (IOError, OSError):
            pass

        # Display name
        display_name = f"⬇ {os.path.basename(remote_path)}"

        # Add to visual queue and immediately mark as in-progress
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            index = queue.add_transfer(display_name, total_bytes)
            queue.set_in_progress(index)
            self._download_queue_index = index

        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )

        if connection_type == CONN_TYPE_ADB:
            download_sftp = sftp
        else:
            # Open a dedicated SFTP session for the download
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
            remote_paths=[remote_path],
            local_destination=local_dir,
            total_bytes=total_bytes,
        )
        self._download_worker.moveToThread(self._download_thread)

        # Connect signals
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_thread.finished.connect(self._cleanup_download)

        # Start
        self._download_thread.start()
        self._download_remote_path = remote_path
        self._download_local_dir = local_dir
        self._download_total_bytes = total_bytes
        logger.download(f"Download: {os.path.basename(remote_path)}")
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

    def _on_download_finished(self) -> None:
        """Handle download completion — defer to main thread via timer."""
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._complete_download)

    def _complete_download(self) -> None:
        """Actually mark download complete (runs on main thread)."""
        if hasattr(self, "_download_queue_index") and hasattr(
            self.view, "transfer_queue"
        ):
            self.view.transfer_queue.set_completed(self._download_queue_index)

        # Record in transfer history
        if hasattr(self, "_download_remote_path") and hasattr(
            self, "_download_local_dir"
        ):
            self.manual_transfer.history.add(
                filename=os.path.basename(self._download_remote_path),
                direction="download",
                source=self._download_remote_path,
                destination=self._download_local_dir,
                size_bytes=getattr(self, "_download_total_bytes", 0),
                server_name=self.settings.config.current_server_id,
            )

        if hasattr(self, "_download_thread") and self._download_thread:
            self._download_thread.quit()

    def _on_download_error(self, error_msg: str) -> None:
        """Handle download failure — defer to main thread via timer."""
        from PySide6.QtCore import QTimer

        self._download_error_msg = error_msg
        QTimer.singleShot(0, self._fail_download)

    def _fail_download(self) -> None:
        """Actually mark download failed (runs on main thread)."""
        error_msg = getattr(self, "_download_error_msg", "Unknown error")
        if hasattr(self, "_download_queue_index") and hasattr(
            self.view, "transfer_queue"
        ):
            self.view.transfer_queue.set_failed(self._download_queue_index, error_msg)
        if hasattr(self, "_download_thread") and self._download_thread:
            self._download_thread.quit()

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

        basename = os.path.basename(src_path)
        confirm = QMessageBox.question(
            self.view,
            "Move Item",
            f"Move '{basename}' to:\n{dest_path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            if is_remote:
                sftp = self.view.remote_explorer.sftp
                if not sftp:
                    raise RuntimeError("No connection available")
                sftp.rename(src_path, dest_path)
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
    def open_settings(self):
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
        try:
            self.connection_manager.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
