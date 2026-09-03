"""
Remote file service — centralizes connection-lost detection for remote operations.

Every caller currently does its own try/except for IOError("Socket is closed").
This service provides a single place to handle that pattern.
"""

from __future__ import annotations

from typing import Any, List

from src.models.errors import ConnectionLostError


def is_connection_lost_error(error: Exception) -> bool:
    """Check if an exception indicates a lost connection."""
    msg = str(error).lower()
    return (
        "socket is closed" in msg
        or "not open" in msg
        or ("no such file" in msg and "socket" in msg)
        or ("eof" in msg and "transport" in msg)
    )


def safe_stat(sftp: Any, path: str) -> Any:
    """
    Stat a remote path, raising ConnectionLostError on dead socket.

    Returns the stat result or raises ConnectionLostError / IOError.
    """
    try:
        return sftp.stat(path)
    except IOError as e:
        if is_connection_lost_error(e):
            raise ConnectionLostError("Connection lost during stat", details=str(e))
        raise


def safe_listdir_attr(sftp: Any, path: str) -> List[Any]:
    """
    List directory with attributes, raising ConnectionLostError on dead socket.
    """
    try:
        return sftp.listdir_attr(path)
    except IOError as e:
        if is_connection_lost_error(e):
            raise ConnectionLostError(
                "Connection lost during directory listing", details=str(e)
            )
        raise


def safe_rename(sftp: Any, old_path: str, new_path: str) -> None:
    """Rename with connection-lost detection."""
    try:
        sftp.rename(old_path, new_path)
    except IOError as e:
        if is_connection_lost_error(e):
            raise ConnectionLostError("Connection lost during rename", details=str(e))
        raise


def safe_remove(sftp: Any, path: str) -> None:
    """Remove file with connection-lost detection."""
    try:
        sftp.remove(path)
    except IOError as e:
        if is_connection_lost_error(e):
            raise ConnectionLostError(
                "Connection lost during file removal", details=str(e)
            )
        raise


def safe_rmdir(sftp: Any, path: str) -> None:
    """Remove directory with connection-lost detection."""
    try:
        sftp.rmdir(path)
    except IOError as e:
        if is_connection_lost_error(e):
            raise ConnectionLostError(
                "Connection lost during directory removal", details=str(e)
            )
        raise


def safe_mkdir(sftp: Any, path: str) -> None:
    """Create directory with connection-lost detection."""
    try:
        sftp.mkdir(path)
    except IOError as e:
        if is_connection_lost_error(e):
            raise ConnectionLostError(
                "Connection lost during directory creation", details=str(e)
            )
        raise
