"""
Connection controller — owns the SSH/ADB/iOS connection lifecycle.

Handles:
- Initial connection (async for SSH, sync for ADB/iOS)
- Health monitoring with auto-reconnect
- Connection status UI updates
- ADB/iOS device discovery
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox

from src.config.settings import Settings
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import (
    CONN_TYPE_ADB,
    CONN_TYPE_IOS,
    CONN_TYPE_KEY,
    CONN_TYPE_SSH,
    DEFAULT_ADB_BASE_DIR,
    DIALOG_CONNECTION_ERROR,
    DIALOG_CONNECTION_FAILED,
    HEALTH_CHECK_INTERVAL_MS,
    TIMEOUT_FFMPEG_INSTALL,
)
from src.utils.logging_signal import logger

if TYPE_CHECKING:
    from src.views.main_window import MainWindow


class ConnectionController(QObject):
    """
    Manages connection lifecycle for all backend types (SSH, ADB, iOS).

    Signals:
        connected: Emitted after successful connection with the client object
        disconnected: Emitted when connection is lost
    """

    connected = Signal()
    disconnected = Signal()

    def __init__(
        self,
        view: "MainWindow",
        settings: Settings,
        connection_manager: ConnectionManagerService,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.view = view
        self.settings = settings
        self.connection_manager = connection_manager
        self._last_latency: float = -1.0

        # Health timer
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self.check_health)
        self._health_timer.start(HEALTH_CHECK_INTERVAL_MS)

        # Connection thread state
        self._connect_thread = None
        self._connect_worker = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection based on current server's connection type."""
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )

        if connection_type == CONN_TYPE_ADB:
            self._connect_adb(server_config)  # type: ignore
        elif connection_type == CONN_TYPE_IOS:
            self._connect_ios(server_config)  # type: ignore
        else:
            self._connect_ssh()

    def shutdown(self) -> None:
        """Stop health timer, kill any running threads, and disconnect."""
        self._health_timer.stop()

        # Stop connection thread if running
        if self._connect_thread and self._connect_thread.isRunning():
            self._connect_thread.quit()
            self._connect_thread.wait(2000)

        try:
            self.connection_manager.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    def check_health(self) -> None:
        """Periodic connection health check with auto-reconnect."""
        from src.clients.adb_client import ADBClient
        from src.clients.ios_client import IOSClient

        # Skip health check for ADB/iOS connections (stateless USB)
        if self.view.remote_explorer.sftp and isinstance(
            self.view.remote_explorer.sftp, (ADBClient, IOSClient)
        ):
            return

        # Skip if not connected
        if not self.connection_manager.is_connected():
            return

        # Skip reconnect if a transfer is in progress
        if (
            hasattr(self.view, "controller")
            and self.view.controller.manual_transfer.is_busy()
        ):
            return

        # Skip if a download is in progress
        if (
            hasattr(self.view.controller, "download_ctrl")
            and self.view.controller.download_ctrl.is_active
        ):
            return

        # Skip if DirectoryLoader is running
        if (
            self.view.remote_explorer._loader_thread
            and self.view.remote_explorer._loader_thread.isRunning()
        ):
            return

        # Check if connection is alive
        if self.connection_manager.check_alive():
            latency = self.connection_manager.measure_latency()
            self._last_latency = latency
            self._update_status_with_latency(latency)
        else:
            self._handle_connection_lost()

    @property
    def last_latency(self) -> float:
        return self._last_latency

    # ------------------------------------------------------------------
    # SSH (async via ConnectionWorker)
    # ------------------------------------------------------------------

    def _connect_ssh(self) -> None:
        """Establish SSH/SFTP connection on a background thread."""
        from PySide6.QtCore import QThread

        from src.workers.connection_worker import ConnectionWorker

        self._set_status("● Connecting...", "connection_warning")
        self.view.connect_btn.setEnabled(False)

        self._connect_thread = QThread(self.view)
        self._connect_worker = ConnectionWorker(self.connection_manager)
        self._connect_worker.moveToThread(self._connect_thread)

        self._connect_thread.started.connect(self._connect_worker.run)
        self._connect_worker.connected.connect(self._on_ssh_connected)
        self._connect_worker.failed.connect(self._on_ssh_failed)
        self._connect_worker.connected.connect(self._connect_thread.quit)
        self._connect_worker.failed.connect(self._connect_thread.quit)
        self._connect_thread.finished.connect(self._cleanup_connect_thread)

        self._connect_thread.start()

    def _on_ssh_connected(self) -> None:
        """Handle successful SSH connection."""
        self.view.connect_btn.setEnabled(True)
        self.view.connection_attempts = 0
        self._set_status("", "connection_connected")

        if self.connection_manager.sftp_client:
            start_path = self._get_initial_path(self.settings.remote_base_dir)
            self.view.remote_explorer.root_path = self.settings.remote_base_dir
            self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
            # Give detail panel its own dedicated channel (no contention)
            if self.connection_manager.sftp_metadata:
                self.view.remote_explorer._detail_panel.set_sftp(
                    self.connection_manager.sftp_metadata
                )
            # Give background workers their own channel
            if self.connection_manager.sftp_background:
                self.view.remote_explorer.set_sftp_background(
                    self.connection_manager.sftp_background
                )
            self.view.remote_explorer.refresh(start_path)

        self.connected.emit()

    def _on_ssh_failed(self, error_type: str, message: str, details: str) -> None:
        """Handle SSH connection failure."""
        self.view.connect_btn.setEnabled(True)
        detail_text = f"{message}\n\n{details}" if details else message

        if error_type == "AuthenticationError":
            self._set_status("● Authentication Failed", "connection_disconnected")
            QMessageBox.critical(
                self.view,
                "Authentication Error",
                detail_text,
                QMessageBox.StandardButton.Ok,
            )
        elif error_type == "FileAccessError":
            self._set_status("● SSH Key Error", "connection_disconnected")
            QMessageBox.critical(
                self.view,
                "SSH Key Error",
                detail_text,
                QMessageBox.StandardButton.Ok,
            )
        elif error_type == "SSHConnectionError":
            self._set_status("● Connection Failed", "connection_disconnected")
            QMessageBox.warning(
                self.view,
                DIALOG_CONNECTION_FAILED,
                detail_text,
                QMessageBox.StandardButton.Ok,
            )
        else:
            self._set_status("● Error", "connection_disconnected")
            logger.error(f"Unexpected connection error: {message}")
            QMessageBox.critical(
                self.view,
                DIALOG_CONNECTION_ERROR,
                f"An unexpected error occurred:\n{message}",
                QMessageBox.StandardButton.Ok,
            )

        self.view.handle_connection_failure()

    def _cleanup_connect_thread(self) -> None:
        if self._connect_worker:
            self._connect_worker.deleteLater()
            self._connect_worker = None
        if self._connect_thread:
            self._connect_thread.deleteLater()
            self._connect_thread = None

    # ------------------------------------------------------------------
    # ADB
    # ------------------------------------------------------------------

    def _connect_adb(self, server_config: dict) -> None:
        """Connect to an Android device via ADB."""
        from src.clients.adb_client import (
            ADBClient,
            connect_wifi,
            get_adb_path,
            get_connected_devices,
        )

        try:
            get_adb_path()
        except IOError:
            self._prompt_install_adb()
            return

        device_id = server_config.get("device_id")
        device_name = server_config.get("name", "Android Device")
        root_path = server_config.get("remote_base_dir", DEFAULT_ADB_BASE_DIR)
        wifi_ip = server_config.get("wifi_ip")

        if wifi_ip:
            logger.info(f"ADB: Attempting WiFi connection to {wifi_ip}...")
            connect_wifi(wifi_ip)

        devices = get_connected_devices()
        if not devices:
            self._set_status("● No device found", "connection_disconnected")
            logger.error("ADB: No Android device connected")
            return

        if device_id:
            matching = [d for d in devices if d["id"] == device_id]
            if not matching:
                logger.warn(f"ADB: Device {device_id} not found, using first available")
                device_id = devices[0]["id"]
        else:
            device_id = devices[0]["id"]

        try:
            client = ADBClient(device_id)
            client.listdir(root_path)

            self._set_status("", "connection_connected")
            start_path = self._get_initial_path(root_path)
            self.view.remote_explorer.root_path = root_path
            # Clear stale SSH background channel before setting ADB client
            self.view.remote_explorer.set_sftp_background(None)
            self.view.remote_explorer.set_sftp(client)
            self.view.remote_explorer.refresh(start_path)

            logger.success(f"Connected: {device_name} (USB)")
            self.connected.emit()
        except Exception as e:
            self._set_status("● ADB Error", "connection_disconnected")
            logger.error(f"ADB connection failed: {e}")

    # ------------------------------------------------------------------
    # iOS
    # ------------------------------------------------------------------

    def _connect_ios(self, server_config: dict) -> None:
        """Connect to an iPhone/iPad via USB (AFC protocol)."""
        from src.clients.ios_client import IOSClient, get_connected_ios_devices

        device_id = server_config.get("device_id")
        device_name = server_config.get("name", "iPhone")
        root_path = server_config.get("remote_base_dir", "/DCIM")

        devices = get_connected_ios_devices()
        if not devices:
            self._set_status("● No iPhone found", "connection_disconnected")
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

        if device_id:
            matching = [d for d in devices if d["id"] == device_id]
            if not matching:
                logger.warn(f"iOS: Device {device_id} not found, using first available")
                device_id = devices[0]["id"]
        else:
            device_id = devices[0]["id"]

        try:
            client = IOSClient(device_id)
            client.listdir(root_path)

            self._set_status("", "connection_connected")
            start_path = self._get_initial_path(root_path)
            self.view.remote_explorer.root_path = root_path
            # Clear stale SSH background channel before setting iOS client
            self.view.remote_explorer.set_sftp_background(None)
            self.view.remote_explorer.set_sftp(client)
            self.view.remote_explorer.refresh(start_path)

            logger.success(f"Connected: {device_name} (iPhone)")
            self.connected.emit()
        except Exception as e:
            self._set_status("● iOS Error", "connection_disconnected")
            logger.error(f"iOS connection failed: {e}")
            QMessageBox.critical(
                self.view,
                "iOS Connection Error",
                f"Failed to connect to iPhone:\n\n{e}\n\n"
                "Make sure pymobiledevice3 is installed:\n"
                "pip install pymobiledevice3",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_initial_path(self, root_path: str) -> str:
        """Choose the first path shown after connecting."""
        return self.settings.get_default_bookmark() or root_path

    def _set_status(self, text: str, object_name: str) -> None:
        """Update connection status label text and style."""
        label = self.view.connection_status_label
        label.setText(text)
        label.setObjectName(object_name)
        label.style().polish(label)
        self._update_connect_btn()

    def _update_status_with_latency(self, latency: float) -> None:
        """Update status bar with latency and color-coded quality."""
        label = self.view.connection_status_label
        if latency >= 0:
            label.setText(f"{latency:.0f}ms")
            if latency < 100:
                label.setObjectName("connection_connected")
            elif latency < 300:
                label.setObjectName("connection_warning")
            else:
                label.setObjectName("connection_slow")
            label.style().polish(label)
            self._update_connect_btn()

    def _update_connect_btn(self) -> None:
        """Sync the power button color with connection status."""
        obj_name = self.view.connection_status_label.objectName()
        btn = self.view.connect_btn
        if obj_name == "connection_connected":
            btn.setStyleSheet("QPushButton#icon_btn { color: #30d158; }")
        else:
            btn.setStyleSheet("")

    def _handle_connection_lost(self) -> None:
        """Handle detected connection loss — attempt auto-reconnect."""
        logger.warn("Connection: Lost — attempting reconnect...")
        self._set_status("● Reconnecting...", "connection_warning")

        if self.connection_manager.reconnect():
            if self.connection_manager.sftp_client:
                self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
                if self.connection_manager.sftp_metadata:
                    self.view.remote_explorer._detail_panel.set_sftp(
                        self.connection_manager.sftp_metadata
                    )
                if self.connection_manager.sftp_background:
                    self.view.remote_explorer.set_sftp_background(
                        self.connection_manager.sftp_background
                    )
                self.view.remote_explorer.refresh()
            self._set_status("", "connection_connected")
            logger.success("Connection: Reconnected")
            self.connected.emit()
        else:
            self._set_status("● Disconnected", "connection_disconnected")
            logger.error("Connection: Reconnect failed")
            self.disconnected.emit()

    def handle_explorer_failure(self, error_msg: str) -> None:
        """Handle remote explorer errors by attempting to reconnect."""
        logger.error(f"Explorer Error: {error_msg}")

        # Determine connection type so we use the correct reconnect path
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )

        if connection_type == CONN_TYPE_ADB:
            self._connect_adb(server_config)  # type: ignore
        elif connection_type == CONN_TYPE_IOS:
            self._connect_ios(server_config)  # type: ignore
        else:
            ok = self.connection_manager.connect()
            if ok and self.connection_manager.sftp_client:
                self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
                self.view.remote_explorer.refresh(self.settings.remote_base_dir)
            else:
                self._set_status("● Disconnected", "connection_disconnected")
                logger.error("Cannot recover connection.")

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
        """Run brew install android-platform-tools."""
        import subprocess

        logger.info("Installing ADB via Homebrew...")
        self._set_status("● Installing ADB...", "connection_warning")

        try:
            result = subprocess.run(
                ["brew", "install", "android-platform-tools"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_FFMPEG_INSTALL,
            )
            if result.returncode == 0:
                logger.success("ADB installed. Connect device and try again.")
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

        self._set_status("● Disconnected", "connection_disconnected")
