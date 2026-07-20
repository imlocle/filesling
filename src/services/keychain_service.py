"""
Credential storage service for FileSling.

Stores and retrieves SSH passwords and passphrases securely
using the platform's native credential manager (macOS Keychain,
Windows Credential Manager, etc.) via the src.platform abstraction.
"""

from __future__ import annotations

from typing import Optional

from src.platform import (
    delete_credential,
    get_credential,
    has_credential,
    store_credential,
)


def store_password(account: str, password: str) -> bool:
    """
    Store a password in the platform's credential manager.

    Args:
        account: Account identifier (e.g., "user@host" or server_id)
        password: The password/passphrase to store

    Returns:
        True if stored successfully
    """
    return store_credential(account, password)


def retrieve_password(account: str) -> Optional[str]:
    """
    Retrieve a password from the platform's credential manager.

    Args:
        account: Account identifier (e.g., "user@host" or server_id)

    Returns:
        The stored password, or None if not found
    """
    return get_credential(account)


def delete_password(account: str) -> bool:
    """
    Delete a password from the platform's credential manager.

    Args:
        account: Account identifier

    Returns:
        True if deleted successfully
    """
    return delete_credential(account)


def has_stored_password(account: str) -> bool:
    """Check if a password exists for this account."""
    return has_credential(account)
