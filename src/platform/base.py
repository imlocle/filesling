"""
Platform abstraction — base (no-op stubs).

Used as fallback on unsupported platforms (e.g., Linux without desktop integration).
All functions are safe to call but do nothing.
"""

from __future__ import annotations

from typing import Optional

# =============================================================================
# Credential Storage
# =============================================================================


def store_credential(account: str, password: str) -> bool:
    """Store a credential. Returns True if successful."""
    return False


def get_credential(account: str) -> Optional[str]:
    """Retrieve a stored credential. Returns None if not found."""
    return None


def delete_credential(account: str) -> bool:
    """Delete a stored credential. Returns True if successful."""
    return False


def has_credential(account: str) -> bool:
    """Check if a credential exists for this account."""
    return False


# =============================================================================
# Notifications
# =============================================================================


def notify(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = False,
) -> None:
    """Send a desktop notification."""
    pass


def set_dock_badge(count: int) -> None:
    """Set the taskbar/dock badge count. Pass 0 to clear."""
    pass


# =============================================================================
# Sleep Inhibition
# =============================================================================


def inhibit_sleep() -> bool:
    """Prevent the system from sleeping. Returns True if successful."""
    return False


def release_sleep() -> None:
    """Allow the system to sleep again."""
    pass


def is_sleep_inhibited() -> bool:
    """Check if sleep is currently inhibited."""
    return False


# =============================================================================
# File Manager Integration
# =============================================================================


def reveal_in_file_manager(path: str) -> None:
    """Reveal a file in the system file manager (Finder/Explorer)."""
    pass
