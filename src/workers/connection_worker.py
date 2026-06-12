"""
Connection worker — runs SSH connection attempts on a background thread.

Emits success/failure signals so the UI thread stays responsive during
the potentially slow SSH handshake + retry loop.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from src.services.connection_manager_service import ConnectionManagerService


class ConnectionWorker(QObject):
    """
    Runs ConnectionManagerService.connect() on a background thread.

    Signals:
        connected: Emitted on successful connection
        failed: Emitted with (error_type, message, details) on failure
    """

    connected = Signal()
    failed = Signal(str, str, str)  # error_type, message, details

    def __init__(self, connection_manager: ConnectionManagerService) -> None:
        super().__init__()
        self.connection_manager = connection_manager

    def run(self) -> None:
        """Attempt connection. Emits connected or failed."""
        try:
            result = self.connection_manager.connect()
            if result:
                self.connected.emit()
            else:
                self.failed.emit("connection", "Connection failed", "")
        except Exception as e:
            # Extract error type name for the UI to differentiate handling
            error_type = type(e).__name__
            message = getattr(e, "message", str(e))
            details = getattr(e, "details", "") or ""
            self.failed.emit(error_type, message, details)
