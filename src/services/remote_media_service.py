"""Remote ffprobe and ffmpeg operations for media inspection and repair."""

from __future__ import annotations

import json
import os
import shlex
import uuid
from typing import Any, Optional, Tuple

from paramiko import SFTPClient, Transport

from src.clients.ssh_command_client import open_ssh_session
from src.models.media import AudioTrack, QuickFixOptions, SubtitleTrack
from src.utils.nfo import parse_nfo_content


class RemoteMediaService:
    """Run media tools and parse their output for one remote connection."""

    def __init__(self, sftp: SFTPClient) -> None:
        self._sftp = sftp

    def get_transport(self) -> Optional[Transport]:
        """Return the SSH transport backing the SFTP session, if available."""
        channel = self._sftp.get_channel()
        return channel.get_transport() if channel else None

    def probe_media(self, remote_path: str) -> dict[str, Any]:
        """Return ffprobe format and stream metadata for a remote video."""
        command = (
            "ffprobe -v quiet -print_format json -show_format -show_streams "
            f"{shlex.quote(remote_path)}"
        )
        output = self._run_command(command).decode("utf-8", errors="ignore").strip()
        if not output:
            raise ValueError("ffprobe returned no output")
        return json.loads(output)

    def read_nfo(self, remote_video_path: str) -> dict[str, str]:
        """Read a video's XML sidecar metadata when a valid NFO exists."""
        nfo_path = os.path.splitext(remote_video_path)[0] + ".nfo"
        return self.read_nfo_path(nfo_path)

    def read_nfo_path(self, nfo_path: str) -> dict[str, str]:
        """Read and parse an NFO from its full remote path."""
        with self._sftp.open(nfo_path, "r") as remote_file:
            content = remote_file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        return parse_nfo_content(content)

    def write_nfo_path(self, nfo_path: str, content: str) -> None:
        """Write XML content to a remote NFO sidecar."""
        with self._sftp.open(nfo_path, "w") as remote_file:
            remote_file.write(content.encode("utf-8"))

    def probe_subtitle_tracks(self, remote_path: str) -> list[SubtitleTrack]:
        """Return subtitle stream details for a remote video."""
        return self.probe_stream_tracks(remote_path)[1]

    def probe_audio_tracks(self, remote_path: str) -> list[AudioTrack]:
        """Return audio stream details for a remote video."""
        return self.probe_stream_tracks(remote_path)[0]

    def probe_stream_tracks(
        self, remote_path: str
    ) -> tuple[list[AudioTrack], list[SubtitleTrack]]:
        """Return audio and subtitle tracks from one ffprobe request."""
        command = (
            "ffprobe -v quiet -print_format json -show_streams "
            f"{shlex.quote(remote_path)}"
        )
        output = self._run_command(command).decode("utf-8", errors="replace")
        if not output.strip():
            return [], []

        data = json.loads(output)
        audio_tracks = []
        subtitle_tracks = []
        for stream in data.get("streams", []):
            tags = stream.get("tags", {})
            codec = stream.get("codec_name", "unknown")
            language = tags.get("language", "und")
            title = tags.get("title", "")
            if stream.get("codec_type") == "audio":
                audio_tracks.append(
                    AudioTrack(
                        index=len(audio_tracks),
                        language=language,
                        codec=codec,
                        title=title,
                    )
                )
            elif stream.get("codec_type") == "subtitle":
                subtitle_tracks.append(
                    SubtitleTrack(
                        index=len(subtitle_tracks),
                        language=language,
                        codec=codec,
                        title=title,
                    )
                )
        return audio_tracks, subtitle_tracks

    def build_quick_fix_command(
        self,
        remote_path: str,
        options: QuickFixOptions,
        subtitle_track_count: int,
    ) -> Tuple[str, str]:
        """Build the safely quoted ffmpeg command and an action summary."""
        extension = os.path.splitext(remote_path)[1]
        base_path = os.path.splitext(remote_path)[0]
        output_extension = ".mp4" if options.to_mp4 else extension
        temporary_path = f"{base_path}.filesling-{uuid.uuid4().hex}{output_extension}"
        command_parts = ["ffmpeg", "-y"]

        if options.fix_timestamps:
            command_parts.extend(["-fflags", "+genpts"])
        command_parts.extend(["-i", shlex.quote(remote_path)])

        filter_audio = options.strip_audio or options.keep_audio_indices is not None
        filter_subtitles = (
            options.strip_subtitles or options.keep_subtitle_indices is not None
        )
        if filter_audio or filter_subtitles:
            command_parts.extend(["-map", "0", "-map_metadata", "0"])
            if filter_audio:
                command_parts.extend(["-map", "-0:a"])
                if options.keep_audio_indices is not None:
                    for index in options.keep_audio_indices:
                        command_parts.extend(["-map", f"0:a:{index}"])
            if filter_subtitles:
                command_parts.extend(["-map", "-0:s"])
                if options.keep_subtitle_indices is not None:
                    for index in options.keep_subtitle_indices:
                        command_parts.extend(["-map", f"0:s:{index}"])
        command_parts.extend(["-c", "copy"])

        if options.to_mp4:
            command_parts.extend(["-movflags", "+faststart"])
        command_parts.extend([shlex.quote(temporary_path), "2>/dev/null"])
        ffmpeg_command = " ".join(command_parts)

        if output_extension.lower() != extension.lower():
            final_path = f"{base_path}{output_extension}"
            backup_path = f"{remote_path}.filesling-backup-{uuid.uuid4().hex}"
            full_command = (
                f"if [ -e {shlex.quote(final_path)} ]; then "
                "echo 'Output already exists' >&2; "
                f"exit 17; fi && {ffmpeg_command} && "
                f"mv {shlex.quote(remote_path)} "
                f"{shlex.quote(backup_path)} && "
                f"if mv {shlex.quote(temporary_path)} {shlex.quote(final_path)}; "
                f"then rm -f {shlex.quote(backup_path)}; "
                f"else mv {shlex.quote(backup_path)} {shlex.quote(remote_path)}; "
                f"exit 1; fi"
            )
        else:
            full_command = (
                f"{ffmpeg_command} && mv {shlex.quote(temporary_path)} "
                f"{shlex.quote(remote_path)}"
            )

        actions = []
        if options.to_mp4:
            actions.append("container to MP4")
        if options.fix_timestamps:
            actions.append("fix timestamps")
        if options.keep_subtitle_indices is not None:
            kept_count = len(options.keep_subtitle_indices)
            actions.append(f"keep {kept_count}/{subtitle_track_count} subs")
        elif options.strip_subtitles:
            actions.append("remove subs")
        if options.strip_audio:
            actions.append("remove audio")
        elif options.keep_audio_indices is not None:
            actions.append(f"keep {len(options.keep_audio_indices)} audio tracks")
        return full_command, ", ".join(actions)

    def _run_command(self, command: str) -> bytes:
        """Run a remote shell command and return its standard output."""
        transport = self.get_transport()
        if transport is None:
            raise RuntimeError("No SSH transport is available")

        with open_ssh_session(transport, command) as session:
            output = bytearray()
            while True:
                chunk = session.recv(4096)
                if not chunk:
                    break
                output.extend(chunk)
            return bytes(output)
