"""
macOS notification service for FileSling.

Sends native macOS notifications when transfers complete, fail, etc.
Uses osascript (AppleScript) for reliable delivery without extra dependencies.
"""

from __future__ import annotations

import subprocess
from typing import Optional

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
        script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
        if subtitle:
            script += f' subtitle "{_escape(subtitle)}"'
        if sound:
            script += ' sound name "default"'

        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        logger.warn("Notification: osascript timed out")
    except Exception as e:
        logger.warn(f"Notification: Failed to send: {e}")


def notify_transfer_complete(filename: str, action: str = "uploaded") -> None:
    """Send notification for a completed transfer."""
    notify(
        title="FileSling",
        message=f"{filename} {action} successfully",
        sound=True,
    )


def notify_transfer_failed(filename: str, error: str = "") -> None:
    """Send notification for a failed transfer."""
    message = f"{filename} transfer failed"
    if error:
        message += f": {error[:60]}"
    notify(
        title="FileSling",
        message=message,
    )


def notify_batch_complete(count: int, action: str = "downloaded") -> None:
    """Send notification for a batch of completed transfers."""
    notify(
        title="FileSling",
        message=f"{count} files {action} successfully",
        sound=True,
    )


def _escape(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
