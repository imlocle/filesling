"""
rsync transfer service for FileSling.

Provides fast, delta-based file transfers over SSH using the system `rsync`
binary. rsync only sends the changed parts of files, making re-transfers of
large files dramatically faster than a full SFTP re-upload.

This is used as an optional fast path for SSH key-based connections. When
rsync is unavailable (not installed, password auth, or non-SSH backend), the
caller falls back to the SFTP transfer worker.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.utils.logging_signal import logger

# rsync progress lines look like:
#   1,234,567  45%   1.23MB/s    0:00:12
_PROGRESS_RE = re.compile(r"(\d+)%")


@dataclass
class RsyncConfig:
    """SSH connection details needed to build an rsync command."""

    host: str
    username: str
    ssh_key_path: str
    ssh_port: int = 22


def is_rsync_available() -> bool:
    """Return True if the rsync binary is available on this machine."""
    return shutil.which("rsync") is not None


def _build_ssh_option(config: RsyncConfig) -> str:
    """Build the -e ssh option string with key and port."""
    key = os.path.expanduser(config.ssh_key_path)
    # BatchMode avoids interactive prompts; StrictHostKeyChecking=accept-new
    # matches the app's AutoAddPolicy behavior without failing on first connect.
    parts = [
        "ssh",
        "-p",
        str(config.ssh_port),
        "-i",
        key,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    return " ".join(parts)


def _remote_spec(config: RsyncConfig, remote_path: str) -> str:
    """Build the user@host:path destination spec for rsync.

    The remote path is wrapped in quotes to handle shell special characters
    (spaces, parentheses, brackets, etc.) since rsync passes it through
    a remote shell invocation.
    """
    # Single-quote the path to protect all special characters from the remote shell.
    # Escape any single quotes within the path itself.
    safe_path = remote_path.replace("'", "'\\''")
    return f"{config.username}@{config.host}:'{safe_path}'"


class RsyncTransfer:
    """
    Runs a single rsync transfer as a subprocess and reports progress.

    Designed to be driven from a background thread (the TransferWorker).
    """

    def __init__(
        self,
        config: RsyncConfig,
        local_paths: List[str],
        remote_dir: str,
    ) -> None:
        self.config = config
        self.local_paths = local_paths
        self.remote_dir = remote_dir
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    def _build_command(self) -> List[str]:
        """Build the full rsync argument list."""
        ssh_opt = _build_ssh_option(self.config)

        # -a: archive (recursive, preserve timestamps/perms)
        # --partial: keep partially transferred files for resume
        # --progress: per-file progress (compatible with openrsync + GNU rsync)
        # NOTE: no -z (compression) — on local networks it slows things down
        # by adding CPU overhead without meaningful size reduction for media files.
        cmd = [
            "rsync",
            "-a",
            "--partial",
            "--progress",
            "-e",
            ssh_opt,
        ]

        # Ensure remote dir has a trailing slash so files land inside it
        remote_dir = self.remote_dir
        if not remote_dir.endswith("/"):
            remote_dir += "/"

        # Strip trailing slashes from local paths — rsync treats
        # "folder/" as "copy contents of folder" vs "folder" as "copy the folder"
        # NOTE: brackets [] in local paths are safe because we pass args as a list
        # (not through shell). rsync only interprets wildcards in filter patterns.
        clean_paths = [p.rstrip("/") for p in self.local_paths]
        cmd.extend(clean_paths)
        cmd.append(_remote_spec(self.config, remote_dir))
        return cmd

    def run(self, progress_cb: Optional[Callable[[int], None]] = None) -> None:
        """
        Execute the rsync transfer.

        Args:
            progress_cb: Optional callback receiving overall percentage (0-100)

        Raises:
            RuntimeError: If rsync exits with a non-zero status
        """
        cmd = self._build_command()
        logger.info(f"rsync: {' '.join(self.local_paths)} → {self.remote_dir}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                # rsync uses carriage returns to update progress in place;
                # universal newlines splits on \r too.
                universal_newlines=True,
            )
        except FileNotFoundError:
            raise RuntimeError("rsync binary not found")
        except Exception as e:
            raise RuntimeError(f"Failed to start rsync: {e}")

        # Read progress from stdout line by line
        # --progress outputs per-file lines like: "1,234,567  45%  1.23MB/s  0:00:12"
        assert self._process.stdout is not None
        stdout_lines = []
        for line in self._process.stdout:
            stdout_lines.append(line)
            if self._cancelled:
                break
            match = _PROGRESS_RE.search(line)
            if match and progress_cb:
                pct = int(match.group(1))
                progress_cb(min(pct, 100))

        self._process.wait()

        if self._cancelled:
            raise RuntimeError("Transfer cancelled")

        if self._process.returncode != 0:
            stderr = ""
            if self._process.stderr is not None:
                stderr = self._process.stderr.read().strip()
            raise RuntimeError(
                f"rsync failed (exit {self._process.returncode}): {stderr}"
            )

        if progress_cb:
            progress_cb(100)

    def cancel(self) -> None:
        """Cancel the running rsync process."""
        self._cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
