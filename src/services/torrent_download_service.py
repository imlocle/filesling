"""Application operations for remote qBittorrent downloads."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from paramiko import Transport

from src.clients.qbittorrent_client import QBittorrentClient
from src.models.torrent import TorrentInfo

MAX_TORRENT_FILE_BYTES = 32 * 1024 * 1024


class TorrentDownloadService:
    """Coordinate qBittorrent API operations for one SSH server."""

    def __init__(
        self,
        transport: Transport,
        webui_port: int,
        username: str,
        password: str,
    ) -> None:
        self._client = QBittorrentClient(
            transport=transport,
            port=webui_port,
            username=username,
            password=password,
        )

    def list_torrents(self) -> list[TorrentInfo]:
        return self._client.list_torrents()

    def add_magnet(self, magnet_link: str, save_path: str) -> None:
        magnet = magnet_link.strip()
        parsed = urlsplit(magnet)
        if (
            parsed.scheme.lower() != "magnet"
            or not parsed.query
            or any(character in magnet for character in "\r\n\0")
        ):
            raise ValueError("Enter a valid magnet link")
        self._client.add_magnet(magnet, self._validate_save_path(save_path))

    def add_torrent_file(self, torrent_path: str, save_path: str) -> None:
        path = Path(torrent_path).expanduser()
        if path.suffix.lower() != ".torrent":
            raise ValueError("Choose a file with the .torrent extension")
        try:
            with path.open("rb") as torrent_file:
                torrent_data = torrent_file.read(MAX_TORRENT_FILE_BYTES + 1)
        except OSError as error:
            raise ValueError(f"Could not read the torrent file: {error}") from error
        if not torrent_data or len(torrent_data) > MAX_TORRENT_FILE_BYTES:
            raise ValueError("Torrent files must be between 1 byte and 32 MB")
        self._client.add_torrent_file(
            path.name,
            torrent_data,
            self._validate_save_path(save_path),
        )

    def pause(self, torrent_hash: str) -> None:
        self._client.pause(torrent_hash)

    def resume(self, torrent_hash: str) -> None:
        self._client.resume(torrent_hash)

    def remove(self, torrent_hash: str) -> None:
        self._client.remove(torrent_hash)

    def remove_with_data(self, torrent_hash: str) -> None:
        self._client.remove_with_data(torrent_hash)

    def set_location(self, torrent_hash: str, location: str) -> None:
        path = self._validate_save_path(location)
        if not path:
            raise ValueError("Enter an absolute folder path on the Raspberry Pi")
        self._client.set_location(torrent_hash, path)

    @staticmethod
    def _validate_save_path(save_path: str) -> str:
        path = save_path.strip()
        if not path:
            return ""
        if (
            not path.startswith("/")
            or any(character in path for character in "\r\n\0")
        ):
            raise ValueError("Enter an absolute folder path on the Raspberry Pi")
        return path
