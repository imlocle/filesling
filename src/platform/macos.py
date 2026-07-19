"""
Platform abstraction — macOS implementation.

Uses:
- `security` CLI for Keychain credential storage
- `osascript` for native notifications
- `caffeinate` for sleep prevention
- `open -R` for Finder reveal
- Qt's setBadgeNumber for Dock badge
"""

from __future__ import annotations

import subprocess
from typing import Optional

from src.utils.constants import SOFTWARE_NAME, TIMEOUT_KEYCHAIN, TIMEOUT_NOTIFICATION
from src.utils.logging_signal import logger

_SERVICE_NAME = SOFTWARE_NAME

# Track caffeinate process for sleep inhibition
_caffeinate_process: Optional[subprocess.Popen] = None


# =============================================================================
# Credential Storage (macOS Keychain via `security` CLI)
# =============================================================================


def store_credential(account: str, password: str) -> bool:
    """Store a password in the macOS Keychain."""
    try:
        # Delete existing entry first (ignore errors if not found)
        subprocess.run(
            ["security", "delete-generic-password", "-s", _SERVICE_NAME, "-a", account],
            capture_output=True,
            timeout=TIMEOUT_KEYCHAIN,
        )

        # Add new entry — password via stdin to avoid ps visibility
        proc = subprocess.Popen(
            [
                "security",
                "add-generic-password",
                "-s",
                _SERVICE_NAME,
                "-a",
                account,
                "-w",
                "-U",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _, stderr = proc.communicate(input=password, timeout=TIMEOUT_KEYCHAIN)
        if proc.returncode == 0:
            logger.info(f"Keychain: Stored credentials for {account}")
            return True
        else:
            logger.warn(f"Keychain: Failed to store: {stderr.strip()}")
            return False
    except Exception as e:
        logger.warn(f"Keychain: Store failed: {e}")
        return False


def get_credential(account: str) -> Optional[str]:
    """Retrieve a password from the macOS Keychain."""
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _SERVICE_NAME,
                "-a",
                account,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_KEYCHAIN,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception as e:
        logger.warn(f"Keychain: Retrieve failed: {e}")
        return None


def delete_credential(account: str) -> bool:
    """Delete a password from the macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "delete-generic-password", "-s", _SERVICE_NAME, "-a", account],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_KEYCHAIN,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warn(f"Keychain: Delete failed: {e}")
        return False


def has_credential(account: str) -> bool:
    """Check if a password exists in the keychain for this account."""
    return get_credential(account) is not None


# =============================================================================
# Notifications (macOS via osascript)
# =============================================================================


def notify(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = False,
) -> None:
    """Send a macOS notification via osascript."""
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


def set_dock_badge(count: int) -> None:
    """Set the macOS Dock icon badge count. Pass 0 to clear."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.setBadgeNumber(count)  # type: ignore
    except (AttributeError, TypeError):
        pass
    except Exception as e:
        logger.warn(f"Notification: Badge update failed: {e}")


def _escape(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


# =============================================================================
# Sleep Inhibition (macOS via caffeinate)
# =============================================================================


def inhibit_sleep() -> bool:
    """Prevent idle sleep via caffeinate. Returns True if successful."""
    global _caffeinate_process

    if is_sleep_inhibited():
        return True

    try:
        _caffeinate_process = subprocess.Popen(
            ["caffeinate", "-i"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Sleep inhibitor: Acquired (preventing idle sleep)")
        return True
    except FileNotFoundError:
        logger.warn("Sleep inhibitor: caffeinate not found")
        return False
    except Exception as e:
        logger.warn(f"Sleep inhibitor: Failed to acquire: {e}")
        return False


def release_sleep() -> None:
    """Allow sleep again by terminating caffeinate."""
    global _caffeinate_process

    if _caffeinate_process is None:
        return

    try:
        _caffeinate_process.terminate()
        _caffeinate_process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _caffeinate_process.kill()
    except Exception:
        pass

    _caffeinate_process = None
    logger.info("Sleep inhibitor: Released (sleep allowed)")


def is_sleep_inhibited() -> bool:
    """Check if caffeinate is currently running."""
    if _caffeinate_process is None:
        return False
    return _caffeinate_process.poll() is None


# =============================================================================
# File Manager Integration (macOS Finder)
# =============================================================================


def reveal_in_file_manager(path: str) -> None:
    """Reveal a file in Finder."""
    try:
        subprocess.run(["open", "-R", path], check=False)
    except Exception:
        pass
