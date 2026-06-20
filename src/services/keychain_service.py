"""
macOS Keychain integration for FileSling.

Stores and retrieves SSH passwords and passphrases securely
using the macOS Keychain via the `security` command-line tool.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from src.utils.constants import SOFTWARE_NAME, TIMEOUT_KEYCHAIN
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
            timeout=TIMEOUT_KEYCHAIN,
        )

        # Add new entry — use stdin for the password to avoid it appearing
        # in `ps` output (security concern with -w flag on command line)
        proc = subprocess.Popen(
            [
                "security",
                "add-generic-password",
                "-s",
                SERVICE_NAME,
                "-a",
                account,
                "-w",
                "-U",  # Update if exists
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
            timeout=TIMEOUT_KEYCHAIN,
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
            timeout=TIMEOUT_KEYCHAIN,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warn(f"Keychain: Delete failed: {e}")
        return False


def has_stored_password(account: str) -> bool:
    """Check if a password exists in the keychain for this account."""
    return retrieve_password(account) is not None
