"""
DeviceClient protocol — defines the interface for all device backends.

SFTPClient (Paramiko), ADBClient, and IOSClient all implement this interface.
Using a Protocol allows type-safe duck typing without requiring inheritance.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class DeviceClient(Protocol):
    """
    Protocol defining the file operations interface for remote devices.

    Implementations:
    - paramiko.SFTPClient (SSH/SFTP)
    - src.services.adb_client.ADBClient (Android via USB/WiFi)
    - src.services.ios_client.IOSClient (iPhone/iPad via USB)
    """

    def listdir(self, path: str) -> List[str]:
        """List directory contents (filenames only)."""
        ...

    def listdir_attr(self, path: str) -> List[Any]:
        """List directory with stat attributes for each entry."""
        ...

    def stat(self, path: str) -> Any:
        """Get file/directory info. Returns an object with st_mode and st_size."""
        ...

    def get(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable] = None,
    ) -> None:
        """Download a file from the device to local filesystem."""
        ...

    def put(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable] = None,
    ) -> None:
        """Upload a file from local filesystem to the device."""
        ...

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename or move a file/directory."""
        ...

    def remove(self, path: str) -> None:
        """Delete a file."""
        ...

    def rmdir(self, path: str) -> None:
        """Delete a directory (may be recursive depending on implementation)."""
        ...

    def mkdir(self, path: str) -> None:
        """Create a directory."""
        ...

    def close(self) -> None:
        """Close the connection/session."""
        ...
