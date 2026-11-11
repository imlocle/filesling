"""Background worker for running a remote ffmpeg quick fix."""

from __future__ import annotations

from paramiko import Transport
from PySide6.QtCore import QObject, Signal

from src.clients.ssh_command_client import open_ssh_session

class QuickFixWorker(QObject):
    """Run a prepared remote command without blocking the UI thread."""

    done = Signal()

    def __init__(self, transport: Transport, command: str) -> None:
        super().__init__()
        self._transport = transport
        self._command = command
        self.exit_code = -1
        self.error_msg = ""

    def run(self) -> None:
        try:
            with open_ssh_session(self._transport, self._command) as session:
                self.exit_code = session.recv_exit_status()
        except Exception as error:
            self.error_msg = str(error)
        finally:
            self.done.emit()
