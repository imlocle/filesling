"""
Remote ffmpeg service for FileSling.

Runs ffmpeg commands on the remote server via SSH to convert video files
without downloading them. Parses progress output for percentage tracking.

Only works for SSH connections (requires remote command execution).
"""

from __future__ import annotations

import re
import shlex
from typing import Callable, Optional

from src.utils.logging_signal import logger

# ffmpeg progress output: "time=00:01:23.45"
_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

# Video file extensions that can be converted
VIDEO_EXTENSIONS = frozenset(
    (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".ts",
        ".divx",
        ".xvid",
    )
)


def is_video_file(filename: str) -> bool:
    """Check if a filename is a video file."""
    import os

    ext = os.path.splitext(filename)[1].lower()
    return ext in VIDEO_EXTENSIONS


def get_video_duration(ssh_client: object, remote_path: str) -> float:
    """
    Get the duration of a remote video file in seconds via ffprobe.

    Args:
        ssh_client: Paramiko SFTPClient or SSHClient (needs .get_channel().get_transport())

    Returns 0.0 if duration can't be determined.
    """
    try:
        transport = _get_transport(ssh_client)
        if not transport:
            return 0.0

        cmd = (
            f"ffprobe -v error -show_entries format=duration "
            f"-of default=noprint_wrappers=1:nokey=1 "
            f"{shlex.quote(remote_path)}"
        )
        session = transport.open_session()
        session.exec_command(cmd)
        output = session.recv(1024).decode("utf-8").strip()
        session.close()

        return float(output) if output else 0.0
    except (ValueError, TypeError, OSError):
        return 0.0


def check_ffmpeg_installed(ssh_client: object) -> bool:
    """Check if ffmpeg is available on the remote server."""
    try:
        transport = _get_transport(ssh_client)
        if not transport:
            return False

        session = transport.open_session()
        session.exec_command("which ffmpeg")
        output = session.recv(1024).decode("utf-8").strip()
        exit_code = session.recv_exit_status()
        session.close()

        return exit_code == 0 and bool(output)
    except Exception:
        return False


def _get_transport(client: object) -> object:
    """Get the SSH transport from either an SFTPClient or SSHClient."""
    # SFTPClient path
    if hasattr(client, "get_channel"):
        channel = client.get_channel()  # type: ignore
        if channel:
            return channel.get_transport()
    # SSHClient path
    if hasattr(client, "get_transport"):
        return client.get_transport()  # type: ignore
    return None


def convert_video(
    ssh_client: object,
    remote_path: str,
    preset: str = "fast",
    crf: int = 18,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> str:
    """
    Convert a video file to H.264 on the remote server.

    Runs ffmpeg remotely, monitors progress, and returns the output path.

    Args:
        ssh_client: Paramiko SSHClient with active connection
        remote_path: Full path to the video on the remote server
        preset: ffmpeg preset (ultrafast, fast, medium, slow)
        crf: Quality (18=high, 22=good, 28=low). Lower = bigger file.
        progress_cb: Callback receiving percentage (0-100)

    Returns:
        Path to the converted file on the remote server

    Raises:
        RuntimeError: If ffmpeg fails or isn't installed
    """
    import os

    # Build output path (same dir, _converted suffix before extension)
    base, ext = os.path.splitext(remote_path)
    output_path = f"{base}_h264.mp4"

    # Get duration for progress calculation
    duration = get_video_duration(ssh_client, remote_path)

    # Build ffmpeg command
    # -y: overwrite output
    # -progress pipe:1: output progress to stdout
    cmd = (
        f"ffmpeg -y -i {shlex.quote(remote_path)} "
        f"-c:v libx264 -preset {preset} -crf {crf} "
        f"-c:a aac -b:a 128k "
        f"-movflags +faststart "
        f"-progress pipe:1 "
        f"{shlex.quote(output_path)} 2>/dev/null"
    )

    logger.info(f"ffmpeg: Converting {os.path.basename(remote_path)}...")
    logger.info(f"ffmpeg: Preset={preset}, CRF={crf}")

    try:
        transport = _get_transport(ssh_client)
        if not transport:
            raise RuntimeError("No SSH connection")

        session = transport.open_session()
        session.exec_command(cmd)

        # Read progress output
        buffer = ""
        while True:
            if session.exit_status_ready():
                # Read remaining output
                while session.recv_ready():
                    buffer += session.recv(4096).decode("utf-8", errors="ignore")
                break

            if session.recv_ready():
                chunk = session.recv(4096).decode("utf-8", errors="ignore")
                buffer += chunk

                # Parse time from progress output
                if duration > 0 and progress_cb:
                    matches = _TIME_RE.findall(buffer)
                    if matches:
                        last = matches[-1]
                        current_secs = (
                            int(last[0]) * 3600
                            + int(last[1]) * 60
                            + float(last[2])
                        )
                        pct = min(int(current_secs * 100 / duration), 99)
                        progress_cb(pct)

                # Keep buffer manageable
                if len(buffer) > 8192:
                    buffer = buffer[-4096:]

        exit_code = session.recv_exit_status()
        session.close()

        if exit_code != 0:
            raise RuntimeError(f"ffmpeg exited with code {exit_code}")

        if progress_cb:
            progress_cb(100)

        logger.success(
            f"ffmpeg: Conversion complete → {os.path.basename(output_path)}"
        )
        return output_path

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"ffmpeg conversion failed: {e}")


def replace_original(
    ssh_client: object, original_path: str, converted_path: str
) -> None:
    """
    Replace the original file with the converted one.

    Deletes the original and renames the converted file to the original name
    (but with .mp4 extension).
    """
    import os

    try:
        transport = _get_transport(ssh_client)
        if not transport:
            raise RuntimeError("No SSH connection")

        # Determine final name (original name but .mp4 extension)
        base = os.path.splitext(original_path)[0]
        final_path = f"{base}.mp4"

        # If original and final are different files, remove original first
        if original_path != final_path:
            cmd = f"rm -f {shlex.quote(original_path)}"
            session = transport.open_session()
            session.exec_command(cmd)
            session.recv_exit_status()
            session.close()

        # Rename converted to final
        cmd = f"mv {shlex.quote(converted_path)} {shlex.quote(final_path)}"
        session = transport.open_session()
        session.exec_command(cmd)
        exit_code = session.recv_exit_status()
        session.close()

        if exit_code != 0:
            raise RuntimeError("Failed to rename converted file")

        logger.success(f"ffmpeg: Replaced original with {os.path.basename(final_path)}")

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to replace original: {e}")
