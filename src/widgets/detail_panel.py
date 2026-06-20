"""
Detail panel — shows file metadata when a file is selected in the explorer.

Reads .nfo sidecar files (instant) and optionally runs ffprobe for
video stream info. Designed to be fast — no image previews or downloads.
"""

from __future__ import annotations

import os
import shlex
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings


class DetailPanel(QWidget):
    """
    Side panel that shows file details on selection.

    Shows:
    - File name, size, type
    - NFO metadata (title, show, season, genre) — instant from .nfo file
    - Video/audio stream info — from ffprobe (background thread)
    """

    def __init__(self, settings: Settings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._sftp: object = None
        self._current_path: str = ""

        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)

        # File name
        self._name_label = QLabel("")
        self._name_label.setWordWrap(True)
        name_font = QFont()
        name_font.setWeight(QFont.Weight.DemiBold)
        name_font.setPointSize(13)
        self._name_label.setFont(name_font)
        layout.addWidget(self._name_label)

        # Basic info
        self._info_label = QLabel("")
        self._info_label.setObjectName("secondary_label")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setObjectName("separator")
        layout.addWidget(sep1)

        # Metadata (from NFO) — shown first since it's instant
        self._meta_header = QLabel("Metadata")
        meta_font = QFont()
        meta_font.setWeight(QFont.Weight.Medium)
        self._meta_header.setFont(meta_font)
        layout.addWidget(self._meta_header)

        self._meta_label = QLabel("")
        self._meta_label.setWordWrap(True)
        self._meta_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._meta_label)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("separator")
        layout.addWidget(sep2)
        self._sep2 = sep2

        # Stream info (from ffprobe) — loads async, appears after metadata
        self._stream_label = QLabel("")
        self._stream_label.setWordWrap(True)
        self._stream_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._stream_label)

        layout.addStretch()

        # Empty state
        self._empty_label = QLabel("Select a file to see details")
        self._empty_label.setObjectName("secondary_label")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        self._show_empty()

    def set_sftp(self, sftp: object) -> None:
        """Update the SFTP client reference."""
        self._sftp = sftp

    def show_file(self, remote_path: str, file_size_str: str = "") -> None:
        """Show details for the selected file."""
        from src.services.ffmpeg_service import is_video_file

        self._current_path = remote_path
        filename = os.path.basename(remote_path)
        ext = os.path.splitext(filename)[1].lower()

        # Show name and basic info
        self._name_label.setText(filename)
        self._name_label.setVisible(True)

        info_parts = []
        if file_size_str:
            info_parts.append(file_size_str)
        if ext:
            type_name = ext.lstrip(".").upper()
            info_parts.append(f"{type_name} file")
        self._info_label.setText("  •  ".join(info_parts))
        self._info_label.setVisible(True)

        self._empty_label.setVisible(False)

        is_video = is_video_file(filename)

        # Stream info — only for video files
        if is_video and self._sftp:
            self._stream_label.setText("Loading...")
            self._stream_label.setVisible(True)
            self._sep2.setVisible(True)
            self._fetch_probe(remote_path)
        else:
            self._stream_label.setVisible(False)
            self._sep2.setVisible(False)

        # Metadata from NFO — only for video files (NFOs are video sidecar files)
        if is_video and self._sftp:
            self._load_nfo_metadata(remote_path)
        else:
            self._meta_header.setVisible(False)
            self._meta_label.setVisible(False)

    def show_folder(self, folder_name: str) -> None:
        """Show minimal info for a folder (no network calls)."""
        self._name_label.setText(folder_name)
        self._name_label.setVisible(True)
        self._info_label.setText("Folder")
        self._info_label.setVisible(True)
        self._empty_label.setVisible(False)
        self._stream_label.setVisible(False)
        self._sep2.setVisible(False)
        self._meta_header.setVisible(False)
        self._meta_label.setVisible(False)

    def clear(self) -> None:
        """Clear the panel (no selection)."""
        self._show_empty()

    def _show_empty(self) -> None:
        self._name_label.setVisible(False)
        self._info_label.setVisible(False)
        self._stream_label.setVisible(False)
        self._sep2.setVisible(False)
        self._meta_header.setVisible(False)
        self._meta_label.setVisible(False)
        self._empty_label.setVisible(True)

    def _load_nfo_metadata(self, remote_path: str) -> None:
        """Read .nfo sidecar file for metadata via SFTP (fast)."""
        nfo_path = os.path.splitext(remote_path)[0] + ".nfo"

        if not self._sftp:
            self._meta_header.setVisible(False)
            self._meta_label.setVisible(False)
            return

        try:
            # Use SFTP open() — much faster than SSH exec cat
            with self._sftp.open(nfo_path, "r") as f:
                content = f.read().decode("utf-8", errors="ignore").strip()

            if not content:
                self._meta_header.setVisible(False)
                self._meta_label.setVisible(False)
                return

            # Scene NFOs are often ASCII art, not XML — skip those
            if not content.lstrip().startswith("<"):
                self._meta_header.setVisible(False)
                self._meta_label.setVisible(False)
                return

            import xml.etree.ElementTree as ET

            root = ET.fromstring(content)
            lines = []

            field_map = [
                ("title", "Title"),
                ("sorttitle", "Sort"),
                ("showtitle", "Show"),
                ("season", "Season"),
                ("episode", "Episode"),
                ("year", "Year"),
                ("genre", "Genre"),
                ("plot", "Plot"),
                ("director", "Director"),
                ("artist", "Artist"),
                ("studio", "Studio"),
            ]

            genres = []
            for elem in root:
                if elem.tag == "genre" and elem.text:
                    genres.append(elem.text.strip())

            for tag, label in field_map:
                if tag == "genre":
                    continue
                elem = root.find(tag)
                if elem is not None and elem.text and elem.text.strip():
                    val = elem.text.strip()
                    if len(val) > 60:
                        val = val[:57] + "..."
                    lines.append(f"<b>{label}:</b> {val}")

            if genres:
                lines.append(f"<b>Genre:</b> {', '.join(genres)}")

            if lines:
                self._meta_header.setVisible(True)
                self._meta_label.setVisible(True)
                self._meta_label.setTextFormat(Qt.TextFormat.RichText)
                self._meta_label.setText("<br>".join(lines))
            else:
                self._meta_header.setVisible(False)
                self._meta_label.setVisible(False)

        except (IOError, OSError):
            # NFO file doesn't exist — that's fine, just hide metadata
            self._meta_header.setVisible(False)
            self._meta_label.setVisible(False)
        except Exception as e:
            # Parse error — log it so we can debug
            from src.utils.logging_signal import logger

            logger.warn(f"Detail panel: NFO parse error: {e}")
            self._meta_header.setVisible(False)
            self._meta_label.setVisible(False)

    def _fetch_probe(self, remote_path: str) -> None:
        """Run ffprobe synchronously on the metadata channel.

        This is fast (~200ms) and safe — uses its own dedicated SFTP channel
        that doesn't conflict with the explorer or transfers. Running synchronously
        eliminates the QThread destruction crash that occurred when the thread
        couldn't be stopped in time.
        """
        try:
            channel = self._sftp.get_channel()
            if not channel:
                self._on_probe_error()
                return
            transport = channel.get_transport()
            if not transport:
                self._on_probe_error()
                return

            cmd = (
                f"ffprobe -v quiet -print_format json "
                f"-show_format -show_streams "
                f"{shlex.quote(remote_path)}"
            )
            session = transport.open_session()
            session.exec_command(cmd)

            output = b""
            while True:
                chunk = session.recv(4096)
                if not chunk:
                    break
                output += chunk
            session.close()

            import json

            data = json.loads(output.decode("utf-8", errors="ignore"))
            self._on_probe_done(data)
        except Exception:
            self._on_probe_error()

    def _on_probe_done(self, data: dict) -> None:
        """Display ffprobe results."""
        # Check we're still showing the same file
        lines = []

        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))
        if duration > 0:
            mins = int(duration // 60)
            secs = int(duration % 60)
            lines.append(f"Duration: {mins}:{secs:02d}")

        streams = data.get("streams", [])
        for stream in streams:
            codec_type = stream.get("codec_type")
            codec_name = stream.get("codec_name", "?")

            if codec_type == "video":
                w = stream.get("width", "?")
                h = stream.get("height", "?")
                fps_str = stream.get("r_frame_rate", "")
                fps = ""
                if fps_str and "/" in fps_str:
                    try:
                        num, den = fps_str.split("/")
                        fps = f"{int(num) / int(den):.0f}fps"
                    except (ValueError, ZeroDivisionError):
                        pass
                profile = stream.get("profile", "")
                codec_display = codec_name.upper()
                if profile:
                    codec_display += f" {profile}"
                res = f"{w}×{h}"
                parts = [codec_display, res]
                if fps:
                    parts.append(fps)
                lines.append(f"Video: {', '.join(parts)}")

            elif codec_type == "audio":
                ch = stream.get("channels", "?")
                rate = stream.get("sample_rate", "")
                lang = stream.get("tags", {}).get("language", "")
                parts = [codec_name.upper(), f"{ch}ch"]
                if rate:
                    parts.append(f"{int(rate) // 1000}kHz")
                if lang:
                    parts.append(lang)
                lines.append(f"Audio: {', '.join(parts)}")

            elif codec_type == "subtitle":
                lang = stream.get("tags", {}).get("language", "")
                lines.append(f"Sub: {codec_name}" + (f" ({lang})" if lang else ""))

        self._stream_label.setText("\n".join(lines) if lines else "")
        self._stream_label.setVisible(bool(lines))

    def _on_probe_error(self) -> None:
        self._stream_label.setText("")
        self._stream_label.setVisible(False)
