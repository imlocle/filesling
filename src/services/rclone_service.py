"""Optional rclone SFTP fast path for bulk uploads."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from src.utils.logging_signal import logger

_PROGRESS_RE = re.compile(r"(\d+(?:\.\d+)?)%")


@dataclass(frozen=True)
class RcloneConfig:
    """SSH details needed to use rclone's SFTP backend."""

    host: str
    username: str
    ssh_key_path: str
    ssh_port: int
    known_hosts_path: str


def is_rclone_available() -> bool:
    """Return whether the rclone executable is available on this machine."""
    return shutil.which("rclone") is not None


class RcloneTransfer:
    """Run one copy operation through rclone and report its progress."""

    def __init__(self, config: RcloneConfig) -> None:
        self.config = config
        self._process: Optional[subprocess.Popen[str]] = None
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        """Whether the transfer was explicitly cancelled by the user."""
        return self._cancelled

    def _build_command(
        self, local_path: str, remote_path: str, *, is_directory: bool
    ) -> list[str]:
        command = ["rclone", "copy" if is_directory else "copyto"]
        command.extend(
            [
                "--transfers",
                "4",
                "--checksum",
                "--create-empty-src-dirs",
                "--progress",
                "--stats",
                "1s",
                "--stats-one-line",
                "--sftp-host",
                self.config.host,
                "--sftp-user",
                self.config.username,
                "--sftp-port",
                str(self.config.ssh_port),
                "--sftp-key-file",
                os.path.expanduser(self.config.ssh_key_path),
                "--sftp-known-hosts-file",
                os.path.expanduser(self.config.known_hosts_path),
                local_path,
                f":sftp:{remote_path}",
            ]
        )
        return command

    def run(
        self,
        local_path: str,
        remote_path: str,
        progress_cb: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Copy a file or directory, raising when rclone cannot complete it."""
        command = self._build_command(
            local_path, remote_path, is_directory=os.path.isdir(local_path)
        )
        logger.info(f"rclone: Uploading {os.path.basename(local_path.rstrip('/\\'))}")
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError("rclone binary not found") from error
        except OSError as error:
            raise RuntimeError(f"Failed to start rclone: {error}") from error

        output_lines: list[str] = []
        if self._process.stdout is not None:
            for line in self._process.stdout:
                output_lines.append(line.rstrip())
                if self._cancelled:
                    break
                match = _PROGRESS_RE.search(line)
                if match and progress_cb:
                    progress_cb(min(int(float(match.group(1))), 100))

        if self._cancelled:
            self.cancel()
            raise RuntimeError("rclone transfer cancelled")

        return_code = self._process.wait()
        if return_code != 0:
            details = "\n".join(output_lines[-12:]).strip()
            raise RuntimeError(
                f"rclone exited with code {return_code}"
                + (f": {details}" if details else "")
            )
        if progress_cb:
            progress_cb(100)

    def cancel(self) -> None:
        """Stop an active rclone subprocess."""
        self._cancelled = True
        process = self._process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
