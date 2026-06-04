"""
iOS device client for FileSling.

Provides access to iPhone/iPad camera roll and media files over USB using
Apple's AFC (Apple File Conduit) protocol via pymobiledevice3.

This client mimics the SFTPClient interface so the file explorer, transfer
workers, and download workers can use it without modification — same pattern
as ADBClient.

Requirements:
    pip install pymobiledevice3

The AFC service exposes the device's Media folder (jailed), which includes:
    /DCIM/          — Camera roll (all photos and videos)
    /PhotoData/     — Photo library metadata
    /Photos/        — Synced photos
    /Downloads/     — Safari downloads
    /iTunes_Control/ — Music (if synced via iTunes/Finder)

The user must unlock the device and tap "Trust This Computer" on first connect.
"""

from __future__ import annotations

import posixpath
import stat as stat_module
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.utils.logging_signal import logger

# Connection type constant
CONN_TYPE_IOS = "ios"


@dataclass
class IOSStat:
    """Stat result that mimics paramiko's SFTPAttributes."""

    filename: str = ""
    st_size: int = 0
    st_mode: int = 0
    st_atime: float = 0.0
    st_mtime: float = 0.0


def get_connected_ios_devices() -> List[dict]:
    """
    Detect connected iOS devices via USB.

    Returns:
        List of dicts with 'id' (UDID), 'name', and 'model' keys.
    """
    try:
        import asyncio

        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.usbmux import list_devices

        async def _list():
            return await list_devices()

        # Run the async list_devices in a new event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, can't use asyncio.run
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                devices = loop.run_in_executor(pool, asyncio.run, _list())
        except RuntimeError:
            devices = asyncio.run(_list())

        result = []
        for device in devices:
            try:
                lockdown = create_using_usbmux(serial=device.serial)
                name = lockdown.all_values.get("DeviceName", "iPhone")
                model = lockdown.all_values.get("ProductType", "")
                result.append(
                    {"id": device.serial, "name": name, "model": model}
                )
            except Exception:
                result.append(
                    {"id": device.serial, "name": "iOS Device", "model": ""}
                )
        return result
    except ImportError:
        logger.warn("iOS: pymobiledevice3 not installed")
        return []
    except Exception as e:
        logger.warn(f"iOS: Device detection failed: {e}")
        return []


class IOSClient:
    """
    iOS AFC client that mimics the SFTPClient interface.

    Provides: listdir, listdir_attr, stat, get, put, rename, mkdir, remove, rmdir.
    All paths are relative to the AFC Media root (/).
    """

    def __init__(self, device_udid: Optional[str] = None) -> None:
        self._udid = device_udid
        self._afc = None
        self._connect()

    def _connect(self) -> None:
        """Establish AFC connection to the device."""
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.afc import AfcService

            if self._udid:
                lockdown = create_using_usbmux(serial=self._udid)
            else:
                lockdown = create_using_usbmux()

            self._afc = AfcService(lockdown=lockdown)
            logger.info("iOS: AFC connection established")
        except ImportError:
            raise IOError(
                "pymobiledevice3 is required for iOS support. "
                "Install it with: pip install pymobiledevice3"
            )
        except Exception as e:
            raise IOError(f"iOS: Failed to connect: {e}")

    def _ensure_connected(self) -> None:
        """Verify the AFC connection is alive."""
        if self._afc is None:
            raise IOError("iOS: Not connected")

    def listdir(self, path: str) -> List[str]:
        """List directory contents (filenames only)."""
        self._ensure_connected()
        try:
            entries = self._afc.listdir(path)
            # Filter out . and ..
            return [e for e in entries if e not in (".", "..")]
        except Exception as e:
            raise IOError(f"iOS: Failed to list {path}: {e}")

    def listdir_attr(self, path: str) -> List[IOSStat]:
        """List directory with stat info for each entry."""
        self._ensure_connected()
        results = []
        try:
            entries = self.listdir(path)
            for entry in entries:
                full_path = posixpath.join(path, entry)
                try:
                    st = self.stat(full_path)
                    st.filename = entry
                    results.append(st)
                except (IOError, OSError):
                    # Skip entries we can't stat
                    results.append(
                        IOSStat(
                            filename=entry,
                            st_size=0,
                            st_mode=stat_module.S_IFREG | 0o644,
                        )
                    )
            return results
        except Exception as e:
            raise IOError(f"iOS: Failed to list {path}: {e}")

    def stat(self, path: str) -> IOSStat:
        """Get file/directory info."""
        self._ensure_connected()
        try:
            info = self._afc.stat(path)
            # pymobiledevice3 returns a dict with st_ifmt, st_size, etc.
            size = int(info.get("st_size", 0))
            ifmt = info.get("st_ifmt", "")

            if ifmt == "S_IFDIR":
                mode = stat_module.S_IFDIR | 0o755
            else:
                mode = stat_module.S_IFREG | 0o644

            mtime = float(info.get("st_mtime", 0)) / 1e9  # nanoseconds → seconds

            return IOSStat(
                st_size=size,
                st_mode=mode,
                st_mtime=mtime,
            )
        except Exception as e:
            raise IOError(f"iOS: Failed to stat {path}: {e}")

    def get(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable] = None,
    ) -> None:
        """Download a file from the device."""
        self._ensure_connected()
        try:
            data = self._afc.get_file_contents(remote_path)
            with open(local_path, "wb") as f:
                f.write(data)
            if callback:
                callback(len(data), len(data))
        except Exception as e:
            raise IOError(f"iOS: Failed to download {remote_path}: {e}")

    def put(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable] = None,
    ) -> None:
        """Upload a file to the device."""
        self._ensure_connected()
        try:
            with open(local_path, "rb") as f:
                data = f.read()
            self._afc.set_file_contents(remote_path, data)
            if callback:
                callback(len(data), len(data))
        except Exception as e:
            raise IOError(f"iOS: Failed to upload to {remote_path}: {e}")

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename/move a file or directory."""
        self._ensure_connected()
        try:
            self._afc.rename(old_path, new_path)
        except Exception as e:
            raise IOError(f"iOS: Failed to rename {old_path}: {e}")

    def mkdir(self, path: str) -> None:
        """Create a directory."""
        self._ensure_connected()
        try:
            self._afc.makedirs(path)
        except Exception as e:
            raise IOError(f"iOS: Failed to create directory {path}: {e}")

    def remove(self, path: str) -> None:
        """Remove a file."""
        self._ensure_connected()
        try:
            self._afc.rm(path)
        except Exception as e:
            raise IOError(f"iOS: Failed to remove {path}: {e}")

    def rmdir(self, path: str) -> None:
        """Remove a directory (recursively)."""
        self._ensure_connected()
        try:
            self._afc.rm(path, force=True)
        except Exception as e:
            raise IOError(f"iOS: Failed to remove directory {path}: {e}")

    def close(self) -> None:
        """Close the AFC connection."""
        if self._afc:
            try:
                self._afc.close()
            except Exception:
                pass
            self._afc = None
