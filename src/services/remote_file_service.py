"""
Remote file service: centralizes connection-lost detection for remote operations.

Every caller currently does its own try/except for IOError("Socket is closed").
This service provides a single place to handle that pattern.
"""

from __future__ import annotations

from typing import Any, Callable, List, TypeVar

from src.models.errors import ConnectionLostError

Result = TypeVar("Result")


def is_connection_lost_error(error: Exception) -> bool:
    """Check if an exception indicates a lost connection."""
    msg = str(error).lower()
    return (
        "socket is closed" in msg
        or "not open" in msg
        or ("no such file" in msg and "socket" in msg)
        or ("eof" in msg and "transport" in msg)
    )


def _run_sftp_operation(
    operation_name: str, operation: Callable[..., Result], *args: Any
) -> Result:
    """Run an SFTP method and normalize errors caused by a dropped connection."""
    try:
        return operation(*args)
    except IOError as error:
        if is_connection_lost_error(error):
            raise ConnectionLostError(
                f"Connection lost during {operation_name}", details=str(error)
            ) from error
        raise


def safe_stat(sftp: Any, path: str) -> Any:
    """
    Stat a remote path, raising ConnectionLostError on dead socket.

    Returns the stat result or raises ConnectionLostError / IOError.
    """
    return _run_sftp_operation("stat", sftp.stat, path)


def safe_listdir_attr(sftp: Any, path: str) -> List[Any]:
    """
    List directory with attributes, raising ConnectionLostError on dead socket.
    """
    return _run_sftp_operation("directory listing", sftp.listdir_attr, path)


def safe_rename(sftp: Any, old_path: str, new_path: str) -> None:
    """Rename with connection-lost detection."""
    _run_sftp_operation("rename", sftp.rename, old_path, new_path)


def safe_remove(sftp: Any, path: str) -> None:
    """Remove file with connection-lost detection."""
    _run_sftp_operation("file removal", sftp.remove, path)


def safe_rmdir(sftp: Any, path: str) -> None:
    """Remove directory with connection-lost detection."""
    _run_sftp_operation("directory removal", sftp.rmdir, path)


def safe_mkdir(sftp: Any, path: str) -> None:
    """Create directory with connection-lost detection."""
    _run_sftp_operation("directory creation", sftp.mkdir, path)
