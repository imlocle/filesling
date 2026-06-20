"""
Disk usage worker — runs 'df' on a background thread.

Must be a top-level QObject class (not defined inline in a method) so that
Qt's meta-object system properly registers the signals for cross-thread
queued connections. Defining QObject+Signal inside a method body causes
NSWindow crashes on macOS when the signal triggers UI updates.
"""

from __future__ import annotations

import shlex

from PySide6.QtCore import QObject, Signal


class DiskUsageWorker(QObject):
    """Background worker that queries remote filesystem disk usage via SSH."""

    finished = Signal(
        object, object
    )  # used_bytes, total_bytes (use object to avoid C++ int overflow)
    error = Signal()

    def __init__(self, sftp: object, path: str) -> None:
        super().__init__()
        self._sftp = sftp
        self._path = path

    def run(self) -> None:
        """Execute df command and emit results."""
        try:
            channel = self._sftp.get_channel()
            if not channel:
                self.error.emit()
                return
            transport = channel.get_transport()
            if not transport:
                self.error.emit()
                return

            session = transport.open_session()
            session.exec_command(f"df -B1 {shlex.quote(self._path)} | tail -1")
            output = session.recv(1024).decode("utf-8").strip()
            session.close()

            if not output:
                self.error.emit()
                return

            parts = output.split()
            if len(parts) < 4:
                self.error.emit()
                return

            total_bytes = int(parts[1])
            used_bytes = int(parts[2])
            self.finished.emit(used_bytes, total_bytes)
        except Exception:
            self.error.emit()
