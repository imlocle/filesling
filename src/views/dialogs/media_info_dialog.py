"""
Media Info dialog — displays video stream info and editable NFO metadata tags.

This dialog has two tabs:
- Info: Read-only stream details from ffprobe (codec, resolution, bitrate, etc.)
- Tags: Editable metadata fields saved as .nfo sidecar files (Jellyfin-compatible)
"""

import os
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.utils.constants import (
    METADATA_ADVANCED_TAGS,
    METADATA_COMMON_TAGS,
    METADATA_FIELD_HINTS,
    METADATA_KEY_TO_NFO,
    METADATA_NFO_SKIP_KEYS,
    METADATA_NFO_TO_KEY,
    METADATA_PEOPLE_ROLES,
)
from src.utils.logging_signal import logger


class MediaInfoDialog(QDialog):
    """
    Dialog for viewing video stream info and editing NFO metadata.

    Args:
        remote_path: Full remote path to the video file.
        probe_data: Parsed JSON dict from ffprobe (format + streams).
        nfo_data: Parsed NFO data dict (tag → value), or empty dict.
        sftp: The SFTP client for writing .nfo files back.
        parent: Parent widget.
        open_tab: Which tab to open ("info" or "tags").
    """

    def __init__(
        self,
        remote_path: str,
        probe_data: Dict[str, Any],
        nfo_data: Dict[str, str],
        sftp: Any,
        parent: Optional[QWidget] = None,
        open_tab: str = "info",
    ) -> None:
        super().__init__(parent)
        self._remote_path = remote_path
        self._probe_data = probe_data
        self._nfo_data = nfo_data
        self._sftp = sftp
        self._tag_fields: Dict[str, QLineEdit] = {}

        filename = os.path.basename(remote_path)
        self.setWindowTitle(f"Media Info — {filename}")
        self.setMinimumSize(550, 500)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # === Tab 1: Info ===
        tabs.addTab(self._build_info_tab(filename), "Info")

        # === Tab 2: Tags ===
        tabs.addTab(self._build_tags_tab(filename), "Tags")

        # Open on requested tab
        tabs.setCurrentIndex(1 if open_tab == "tags" else 0)

    # ------------------------------------------------------------------
    # Info Tab
    # ------------------------------------------------------------------

    def _build_info_tab(self, filename: str) -> QWidget:
        """Build the read-only stream info tab."""
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)

        info_text = QPlainTextEdit()
        info_text.setReadOnly(True)
        info_text.setStyleSheet("font-family: monospace; font-size: 12px;")

        fmt = self._probe_data.get("format", {})
        streams = self._probe_data.get("streams", [])

        lines = []
        lines.append(f"File: {filename}")
        lines.append(f"Format: {fmt.get('format_long_name', 'Unknown')}")

        duration_secs = float(fmt.get("duration", 0))
        if duration_secs > 0:
            hours = int(duration_secs // 3600)
            mins = int((duration_secs % 3600) // 60)
            secs = int(duration_secs % 60)
            lines.append(f"Duration: {hours:02d}:{mins:02d}:{secs:02d}")

        size_bytes = int(fmt.get("size", 0))
        if size_bytes > 0:
            size_mb = size_bytes / (1024 * 1024)
            lines.append(f"Size: {size_mb:.1f} MB")

        bitrate = int(fmt.get("bit_rate", 0))
        if bitrate > 0:
            lines.append(f"Overall Bitrate: {bitrate // 1000} kbps")

        lines.append("")

        for i, stream in enumerate(streams):
            codec_type = stream.get("codec_type", "unknown")
            codec_name = stream.get("codec_name", "unknown")
            codec_long = stream.get("codec_long_name", "")

            if codec_type == "video":
                width = stream.get("width", "?")
                height = stream.get("height", "?")
                fps_str = stream.get("r_frame_rate", "")
                fps = ""
                if fps_str and "/" in fps_str:
                    num, den = fps_str.split("/")
                    try:
                        fps = f"{int(num) / int(den):.2f} fps"
                    except (ValueError, ZeroDivisionError):
                        fps = fps_str

                pix_fmt = stream.get("pix_fmt", "")
                profile = stream.get("profile", "")
                vbitrate = int(stream.get("bit_rate", 0))

                lines.append(f"━━━ Video Stream #{i} ━━━")
                lines.append(f"  Codec: {codec_name} ({codec_long})")
                if profile:
                    lines.append(f"  Profile: {profile}")
                lines.append(f"  Resolution: {width}×{height}")
                if fps:
                    lines.append(f"  Frame Rate: {fps}")
                if pix_fmt:
                    lines.append(f"  Pixel Format: {pix_fmt}")
                if vbitrate > 0:
                    lines.append(f"  Bitrate: {vbitrate // 1000} kbps")

            elif codec_type == "audio":
                sample_rate = stream.get("sample_rate", "?")
                channels = stream.get("channels", "?")
                abitrate = int(stream.get("bit_rate", 0))
                lang = stream.get("tags", {}).get("language", "")

                lines.append(f"━━━ Audio Stream #{i} ━━━")
                lines.append(f"  Codec: {codec_name} ({codec_long})")
                lines.append(f"  Sample Rate: {sample_rate} Hz")
                lines.append(f"  Channels: {channels}")
                if abitrate > 0:
                    lines.append(f"  Bitrate: {abitrate // 1000} kbps")
                if lang:
                    lines.append(f"  Language: {lang}")

            elif codec_type == "subtitle":
                lang = stream.get("tags", {}).get("language", "")
                lines.append(f"━━━ Subtitle Stream #{i} ━━━")
                lines.append(f"  Codec: {codec_name}")
                if lang:
                    lines.append(f"  Language: {lang}")

            lines.append("")

        info_text.setPlainText("\n".join(lines))
        tab_layout.addWidget(info_text)
        return widget

    # ------------------------------------------------------------------
    # Tags Tab
    # ------------------------------------------------------------------

    def _build_tags_tab(self, filename: str) -> QWidget:
        """Build the editable tags tab with NFO save."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        widget = QWidget()
        tags_layout = QVBoxLayout(widget)

        hint = QLabel(
            "Metadata is saved as an .nfo file next to the video.\n"
            "Jellyfin reads .nfo files automatically on library scan."
        )
        hint.setObjectName("secondary_label")
        hint.setWordWrap(True)
        tags_layout.addWidget(hint)

        # Get embedded tags from ffprobe
        fmt = self._probe_data.get("format", {})
        tags = fmt.get("tags", {})

        # Value resolver: NFO takes priority, then embedded tags
        def _get_value(key: str) -> str:
            nfo_key = METADATA_NFO_TO_KEY.get(key) or key
            # Also check the reverse: our key might map to an NFO element name
            nfo_elem = METADATA_KEY_TO_NFO.get(key, key)
            val = (
                self._nfo_data.get(nfo_elem, "")
                or self._nfo_data.get(key, "")
                or self._nfo_data.get(nfo_key, "")
            )
            if val:
                return val
            return tags.get(key, "") or tags.get(key.upper(), "") or ""

        # Auto-populate title with filename if no title exists
        auto_title = _get_value("title")
        if not auto_title:
            auto_title = os.path.splitext(filename)[0]

        # --- Common tags grid ---
        grid = QGridLayout()
        grid.setSpacing(8)
        row = 0

        for key, label in METADATA_COMMON_TAGS:
            value = auto_title if key == "title" else _get_value(key)
            grid.addWidget(QLabel(label + ":"), row, 0)
            field = QLineEdit(value)
            h = METADATA_FIELD_HINTS.get(key)
            if h:
                field.setPlaceholderText(h[0])
                field.setToolTip(h[1])
            grid.addWidget(field, row, 1)
            self._tag_fields[key] = field
            row += 1

        tags_layout.addLayout(grid)

        # --- Advanced tags (expandable) ---
        advanced_container = QWidget()
        advanced_layout_inner = QVBoxLayout(advanced_container)
        advanced_layout_inner.setContentsMargins(0, 0, 0, 0)
        advanced_layout_inner.setSpacing(4)
        advanced_container.setVisible(False)

        advanced_grid = QGridLayout()
        advanced_grid.setSpacing(8)
        adv_row = 0

        for key, label in METADATA_ADVANCED_TAGS:
            value = _get_value(key)
            advanced_grid.addWidget(QLabel(label + ":"), adv_row, 0)
            field = QLineEdit(value)
            h = METADATA_FIELD_HINTS.get(key)
            if h:
                field.setPlaceholderText(h[0])
                field.setToolTip(h[1])
            advanced_grid.addWidget(field, adv_row, 1)
            self._tag_fields[key] = field
            adv_row += 1

        advanced_layout_inner.addLayout(advanced_grid)
        tags_layout.addWidget(advanced_container)

        # Toggle button
        show_more_btn = QPushButton("▶ Show All Tags")
        show_more_btn.setObjectName("subtle_btn")
        show_more_btn.setMaximumWidth(140)

        def _toggle_advanced() -> None:
            visible = not advanced_container.isVisible()
            advanced_container.setVisible(visible)
            show_more_btn.setText("▼ Show Less" if visible else "▶ Show All Tags")

        show_more_btn.clicked.connect(_toggle_advanced)
        tags_layout.addWidget(show_more_btn)

        # Show extra NFO tags that aren't in our standard lists
        all_known_keys = {k for k, _ in METADATA_COMMON_TAGS + METADATA_ADVANCED_TAGS}
        all_nfo_known = set(METADATA_NFO_TO_KEY.keys()) | {
            METADATA_KEY_TO_NFO.get(k, k) for k in all_known_keys
        }

        for nfo_key, value in self._nfo_data.items():
            if nfo_key in METADATA_NFO_SKIP_KEYS:
                continue
            mapped_key = METADATA_NFO_TO_KEY.get(nfo_key, nfo_key)
            if mapped_key not in all_known_keys and nfo_key not in all_nfo_known:
                advanced_grid.addWidget(QLabel(f"{nfo_key}:"), adv_row, 0)
                field = QLineEdit(value)
                field.setPlaceholderText("(custom tag)")
                advanced_grid.addWidget(field, adv_row, 1)
                self._tag_fields[nfo_key] = field
                adv_row += 1
                advanced_container.setVisible(True)
                show_more_btn.setText("▼ Show Less")

        # Add custom tag button
        def _add_custom_tag() -> None:
            from PySide6.QtWidgets import QInputDialog

            tag_name, ok = QInputDialog.getText(
                self,
                "Add Tag",
                "Tag name (e.g., 'composer', 'copyright', 'network'):",
            )
            if ok and tag_name.strip():
                tag_name = tag_name.strip().lower().replace(" ", "_")
                if tag_name in self._tag_fields:
                    self._tag_fields[tag_name].setFocus()
                    return
                nonlocal adv_row
                advanced_grid.addWidget(QLabel(f"{tag_name}:"), adv_row, 0)
                field = QLineEdit("")
                field.setPlaceholderText("(empty)")
                field.setFocus()
                advanced_grid.addWidget(field, adv_row, 1)
                self._tag_fields[tag_name] = field
                adv_row += 1
                advanced_container.setVisible(True)
                show_more_btn.setText("▼ Show Less")

        add_tag_btn = QPushButton("+ Add Tag")
        add_tag_btn.setToolTip("Add a custom metadata tag.")
        add_tag_btn.setMaximumWidth(100)
        add_tag_btn.clicked.connect(_add_custom_tag)
        tags_layout.addWidget(add_tag_btn)

        tags_layout.addStretch()

        # Save button
        save_btn = QPushButton("💾 Save")
        save_btn.setToolTip(
            "Saves metadata as an .nfo file next to the video.\n"
            "Jellyfin reads this automatically. Instant, doesn't touch the video."
        )
        save_btn.clicked.connect(self._save_nfo)
        tags_layout.addWidget(save_btn)

        scroll.setWidget(widget)
        return scroll

    # ------------------------------------------------------------------
    # Save NFO
    # ------------------------------------------------------------------

    def _save_nfo(self) -> None:
        """Build NFO XML from tag fields and write to server."""
        nfo_path = os.path.splitext(self._remote_path)[0] + ".nfo"

        # Auto-detect NFO type from filled fields
        has_season = bool(
            self._tag_fields.get("season_number")
            and self._tag_fields["season_number"].text().strip()
        )
        has_episode = bool(
            self._tag_fields.get("episode_sort")
            and self._tag_fields["episode_sort"].text().strip()
        )
        has_artist = bool(
            self._tag_fields.get("artist") and self._tag_fields["artist"].text().strip()
        )
        has_director = bool(
            self._tag_fields.get("director")
            and self._tag_fields["director"].text().strip()
        )

        if has_season or has_episode:
            root_tag = "episodedetails"
        elif has_artist and not has_director:
            root_tag = "musicvideo"
        else:
            root_tag = "movie"

        # Build XML
        lines = ['<?xml version="1.0" encoding="utf-8"?>', f"<{root_tag}>"]

        for key, field in self._tag_fields.items():
            value = field.text().strip()
            if not value:
                continue
            nfo_tag = METADATA_KEY_TO_NFO.get(key, key)

            if key == "genre":
                for g in value.split(";"):
                    g = g.strip()
                    if g:
                        lines.append(f"  <genre>{_xml_escape(g)}</genre>")
            else:
                lines.append(f"  <{nfo_tag}>{_xml_escape(value)}</{nfo_tag}>")

        # Auto-generate <actor> entries for Jellyfin's People section
        for key, role in METADATA_PEOPLE_ROLES.items():
            field = self._tag_fields.get(key)
            if not field:
                continue
            value = field.text().strip()
            if not value:
                continue
            for name in value.split(";"):
                name = name.strip()
                if not name:
                    continue
                lines.append("  <actor>")
                lines.append(f"    <name>{_xml_escape(name)}</name>")
                lines.append(f"    <role>{role}</role>")
                lines.append("  </actor>")

        lines.append(f"</{root_tag}>")
        nfo_content = "\n".join(lines) + "\n"

        # Write NFO file via SFTP
        try:
            with self._sftp.open(nfo_path, "w") as f:
                f.write(nfo_content.encode("utf-8"))

            logger.success(f"NFO saved: {os.path.basename(nfo_path)}")
            self.accept()
        except Exception as e:
            logger.error(f"NFO write error: {e}")
            QMessageBox.warning(
                self,
                "Save Failed",
                f"Failed to write .nfo file:\n{e}",
            )


def _xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
