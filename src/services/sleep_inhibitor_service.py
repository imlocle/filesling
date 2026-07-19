"""
Sleep inhibitor service — prevents the system from sleeping during active transfers.

Uses the src.platform abstraction for cross-platform support:
- macOS: caffeinate subprocess
- Windows: SetThreadExecutionState Win32 API
"""

from __future__ import annotations

from src.platform import inhibit_sleep, is_sleep_inhibited, release_sleep


class SleepInhibitorService:
    """
    Manages system sleep inhibition.

    Usage:
        inhibitor = SleepInhibitorService()
        inhibitor.acquire()   # Prevent sleep
        inhibitor.release()   # Allow sleep again

    Safe to call acquire() multiple times — only acquires once.
    Safe to call release() when not acquired — no-op.
    """

    @property
    def is_active(self) -> bool:
        """True if sleep is currently inhibited."""
        return is_sleep_inhibited()

    def acquire(self) -> None:
        """Prevent system sleep. No-op if already acquired."""
        inhibit_sleep()

    def release(self) -> None:
        """Allow sleep again. No-op if not acquired."""
        release_sleep()

    def __del__(self) -> None:
        """Ensure sleep inhibition is released if this object is garbage collected."""
        self.release()
