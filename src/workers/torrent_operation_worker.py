"""Run a qBittorrent operation away from the Qt UI thread."""

from __future__ import annotations

from typing import Optional

from paramiko import Transport
from PySide6.QtCore import QObject, Signal

from src.services.torrent_download_service import TorrentDownloadService


class TorrentOperationWorker(QObject):
    """Execute one qBittorrent request using an existing SSH transport."""

    result = Signal(object)
    error = Signal(str)
    done = Signal()

    def __init__(
        self,
        transport: Transport,
        webui_port: int,
        username: str,
        password: str,
        operation: str,
        value: str = "",
        save_path: str = "",
    ) -> None:
        super().__init__()
        self._transport = transport
        self._webui_port = webui_port
        self._username = username
        self._password = password
        self._operation = operation
        self._value = value
        self._save_path = save_path

    def run(self) -> None:
        try:
            service = TorrentDownloadService(
                self._transport,
                self._webui_port,
                self._username,
                self._password,
            )
            result: Optional[object] = None
            if self._operation == "list":
                result = service.list_torrents()
            elif self._operation == "add_magnet":
                service.add_magnet(self._value, self._save_path)
            elif self._operation == "add_file":
                service.add_torrent_file(self._value, self._save_path)
            elif self._operation == "pause":
                service.pause(self._value)
            elif self._operation == "resume":
                service.resume(self._value)
            elif self._operation == "remove":
                service.remove(self._value)
            elif self._operation == "remove_data":
                service.remove_with_data(self._value)
            elif self._operation == "set_location":
                service.set_location(self._value, self._save_path)
            else:
                raise ValueError("Unsupported qBittorrent operation")
            self.result.emit(result)
        except Exception as error:
            self.error.emit(str(error))
        finally:
            self.done.emit()
