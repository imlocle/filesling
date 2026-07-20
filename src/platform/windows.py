"""
Platform abstraction — Windows implementation.

Uses:
- `keyring` library for Windows Credential Manager
- `QSystemTrayIcon.showMessage()` for toast notifications
- `SetThreadExecutionState` Win32 API for sleep prevention
- `explorer /select,` for Explorer reveal
- Qt's setOverlayIcon or setBadgeNumber for taskbar badge
"""

from __future__ import annotations

import subprocess
from typing import Optional

from src.utils.constants import SOFTWARE_NAME
from src.utils.logging_signal import logger

_SERVICE_NAME = SOFTWARE_NAME

# Track sleep inhibition state
_sleep_inhibited: bool = False


# =============================================================================
# Credential Storage (Windows Credential Manager via `keyring`)
# =============================================================================


def store_credential(account: str, password: str) -> bool:
    """Store a password in the Windows Credential Manager."""
    try:
        import keyring

        keyring.set_password(_SERVICE_NAME, account, password)
        logger.info(f"Credentials: Stored for {account}")
        return True
    except ImportError:
        logger.warn("Credentials: `keyring` package not installed")
        return False
    except Exception as e:
        logger.warn(f"Credentials: Store failed: {e}")
        return False


def get_credential(account: str) -> Optional[str]:
    """Retrieve a password from the Windows Credential Manager."""
    try:
        import keyring

        return keyring.get_password(_SERVICE_NAME, account)
    except ImportError:
        logger.warn("Credentials: `keyring` package not installed")
        return None
    except Exception as e:
        logger.warn(f"Credentials: Retrieve failed: {e}")
        return None


def delete_credential(account: str) -> bool:
    """Delete a password from the Windows Credential Manager."""
    try:
        import keyring

        keyring.delete_password(_SERVICE_NAME, account)
        return True
    except ImportError:
        logger.warn("Credentials: `keyring` package not installed")
        return False
    except Exception as e:
        logger.warn(f"Credentials: Delete failed: {e}")
        return False


def has_credential(account: str) -> bool:
    """Check if a credential exists for this account."""
    return get_credential(account) is not None


# =============================================================================
# Notifications (Windows via Qt system tray or win11toast)
# =============================================================================


def notify(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = False,
) -> None:
    """Send a Windows notification via QSystemTrayIcon."""
    try:
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon

        app = QApplication.instance()
        if app:
            # Find the tray icon instance
            for widget in app.allWidgets():
                tray = widget.findChild(QSystemTrayIcon)
                if tray:
                    full_message = message
                    if subtitle:
                        full_message = f"{subtitle}\n{message}"
                    tray.showMessage(
                        title, full_message, QSystemTrayIcon.Information, 5000
                    )
                    return

        # Fallback: try win11toast if available
        try:
            from win11toast import notify as win_notify

            win_notify(title=title, body=message)
        except ImportError:
            pass
    except Exception as e:
        logger.warn(f"Notification: Failed to send: {e}")


def set_dock_badge(count: int) -> None:
    """Set the Windows taskbar badge. Pass 0 to clear."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            # Qt 6.5+ has setBadgeNumber on Windows too
            app.setBadgeNumber(count)  # type: ignore
    except (AttributeError, TypeError):
        # setBadgeNumber not available on this Qt version
        pass
    except Exception:
        pass


# =============================================================================
# Sleep Inhibition (Windows via SetThreadExecutionState)
# =============================================================================

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def inhibit_sleep() -> bool:
    """Prevent system sleep via SetThreadExecutionState."""
    global _sleep_inhibited

    if _sleep_inhibited:
        return True

    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        )
        _sleep_inhibited = True
        logger.info("Sleep inhibitor: Acquired (preventing system sleep)")
        return True
    except Exception as e:
        logger.warn(f"Sleep inhibitor: Failed to acquire: {e}")
        return False


def release_sleep() -> None:
    """Allow system sleep again."""
    global _sleep_inhibited

    if not _sleep_inhibited:
        return

    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        _sleep_inhibited = False
        logger.info("Sleep inhibitor: Released (sleep allowed)")
    except Exception:
        pass


def is_sleep_inhibited() -> bool:
    """Check if sleep is currently inhibited."""
    return _sleep_inhibited


# =============================================================================
# File Manager Integration (Windows Explorer)
# =============================================================================


def reveal_in_file_manager(path: str) -> None:
    """Reveal a file in Windows Explorer."""
    try:
        # Normalize path separators for Windows
        path = path.replace("/", "\\")
        subprocess.run(["explorer", "/select,", path], check=False)
    except Exception:
        pass
