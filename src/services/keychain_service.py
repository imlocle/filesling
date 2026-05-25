"""
macOS Keychain integration for FileSling.

Stores and retrieves SSH passwords and passphrases securely
using the macOS Keychain via the `security` command-line tool.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from src.utils.constants import SOFTWARE_NAME
from src.utils.logging_signal import logger

SERVICE_NAME = SOFTWARE_NAME


def store_password(account: str, password: str) -> bool:
    """
    Store a password in the macOS Keychain.

    Args:
        account: Account identifier (e.g., "user@host" or server_id)
        password: The password/passphrase to store

    Returns:
        True if stored successfully
    """
    try:
        # Delete existing entry first (ignore errors if not found)
        subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-s",
                SERVICE_NAME,
                "-a",
                account,
            ],
            capture_output=True,
            timeout=5,
        )

        # Add new entry
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                SERVICE_NAME,
                "-a",
                account,
                "-w",
                password,
                "-U",  # Update if exists
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info(f"Keychain: Stored credentials for {account}")
            return True
        else:
            logger.warn(f"Keychain: Failed to store: {result.stderr.strip()}")
            return False
    except Exception as e:
        logger.warn(f"Keychain: Store failed: {e}")
        return False


def retrieve_password(account: str) -> Optional[str]:
    """
    Retrieve a password from the macOS Keychain.

    Args:
        account: Account identifier (e.g., "user@host" or server_id)

    Returns:
        The stored password, or None if not found
    """
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                SERVICE_NAME,
                "-a",
                account,
                "-w",  # Output password only
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception as e:
        logger.warn(f"Keychain: Retrieve failed: {e}")
        return None


def delete_password(account: str) -> bool:
    """
    Delete a password from the macOS Keychain.

    Args:
        account: Account identifier

    Returns:
        True if deleted successfully
    """
    try:
        result = subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-s",
                SERVICE_NAME,
                "-a",
                account,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warn(f"Keychain: Delete failed: {e}")
        return False


def has_stored_password(account: str) -> bool:
    """Check if a password exists in the keychain for this account."""
    return retrieve_password(account) is not None
