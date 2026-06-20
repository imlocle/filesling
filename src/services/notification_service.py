"""
macOS notification service for FileSling.

Sends native macOS notifications when transfers complete, fail, etc.
Uses osascript (AppleScript) for reliable delivery without extra dependencies.
Also manages the Dock badge for pending transfer count.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from src.utils.constants import SOFTWARE_NAME, TIMEOUT_NOTIFICATION
from src.utils.logging_signal import logger


def notify(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = False,
) -> None:
    """
    Send a macOS notification via osascript.

    Args:
        title: Notification title (e.g. "FileSling")
        message: Main notification body
        subtitle: Optional subtitle line
        sound: Whether to play the default notification sound
    """
    try:
        script = (
            f'display notification "{_escape(message)}" '
            f'with title "{_escape(title)}"'
        )
        if subtitle:
            script += f' subtitle "{_escape(subtitle)}"'
        if sound:
            script += ' sound name "default"'

        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=TIMEOUT_NOTIFICATION,
        )
    except subprocess.TimeoutExpired:
        logger.warn("Notification: osascript timed out")
    except Exception as e:
        logger.warn(f"Notification: Failed to send: {e}")


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
    Set the Dock icon badge to show pending transfer count.
    Pass 0 to clear the badge.
    """
    try:
        _set_badge_via_qt(count)
    except Exception as e:
        logger.warn(f"Notification: Badge update failed: {e}")


def _set_badge_via_qt(count: int) -> None:
    """Set dock badge using Qt's macOS integration."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            if count > 0:
                app.setBadgeNumber(count)  # type: ignore
            else:
                app.setBadgeNumber(0)  # type: ignore
    except (AttributeError, TypeError):
        # setBadgeNumber may not be available on older Qt versions
        pass


def _escape(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
