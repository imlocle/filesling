"""Coordinate FileSling UI actions with qBittorrent running over SSH."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtWidgets import QDialog, QMessageBox

from src.config.settings import Settings
from src.models.torrent import TorrentInfo
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import CONN_TYPE_SSH
from src.utils.logging_signal import logger
from src.views.dialogs.torrent_downloads_dialog import TorrentDownloadsDialog
from src.workers.torrent_operation_worker import TorrentOperationWorker

if TYPE_CHECKING:
    from src.views.main_window import MainWindow


class TorrentDownloadController(QObject):
    """Manage the torrent dialog and background qBittorrent operations."""

    def __init__(
        self,
        view: "MainWindow",
        settings: Settings,
        connection_manager: ConnectionManagerService,
        request_jellyfin_refresh: Callable[[str, Optional[bool]], None],
    ) -> None:
        super().__init__(view)
        self._view = view
        self._settings = settings
        self._connection_manager = connection_manager
        self._request_jellyfin_refresh = request_jellyfin_refresh
        self._dialog: Optional[TorrentDownloadsDialog] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[TorrentOperationWorker] = None
        self._server_id = ""
        self._jellyfin_override: Optional[bool] = None
        self._webui_port = 8080
        self._webui_username = ""
        self._webui_password = ""
        self._operation = ""
        self._operation_failed = False
        self._refresh_after_operation = False
        self._pending_operations: list[tuple[str, str, str]] = []
        self._has_snapshot = False
        self._previous_progress: dict[str, float] = {}

    def open_dialog(self) -> None:
        """Open remote torrent controls for the active SSH server."""
        server_id = self._settings.config.current_server_id
        if self._dialog is not None:
            if self._server_id == server_id:
                config = self._settings.get_server_config(server_id)
                password = self._settings.get_server_secret(
                    server_id, "qbittorrent_password"
                ) or ""
                if (
                    config is None
                    or not password
                    or not config.qbittorrent_username.strip()
                ):
                    self._dialog.set_status(
                        "Configure qBittorrent credentials in this SSH server's "
                        "settings."
                    )
                    self._dialog.show()
                    self._dialog.raise_()
                    self._dialog.activateWindow()
                    return
                self._webui_port = config.qbittorrent_webui_port
                self._webui_username = config.qbittorrent_username
                self._webui_password = password
                self._dialog.show()
                self._dialog.raise_()
                self._dialog.activateWindow()
                self.refresh()
                return
            if self._thread is not None and self._thread.isRunning():
                QMessageBox.information(
                    self._view,
                    "Torrent Request In Progress",
                    "Wait for the current server's qBittorrent request to finish "
                    "first.",
                )
                return
            self._dialog.deleteLater()
            self._dialog = None

        server = self._settings.get_server(server_id) or {}
        if server.get("connection_type", CONN_TYPE_SSH) != CONN_TYPE_SSH:
            QMessageBox.information(
                self._view,
                "SSH Connection Required",
                "Remote torrent downloads are available for SSH server connections.",
            )
            return
        if (
            not self._connection_manager.is_connected()
            or not self._connection_manager.ssh_client
        ):
            QMessageBox.information(
                self._view,
                "Connect to the Server",
                "Connect to the SSH server before opening remote torrent downloads.",
            )
            return

        config = self._settings.get_server_config(server_id)
        if config is None:
            QMessageBox.warning(
                self._view,
                "Server Not Found",
                "Select a saved SSH server first.",
            )
            return
        password = self._settings.get_server_secret(
            server_id, "qbittorrent_password"
        ) or ""
        if not password or not config.qbittorrent_username.strip():
            from src.views.settings_window import SettingsWindow

            QMessageBox.information(
                self._view,
                "Configure qBittorrent",
                "Enter the qBittorrent Web UI username and password in this "
                "server's settings.",
            )
            settings_dialog = SettingsWindow(
                self._settings, server_mode=True, server_id=server_id
            )
            if settings_dialog.exec() != QDialog.DialogCode.Accepted:
                return
            config = self._settings.get_server_config(server_id)
            password = self._settings.get_server_secret(
                server_id, "qbittorrent_password"
            ) or ""
            if (
                config is None
                or not password
                or not config.qbittorrent_username.strip()
            ):
                return

        transport = self._connection_manager.ssh_client.get_transport()
        if transport is None or not transport.is_active():
            QMessageBox.warning(
                self._view,
                "SSH Tunnel Unavailable",
                "Reconnect to the SSH server before opening torrent downloads.",
            )
            return

        self._server_id = server_id
        self._jellyfin_override = None
        self._webui_port = config.qbittorrent_webui_port
        self._webui_username = config.qbittorrent_username
        self._webui_password = password
        self._previous_progress.clear()
        self._has_snapshot = False

        default_path = config.qbittorrent_download_path
        profile_controller = getattr(
            self._view, "destination_profile_controller", None
        )
        profile = (
            profile_controller.get_active_profile() if profile_controller else None
        )
        if profile and profile.server_id == server_id:
            default_path = profile.remote_path
            self._jellyfin_override = profile.refresh_jellyfin

        server_name = str(server.get("name") or config.host or server_id)
        dialog = TorrentDownloadsDialog(self._view, server_name, default_path)
        self._dialog = dialog
        dialog.refresh_requested.connect(self.refresh)
        dialog.add_magnet_requested.connect(self.add_magnet)
        dialog.add_file_requested.connect(self.add_torrent_file)
        dialog.pause_requested.connect(
            lambda torrent_hash: self._run("pause", torrent_hash)
        )
        dialog.resume_requested.connect(
            lambda torrent_hash: self._run("resume", torrent_hash)
        )
        dialog.remove_requested.connect(
            lambda torrent_hash: self._run("remove", torrent_hash)
        )
        dialog.delete_data_requested.connect(
            lambda torrent_hash: self._run("remove_data", torrent_hash)
        )
        dialog.move_requested.connect(
            lambda torrent_hash, save_path: self._run(
                "set_location", torrent_hash, save_path
            )
        )
        dialog.settings_requested.connect(self.open_server_settings)
        dialog.show()
        self.refresh()

    def open_server_settings(self) -> None:
        """Open settings for the SSH server used by the torrent dialog."""
        dialog = self._dialog
        if dialog is None or (
            self._thread is not None and self._thread.isRunning()
        ):
            return

        dialog.stop_auto_refresh()
        from src.views.settings_window import SettingsWindow

        settings_dialog = SettingsWindow(
            self._settings, server_mode=True, server_id=self._server_id
        )
        if settings_dialog.exec() != QDialog.DialogCode.Accepted:
            if dialog.isVisible():
                dialog.start_auto_refresh()
            return

        config = self._settings.get_server_config(self._server_id)
        password = self._settings.get_server_secret(
            self._server_id, "qbittorrent_password"
        ) or ""
        if config is None:
            dialog.set_status("Could not reload this server's settings.")
            return

        self._webui_port = config.qbittorrent_webui_port
        self._webui_username = config.qbittorrent_username
        self._webui_password = password
        if not self._webui_username.strip() or not password:
            dialog.set_status(
                "Settings saved. Enter the qBittorrent Web UI username and "
                "password to use remote downloads."
            )
            return

        self.refresh()

    def refresh(self) -> None:
        self._run("list")

    def add_magnet(self, magnet_link: str, save_path: str) -> None:
        self._run("add_magnet", magnet_link, save_path)

    def add_torrent_file(self, torrent_path: str, save_path: str) -> None:
        self._run("add_file", torrent_path, save_path)

    def shutdown(self) -> None:
        """Wait for bounded API work before the SSH transport is closed."""
        if self._dialog is not None:
            self._dialog.stop_auto_refresh()
        if self._thread is not None and self._thread.isRunning():
            if not self._thread.wait(17000):
                logger.warn("Torrent: Stopping a qBittorrent request during shutdown")
                self._thread.terminate()
                self._thread.wait(500)

    def _run(self, operation: str, value: str = "", save_path: str = "") -> None:
        if self._dialog is None:
            return
        if self._thread is not None and self._thread.isRunning():
            if operation == "list":
                if self._operation != "list":
                    self._refresh_after_operation = True
            elif self._operation == "list":
                self._pending_operations.append((operation, value, save_path))
                self._dialog.set_busy(
                    True,
                    "Finishing status refresh. Your request is queued.",
                )
            return
        ssh_client = self._connection_manager.ssh_client
        transport = ssh_client.get_transport() if ssh_client else None
        if (
            not self._connection_manager.is_connected()
            or transport is None
            or not transport.is_active()
        ):
            self._dialog.stop_auto_refresh()
            self._dialog.set_busy(False)
            self._dialog.set_status(
                "SSH connection was lost. Reconnect, then refresh the torrent list."
            )
            return

        self._operation = operation
        self._operation_failed = False
        self._refresh_after_operation = operation != "list"
        self._dialog.set_busy(
            True,
            self._operation_message(operation),
            allow_add=operation == "list",
        )
        self._thread = QThread(self._view)
        self._worker = TorrentOperationWorker(
            transport=transport,
            webui_port=self._webui_port,
            username=self._webui_username,
            password=self._webui_password,
            operation=operation,
            value=value,
            save_path=save_path,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _on_result(self, result: object) -> None:
        dialog = self._dialog
        if dialog is None:
            return
        if self._operation == "list" and isinstance(result, list):
            torrents = [item for item in result if isinstance(item, TorrentInfo)]
            self._handle_torrent_snapshot(torrents)
            dialog.set_torrents(torrents)
            dialog.set_status(
                f"{len(torrents)} torrent job(s). Auto-refreshes every 10 seconds."
            )
            if dialog.isVisible():
                dialog.start_auto_refresh()
            else:
                dialog.stop_auto_refresh()
            return

        messages = {
            "add_magnet": "Magnet link sent to qBittorrent.",
            "add_file": "Torrent file sent to qBittorrent.",
            "pause": "Torrent paused.",
            "resume": "Torrent resumed.",
            "remove": "Torrent job removed. Downloaded data was kept.",
            "remove_data": "Torrent job and downloaded data deleted.",
            "set_location": "qBittorrent is moving the torrent data.",
        }
        dialog.set_status(messages.get(self._operation, "qBittorrent updated."))
        if self._operation in ("add_magnet", "add_file"):
            dialog.magnet_input.clear()

    def _on_error(self, message: str) -> None:
        self._operation_failed = True
        self._refresh_after_operation = False
        dialog = self._dialog
        if dialog is not None:
            dialog.stop_auto_refresh()
            dialog.set_status(message)
        logger.warn(f"Torrent: {message}")

    def _on_thread_finished(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.deleteLater()
        self._worker = None
        self._thread = None
        dialog = self._dialog

        if self._pending_operations:
            operation, value, save_path = self._pending_operations.pop(0)
            QTimer.singleShot(
                0,
                lambda: self._run(operation, value, save_path),
            )
            return

        if dialog is not None:
            dialog.set_busy(False)
        should_refresh = self._refresh_after_operation
        self._refresh_after_operation = False
        if not self._operation_failed and should_refresh and dialog:
            QTimer.singleShot(0, self.refresh)

    def _handle_torrent_snapshot(self, torrents: list[TorrentInfo]) -> None:
        current_progress = {torrent.hash: torrent.progress for torrent in torrents}
        if self._has_snapshot:
            for torrent in torrents:
                was_complete = self._previous_progress.get(torrent.hash, 0.0) >= 0.999
                is_complete = torrent.progress >= 0.999
                if is_complete and not was_complete:
                    self._request_jellyfin_refresh(
                        self._server_id, self._jellyfin_override
                    )
        self._previous_progress = current_progress
        self._has_snapshot = True

    @staticmethod
    def _operation_message(operation: str) -> str:
        messages = {
            "list": "Refreshing torrent status...",
            "add_magnet": "Sending magnet link to qBittorrent...",
            "add_file": "Sending torrent file to qBittorrent...",
            "pause": "Pausing torrent...",
            "resume": "Resuming torrent...",
            "remove": "Removing torrent job...",
            "remove_data": "Deleting torrent job and downloaded data...",
            "set_location": "Moving torrent data to the selected folder...",
        }
        return messages.get(operation, "Contacting qBittorrent...")
