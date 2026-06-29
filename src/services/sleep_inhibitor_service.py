"""
Sleep inhibitor service — prevents macOS from sleeping during active transfers.

Uses the macOS `caffeinate` command to hold an idle sleep assertion.
The assertion is automatically released when the subprocess is killed
or when the app exits (child process cleanup).
"""

from __future__ import annotations

import subprocess
from typing import Optional

from src.utils.logging_signal import logger


class SleepInhibitorService:
    """
    Manages a macOS sleep inhibition assertion via caffeinate.

    Usage:
        inhibitor = SleepInhibitorService()
        inhibitor.acquire()   # Prevent sleep
        inhibitor.release()   # Allow sleep again

    Safe to call acquire() multiple times — only one caffeinate process runs.
    Safe to call release() when not acquired — no-op.
    """

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None

    @property
    def is_active(self) -> bool:
        """True if sleep is currently inhibited."""
        if self._process is None:
            return False
        # Check if process is still running
        return self._process.poll() is None

    def acquire(self) -> None:
        """Prevent idle sleep. No-op if already acquired."""
        if self.is_active:
            return

        try:
            self._process = subprocess.Popen(
                ["caffeinate", "-i"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Sleep inhibitor: Acquired (preventing idle sleep)")
        except FileNotFoundError:
            # caffeinate not available (non-macOS or stripped system)
            logger.warn("Sleep inhibitor: caffeinate not found")
        except Exception as e:
            logger.warn(f"Sleep inhibitor: Failed to acquire: {e}")

    def release(self) -> None:
        """Allow sleep again. No-op if not acquired."""
        if self._process is None:
            return

        try:
            self._process.terminate()
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        except Exception:
            pass

        self._process = None
        logger.info("Sleep inhibitor: Released (sleep allowed)")

    def __del__(self) -> None:
        """Ensure caffeinate is killed if this object is garbage collected."""
        self.release()
