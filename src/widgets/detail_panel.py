"""
Detail panel: shows file metadata when a file is selected in the explorer.

Reads .nfo sidecar files and requests ffprobe stream info. Designed to be fast:
no image previews or downloads.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)



class DetailPanel(QWidget):
    """
    Side panel that shows file details on selection.

    Shows:
    - File name, size, type
    - NFO metadata (title, show, season, genre): loaded from the .nfo sidecar
    - Video/audio stream info: from ffprobe on the metadata channel
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

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

        # Metadata (from NFO): shown first since it's instant
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

        # Stream info (from ffprobe): appears after metadata
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

    def show_file(self, remote_path: str, file_size_str: str = "") -> bool:
        """Show basic file details and return whether it is a video."""
        from src.services.ffmpeg_service import is_video_file

        filename = os.path.basename(remote_path)
        ext = os.path.splitext(filename)[1].lower()

        self._name_label.setText(filename)
        self._name_label.setVisible(True)

        info_parts = []
        if file_size_str:
            info_parts.append(file_size_str)
        if ext:
            info_parts.append(f"{ext.lstrip('.').upper()} file")
        self._info_label.setText("  •  ".join(info_parts))
        self._info_label.setVisible(True)
        self._empty_label.setVisible(False)
        self.clear_stream_info()
        self.clear_metadata()
        return is_video_file(filename)

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

    def show_metadata(self, metadata: dict[str, str]) -> None:
        """Render parsed NFO values or hide the metadata section when empty."""
        field_map = [
            ("title", "Title"),
            ("sorttitle", "Sort"),
            ("showtitle", "Show"),
            ("season", "Season"),
            ("episode", "Episode"),
            ("year", "Year"),
            ("plot", "Plot"),
            ("director", "Director"),
            ("artist", "Artist"),
            ("studio", "Studio"),
        ]
        lines = []
        for tag, label in field_map:
            value = metadata.get(tag, "")
            if value:
                if len(value) > 60:
                    value = value[:57] + "..."
                lines.append(f"<b>{label}:</b> {value}")

        genres = metadata.get("genre", "").replace(";", ", ")
        if genres:
            lines.append(f"<b>Genre:</b> {genres}")

        if not lines:
            self.clear_metadata()
            return

        self._meta_header.setVisible(True)
        self._meta_label.setVisible(True)
        self._meta_label.setTextFormat(Qt.TextFormat.RichText)
        self._meta_label.setText("<br>".join(lines))

    def clear_metadata(self) -> None:
        """Hide the metadata section."""
        self._meta_header.setVisible(False)
        self._meta_label.setVisible(False)

    def show_stream_info(self, data: dict) -> None:
        """Display ffprobe results."""
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

    def clear_stream_info(self) -> None:
        self._stream_label.setText("")
        self._stream_label.setVisible(False)
