"""
Download worker — pulls files from remote to local on a background thread.

Mirrors TransferWorker but in reverse (sftp.get / adb pull).
"""

from __future__ import annotations

import os
from typing import List, Optional

from paramiko import SFTPClient
from PySide6.QtCore import QObject, Signal

from src.models.errors import ConnectionLostError
from src.utils.logging_signal import logger


class DownloadWorker(QObject):
    """
    Downloads files/folders from remote to local on a background thread.
    """

    finished = Signal()
    error = Signal(str)
    progress = Signal(int)  # percentage 0-100

    def __init__(
        self,
        sftp: SFTPClient,
        remote_paths: List[str],
        local_destination: str,
        total_bytes: int = 0,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.sftp = sftp
        self.remote_paths = remote_paths
        self.local_destination = local_destination
        self._total_bytes = total_bytes
        self._cumulative_bytes = 0

    def _is_remote_directory(self, path: str) -> bool:
        """Check if remote path is a directory."""
        try:
            from stat import S_ISDIR

            st = self.sftp.stat(path)
            return S_ISDIR(st.st_mode) if st.st_mode else False
        except (IOError, OSError):
            return False

    def _download_file(self, remote_path: str, local_dir: str) -> None:
        """Download a single file from remote to local."""
        filename = os.path.basename(remote_path)
        local_path = os.path.join(local_dir, filename)

        # Get remote file size for progress
        try:
            remote_stat = self.sftp.stat(remote_path)
            file_size = remote_stat.st_size if remote_stat.st_size else 0
        except (IOError, OSError):
            file_size = 0

        # Progress callback
        def progress_callback(transferred: int, total: int) -> None:
            if total <= 0:
                return
            if self._total_bytes > 0:
                overall_pct = int(
                    (self._cumulative_bytes + transferred) * 100 / self._total_bytes
                )
                self.progress.emit(min(overall_pct, 100))

        try:
            self.sftp.get(remote_path, local_path, callback=progress_callback)
            # Verify downloaded size matches remote
            if file_size > 0:
                local_size = (
                    os.path.getsize(local_path) if os.path.exists(local_path) else 0
                )
                if local_size != file_size:
                    # Partial download — remove the truncated file
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
                    raise IOError(
                        f"Download incomplete: got {local_size} bytes, "
                        f"expected {file_size} bytes"
                    )
            self._cumulative_bytes += file_size
            logger.success(f"Downloaded: {filename}")
        except IOError as e:
            # Clean up partial file on any failure
            if os.path.exists(local_path) and file_size > 0:
                local_size = os.path.getsize(local_path)
                if local_size < file_size:
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during download", details=str(e)
                )
            raise IOError(f"Failed to download {filename}: {e}")

    def _download_folder(self, remote_folder: str, local_dir: str) -> None:
        """Download a folder recursively."""
        folder_name = os.path.basename(remote_folder.rstrip("/"))
        local_folder = os.path.join(local_dir, folder_name)
        os.makedirs(local_folder, exist_ok=True)

        try:
            entries = self.sftp.listdir(remote_folder)
        except (IOError, OSError) as e:
            raise IOError(f"Failed to list {remote_folder}: {e}")

        for entry in entries:
            if entry.startswith(".") or entry.startswith("._"):
                continue
            remote_path = f"{remote_folder.rstrip('/')}/{entry}"
            if self._is_remote_directory(remote_path):
                self._download_folder(remote_path, local_folder)
            else:
                self._download_file(remote_path, local_folder)

    def run(self) -> None:
        """Execute the download operation."""
        try:
            for remote_path in self.remote_paths:
                if self._is_remote_directory(remote_path):
                    self._download_folder(remote_path, self.local_destination)
                else:
                    self._download_file(remote_path, self.local_destination)

            self.finished.emit()

        except ConnectionLostError as e:
            msg = f"Connection lost during download: {e.message}"
            logger.error(msg)
            self.error.emit(msg)

        except Exception as e:
            msg = f"Download failed: {e}"
            logger.error(msg)
            self.error.emit(msg)
