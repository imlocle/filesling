"""Background loader for NFO sidecars found in one remote directory."""

from __future__ import annotations

import posixpath
from typing import Dict, List

from paramiko import SFTPClient
from PySide6.QtCore import QObject, Signal

from src.services.remote_media_service import RemoteMediaService


class NfoCacheWorker(QObject):
    """Read and parse a folder's sidecar files away from the UI thread."""

    loaded = Signal(str, int, dict)

    def __init__(
        self,
        sftp: SFTPClient,
        directory: str,
        nfo_names: List[str],
        generation: int,
    ) -> None:
        super().__init__()
        self._sftp = sftp
        self._directory = directory
        self._nfo_names = nfo_names
        self._generation = generation

    def run(self) -> None:
        """Read each listed sidecar and return the parsed values by full path."""
        service = RemoteMediaService(self._sftp)
        metadata_by_path: Dict[str, Dict[str, str]] = {}
        directory = self._directory.replace("\\", "/")
        for name in self._nfo_names:
            nfo_path = posixpath.join(directory, name)
            try:
                metadata_by_path[nfo_path] = service.read_nfo_path(nfo_path)
            except Exception:
                continue
        self.loaded.emit(self._directory, self._generation, metadata_by_path)
