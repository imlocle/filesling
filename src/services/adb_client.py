"""
ADB client that mimics the Paramiko SFTPClient interface.

This allows the FileExplorerWidget to work with Android devices
connected via USB without any changes to the explorer code.

Requires: `adb` installed (brew install android-platform-tools)
and USB Debugging enabled on the Android device.
"""

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from stat import S_IFDIR, S_IFREG, S_ISDIR
from typing import Callable, Generator, List, Optional


@dataclass
class ADBStat:
    """Mimics paramiko's SFTPAttributes."""

    st_mode: int
    st_size: int
    filename: str = ""


class ADBClient:
    """
    ADB-based file client that implements the same interface as Paramiko's SFTPClient.

    The FileExplorerWidget calls methods like listdir(), stat(), rename(), etc.
    This class translates those into `adb shell` commands.
    """

    def __init__(self, device_id: Optional[str] = None) -> None:
        """
        Initialize ADB client.

        Args:
            device_id: Specific device serial (from `adb devices`).
                      If None, uses the only connected device.
        """
        self.device_id = device_id
        adb_path = get_adb_path()
        self._adb_prefix = [adb_path]
        if device_id:
            self._adb_prefix = [adb_path, "-s", device_id]

    def _run(self, args: List[str], timeout: int = 10) -> str:
        """Run an adb command and return stdout."""
        cmd = self._adb_prefix + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                error = result.stderr.strip()
                if error:
                    raise IOError(f"adb error: {error}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise IOError(f"adb command timed out: {' '.join(cmd)}")
        except FileNotFoundError:
            raise IOError(
                "adb not found. Install with: brew install android-platform-tools"
            )

    def _shell(self, command: str, timeout: int = 10) -> str:
        """Run a shell command on the device."""
        return self._run(["shell", command], timeout=timeout)

    def _shell_stream(
        self, command: str, timeout: int = 60
    ) -> Generator[str, None, None]:
        """Run a shell command and yield stdout lines as they arrive."""
        cmd = self._adb_prefix + ["shell", command]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for line in proc.stdout:  # type: ignore
                yield line
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
        except FileNotFoundError:
            raise IOError(
                "adb not found. Install with: brew install android-platform-tools"
            )

    def _normalize_remote_path(self, path: str) -> str:
        """Normalize malformed remote paths before sending to adb."""
        path = path.strip()
        while "//" in path:
            path = path.replace("//", "/")

        return path

    # -------------------------------------------------------------------------
    # SFTPClient-compatible interface
    # -------------------------------------------------------------------------

    def listdir(self, path: str) -> List[str]:
        """List directory contents."""
        # Use ls -1 for simple listing
        output = self._shell(f'ls -1 "{path}"')
        entries = [line.strip() for line in output.splitlines() if line.strip()]
        return entries

    def listdir_attr(self, path: str) -> List[ADBStat]:
        """List directory with attributes (name, size, type)."""
        results = []
        for batch in self.listdir_attr_stream(path, batch_size=9999):
            results.extend(batch)
        return results

    def listdir_attr_stream(
        self, path: str, batch_size: int = 50
    ) -> Generator[List[ADBStat], None, None]:
        """
        Stream directory listing in batches.

        Yields lists of ADBStat objects, `batch_size` items at a time.
        """
        batch = []
        for line in self._shell_stream(f'ls -la "{path}"'):
            line = line.rstrip("\n\r")
            parts = line.split()
            if len(parts) < 7:
                continue
            if parts[0] == "total":
                continue

            perms = parts[0]

            # Find size: first numeric field after owner/group
            size = 0
            size_idx = None
            for i in range(2, min(len(parts), 6)):
                try:
                    size = int(parts[i])
                    size_idx = i
                    break
                except ValueError:
                    continue

            if size_idx is None:
                try:
                    size = int(parts[4])
                    size_idx = 4
                except (ValueError, IndexError):
                    size = 0
                    size_idx = 4

            # Name is everything after date+time fields
            name_start = size_idx + 3
            if name_start < len(parts):
                name = " ".join(parts[name_start:])
            else:
                name = parts[-1]

            if " -> " in name:
                name = name.split(" -> ")[0]
            name = name.rstrip("/")
            name = os.path.basename(name)

            if not name or name in (".", ".."):
                continue

            is_dir = perms.startswith("d")
            mode = S_IFDIR | 0o755 if is_dir else S_IFREG | 0o644

            stat = ADBStat(st_mode=mode, st_size=size, filename=name)
            batch.append(stat)

            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch

    def stat(self, path: str) -> ADBStat:
        """Get file/directory info (robust Android-safe version)."""

        path = self._normalize_remote_path(path)

        output = self._shell(
            f'if [ -d "{path}" ]; then echo "dir"; '
            f'elif [ -f "{path}" ]; then stat -c "%s" "{path}" 2>/dev/null || echo "0"; '
            f'else echo "missing"; fi'
        ).strip()

        if output == "missing":
            raise FileNotFoundError(f"Remote path does not exist: {path}")

        if output == "dir":
            return ADBStat(st_mode=S_IFDIR | 0o755, st_size=0)

        try:
            size = int(output)
        except ValueError:
            size = 0
        return ADBStat(st_mode=S_IFREG | 0o644, st_size=size)

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename/move a file or directory."""
        old_path = self._normalize_remote_path(old_path)
        new_path = self._normalize_remote_path(new_path)
        self._shell(f'mv "{old_path}" "{new_path}"')

    def remove(self, path: str) -> None:
        """Delete a file."""
        path = self._normalize_remote_path(path)
        quoted = shlex.quote(path)
        self._shell(f"rm -f {quoted}")

    def rmdir(self, path: str) -> None:
        """Delete a directory recursively."""
        path = self._normalize_remote_path(path)
        # Some callers may accidentally route file deletions here.
        # Detect the type first so Android rm errors do not occur.
        try:
            stat = self.stat(path)
            is_dir = S_ISDIR(stat.st_mode)
        except FileNotFoundError:
            return

        quoted = shlex.quote(path)

        if is_dir:
            self._shell(f"rm -rf {quoted}")
        else:
            self._shell(f"rm -f {quoted}")

    def mkdir(self, path: str) -> None:
        """Create a directory."""
        path = self._normalize_remote_path(path)
        self._shell(f'mkdir -p "{path}"')

    def get(
        self, remote_path: str, local_path: str, callback: Optional[Callable] = None
    ) -> None:
        """Alias for pull() — matches Paramiko SFTPClient interface."""
        self.pull(remote_path, local_path, callback)

    def put(
        self, local_path: str, remote_path: str, callback: Optional[Callable] = None
    ) -> None:
        """
        Upload a file to the device.

        Args:
            local_path: Local file path
            remote_path: Destination path on device
            callback: Progress callback(transferred, total) — limited with adb
        """
        total_size = os.path.getsize(local_path)

        # adb push doesn't support progress callbacks natively
        # We emit 0% at start and 100% at end
        if callback:
            callback(0, total_size)

        remote_path = self._normalize_remote_path(remote_path)
        self._run(
            ["push", local_path, remote_path],
            timeout=600,  # 10 min timeout for large files
        )

        if callback:
            callback(total_size, total_size)

    def pull(
        self, remote_path: str, local_path: str, callback: Optional[Callable] = None
    ) -> None:
        """
        Download a file from the device.

        Args:
            remote_path: File path on device
            local_path: Local destination path
            callback: Progress callback(transferred, total)
        """
        remote_path = self._normalize_remote_path(remote_path)

        # Get file size first
        try:
            stat = self.stat(remote_path)
            total_size = stat.st_size
        except Exception:
            total_size = 0

        if callback:
            callback(0, total_size)

        self._run(
            ["pull", remote_path, local_path],
            timeout=600,
        )

        if callback:
            callback(total_size, total_size)

    def get_channel(self) -> "ADBClient":
        """Compatibility stub — returns self for disk usage."""
        return self

    def get_transport(self) -> "ADBClient":
        """Compatibility stub — returns self for disk usage."""
        return self

    def open_session(self) -> "ADBSession":
        """Compatibility stub for disk usage command execution."""
        return ADBSession(self)

    def close(self) -> None:
        """No-op — ADB doesn't maintain a persistent connection."""


class ADBSession:
    """Mimics a paramiko SSH session for executing commands (used by disk usage)."""

    def __init__(self, client: ADBClient) -> None:
        self._client = client
        self._output = ""

    def exec_command(self, command: str) -> None:
        """Execute a command on the device, adapting for Android."""
        # Android's df doesn't support -B1, adapt the command
        if "df -B1" in command:
            # Extract path from command like "df -B1 /storage/emulated/0 | tail -1"
            parts = shlex.split(command.split("|")[0].strip())
            path = parts[-1] if len(parts) > 2 else "/storage/emulated/0"
            # Use Android-compatible df with -k (kilobytes)
            adb_command = f"df {shlex.quote(path)} | tail -1"
            raw_output = self._client._shell(adb_command)
            # Android df output: /path  size  used  avail  use%  mounted
            # Convert to bytes format expected by the caller
            line_parts = raw_output.strip().split()
            if len(line_parts) >= 4:
                try:
                    # Android df outputs in 1K blocks
                    total_kb = int(line_parts[1])
                    used_kb = int(line_parts[2])
                    # Return in same format as df -B1: fs total used avail
                    self._output = (
                        f"{line_parts[0]} {total_kb * 1024} "
                        f"{used_kb * 1024} {int(line_parts[3]) * 1024}"
                    )
                    return
                except (ValueError, IndexError):
                    pass
            self._output = raw_output
        else:
            self._output = self._client._shell(command)

    def recv(self, size: int) -> bytes:
        """Get command output."""
        return self._output.encode("utf-8")

    def close(self) -> None:
        pass


# -------------------------------------------------------------------------
# Device discovery
# -------------------------------------------------------------------------


def get_connected_devices() -> List[dict]:
    """
    Get list of connected Android devices.

    Returns:
        List of dicts with 'id' and 'status' keys.
        Example: [{"id": "ABCD1234", "status": "device", "model": "Pixel 6"}]
    """
    try:
        adb_path = get_adb_path()
        result = subprocess.run(
            [adb_path, "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        devices = []
        for line in result.stdout.splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                device_id = parts[0]
                # Try to get model name
                model = ""
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":", 1)[1]
                        break
                devices.append(
                    {
                        "id": device_id,
                        "status": "device",
                        "model": model or device_id,
                    }
                )
        return devices
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_adb_path() -> str:
    adb_path = shutil.which("adb")

    if not adb_path:
        for candidate in [
            "/opt/homebrew/bin/adb",
            "/usr/local/bin/adb",
        ]:
            if os.path.exists(candidate):
                adb_path = candidate
                break
    if not adb_path:
        raise IOError("abd path error")
    return adb_path
