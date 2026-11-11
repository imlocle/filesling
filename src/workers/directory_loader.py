"""Background worker for loading local and remote directory entries."""

from __future__ import annotations

import os
from stat import S_ISDIR
from typing import Optional

from paramiko import SFTPClient
from PySide6.QtCore import QObject, Signal

from src.config.settings import Settings
from src.utils.file_size import format_bytes, get_directory_size


class DirectoryLoader(QObject):
    """Background worker that loads directory entries via SFTP or local filesystem."""

    finished = Signal(list)  # list of (entry, icon_hint, size_str, size_bytes)
    batch_ready = Signal(list)  # partial results for progressive loading
    nfo_files_found = Signal(str, int, list)
    error = Signal(str)

    def __init__(
        self,
        path: str,
        is_remote: bool,
        sftp: Optional[SFTPClient],
        settings: Settings,
        generation: int = 0,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.is_remote = is_remote
        self.sftp = sftp
        self.settings = settings
        self.generation = generation
        self.nfo_names: list[str] = []

    def run(self) -> None:
        """Load directory entries."""
        self.nfo_names = []
        try:
            if self.is_remote:
                if not self.sftp:
                    self.error.emit("SFTP connection not available")
                    return

                # Use listdir_attr to get names + sizes in one call
                # (avoids per-file stat calls, critical for ADB performance)
                if hasattr(self.sftp, "listdir_attr"):
                    # Check if streaming is available (ADB)
                    if hasattr(self.sftp, "listdir_attr_stream"):
                        all_results = []
                        for batch in self.sftp.listdir_attr_stream(  # type: ignore
                            self.path, batch_size=50
                        ):
                            batch_results = []
                            for attr in batch:
                                if attr.filename.lower().endswith(".nfo"):
                                    self.nfo_names.append(attr.filename)
                                if (
                                    attr.filename.startswith(".")
                                    or attr.filename.startswith("._")
                                    or attr.filename in self.settings.skip_files
                                    or (
                                        self.settings.config.hide_nfo_files
                                        and attr.filename.endswith(".nfo")
                                    )
                                ):
                                    continue
                                is_dir = (
                                    S_ISDIR(attr.st_mode) if attr.st_mode else False
                                )
                                size_bytes = -1 if is_dir else (attr.st_size or 0)
                                size_str = format_bytes(size_bytes)
                                batch_results.append(
                                    (attr.filename, is_dir, size_str, size_bytes)
                                )
                            if batch_results:
                                self.batch_ready.emit(batch_results)
                                all_results.extend(batch_results)

                        # Sort final results and emit finished
                        all_results.sort(key=lambda r: r[0].lower())
                        self.nfo_files_found.emit(
                            self.path, self.generation, self.nfo_names
                        )
                        self.finished.emit(all_results)
                        return

                    # Non-streaming fallback (Paramiko SFTP)
                    attrs = self.sftp.listdir_attr(self.path)
                    self.nfo_names = [
                        attr.filename
                        for attr in attrs
                        if attr.filename.lower().endswith(".nfo")
                    ]
                    filtered = [
                        a
                        for a in attrs
                        if not (
                            a.filename.startswith(".")
                            or a.filename.startswith("._")
                            or a.filename in self.settings.skip_files
                            or (
                                self.settings.config.hide_nfo_files
                                and a.filename.endswith(".nfo")
                            )
                        )
                    ]
                    filtered.sort(key=lambda a: a.filename.lower())

                    results = []
                    for attr in filtered:
                        is_dir = S_ISDIR(attr.st_mode) if attr.st_mode else False
                        size_bytes = -1 if is_dir else (attr.st_size or 0)
                        size_str = format_bytes(size_bytes)
                        results.append((attr.filename, is_dir, size_str, size_bytes))

                    self.nfo_files_found.emit(
                        self.path, self.generation, self.nfo_names
                    )
                    self.finished.emit(results)
                    return

                # Fallback: listdir + individual stat calls
                entries = self.sftp.listdir(self.path)
                self.nfo_names = [
                    entry for entry in entries if entry.lower().endswith(".nfo")
                ]
            else:
                entries = os.listdir(self.path)

            filtered = [
                e
                for e in entries
                if not (
                    e.startswith(".")
                    or e.startswith("._")
                    or e in self.settings.skip_files
                    or (self.settings.config.hide_nfo_files and e.endswith(".nfo"))
                )
            ]
            filtered.sort(key=lambda s: s.lower())

            results = []
            for entry in filtered:
                full_path = os.path.join(self.path, entry)
                is_dir = self._check_is_dir(full_path)
                size_bytes = self._get_size_bytes(full_path, is_dir)
                size_str = format_bytes(size_bytes)
                results.append((entry, is_dir, size_str, size_bytes))

            if self.is_remote:
                self.nfo_files_found.emit(
                    self.path, self.generation, self.nfo_names
                )
            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))

    def _check_is_dir(self, path: str) -> bool:
        try:
            if self.is_remote:
                if not self.sftp:
                    return False
                st = self.sftp.stat(path)
                if st.st_mode is None:
                    return False
                return S_ISDIR(st.st_mode)
            return os.path.isdir(path)
        except Exception:
            return False

    def _get_size_bytes(self, path: str, is_dir: bool) -> int:
        try:
            if self.is_remote:
                if is_dir:
                    return -1
                if not self.sftp:
                    return -1
                st = self.sftp.stat(path)
                return st.st_size if st.st_size is not None else -1
            else:
                if is_dir:
                    return get_directory_size(path)
                return os.path.getsize(path)
        except Exception:
            return -1
