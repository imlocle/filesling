"""
Notification service for FileSling.

Sends native desktop notifications when transfers complete, fail, etc.
Also manages the taskbar/dock badge for pending transfer count.

Uses the src.platform abstraction for cross-platform support.
"""

from __future__ import annotations

from typing import Optional

from src.platform import notify as _platform_notify
from src.platform import set_dock_badge as _platform_set_dock_badge
from src.utils.constants import SOFTWARE_NAME


def notify(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = False,
) -> None:
    """
    Send a desktop notification.

    Args:
        title: Notification title (e.g. "FileSling")
        message: Main notification body
        subtitle: Optional subtitle line
        sound: Whether to play the default notification sound
    """
    _platform_notify(title=title, message=message, subtitle=subtitle, sound=sound)


def notify_transfer_complete(
    filename: str, action: str = "uploaded", sound: bool = True
) -> None:
    """Send notification for a completed transfer."""
    notify(
        title=SOFTWARE_NAME,
        message=f"{filename} {action} successfully",
        sound=sound,
    )


def notify_transfer_failed(filename: str, error: str = "") -> None:
    """Send notification for a failed transfer."""
    message = f"{filename} transfer failed"
    if error:
        message += f": {error[:60]}"
    notify(
        title=SOFTWARE_NAME,
        message=message,
    )


def notify_batch_complete(
    count: int, action: str = "downloaded", sound: bool = True
) -> None:
    """Send notification for a batch of completed transfers."""
    notify(
        title=SOFTWARE_NAME,
        message=f"{count} files {action} successfully",
        sound=sound,
    )


def set_dock_badge(count: int) -> None:
    """
    Set the taskbar/dock icon badge to show pending transfer count.
    Pass 0 to clear the badge.
    """
    _platform_set_dock_badge(count)
