"""
Search worker — recursively searches remote directories in the background.

Extracted from FileExplorerWidget's inline class definition for testability.
"""

from __future__ import annotations

import os
from stat import S_ISDIR

from PySide6.QtCore import QObject, Signal


class SearchWorker(QObject):
    """
    Background worker that searches remote directories recursively.

    Emits results as a list of (relative_path, is_dir, size_str) tuples.
    """

    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self, sftp: object, base_path: str, query: str, max_depth: int = 3
    ) -> None:
        super().__init__()
        self.sftp = sftp
        self.base_path = base_path
        self.query = query
        self.max_depth = max_depth

    def run(self) -> None:
        """Execute recursive search."""
        try:
            results = []
            self._search_dir(self.base_path, results, 0)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _search_dir(self, path: str, results: list, depth: int) -> None:
        """Recursively search a directory."""
        if depth > self.max_depth:
            return
        try:
            entries = self.sftp.listdir_attr(path)
            for attr in entries:
                name = attr.filename
                if name.startswith(".") or name.startswith("._"):
                    continue
                full_path = f"{path}/{name}"
                is_dir = attr.st_mode is not None and S_ISDIR(attr.st_mode)

                if self.query in name.lower():
                    rel = os.path.relpath(full_path, self.base_path)
                    size_str = "—" if is_dir else self._fmt_size(attr.st_size or 0)
                    results.append((rel, is_dir, size_str))

                if is_dir:
                    self._search_dir(full_path, results, depth + 1)
        except Exception:
            pass

    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
