"""
Batch Metadata dialog — edit shared NFO fields for multiple files at once.

Select multiple video files → fill in shared fields (Artist, Series, Season, etc.)
→ writes/updates .nfo sidecar files for all selected files in one pass.

Fields left empty are not touched. Only filled fields overwrite existing values.
Episode # supports auto-increment from a starting number.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.utils.constants import (
    METADATA_FIELD_HINTS,
    METADATA_KEY_TO_NFO,
    METADATA_NFO_TO_KEY,
    METADATA_PEOPLE_ROLES,
)
from src.utils.logging_signal import logger

# Fields shown in the batch editor (only shared/bulk-applicable fields)
BATCH_FIELDS = [
    ("artist", "Artist"),
    ("director", "Director"),
    ("album", "Album / Series"),
    ("show", "Show Name"),
    ("season_number", "Season"),
    ("sort_name", "Sort Title (start)"),
    ("episode_sort", "Episode # (start)"),
    ("date", "Date / Year"),
    ("genre", "Genre"),
    ("description", "Description"),
]


def _xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _read_existing_nfo(sftp: object, nfo_path: str) -> Dict[str, str]:
    """Read an existing NFO file and return a dict of tag → value."""
    data: Dict[str, str] = {}
    try:
        with sftp.open(nfo_path, "r") as f:  # type: ignore
            content = f.read().decode("utf-8", errors="replace")

        # Skip scene NFOs (plain text, not XML)
        if not content.strip().startswith("<?xml") and "<" not in content[:50]:
            return data

        root = ET.fromstring(content)
        for child in root:
            tag = child.tag
            text = (child.text or "").strip()
            if not text or tag == "actor":
                continue
            # Map NFO tag to our internal key
            key = METADATA_NFO_TO_KEY.get(tag, tag)
            if key == "genre":
                existing = data.get("genre", "")
                data["genre"] = f"{existing};{text}" if existing else text
            else:
                data[key] = text
    except Exception:
        pass  # File doesn't exist or can't be read — start fresh
    return data


def _build_nfo_xml(metadata: Dict[str, str]) -> str:
    """Build Jellyfin-compatible NFO XML from a metadata dict."""
    has_season = bool(metadata.get("season_number"))
    has_episode = bool(metadata.get("episode_sort"))
    has_artist = bool(metadata.get("artist"))
    has_director = bool(metadata.get("director"))

    if has_season or has_episode:
        root_tag = "episodedetails"
    elif has_artist and not has_director:
        root_tag = "musicvideo"
    else:
        root_tag = "movie"

    lines = ['<?xml version="1.0" encoding="utf-8"?>', f"<{root_tag}>"]

    for key, value in metadata.items():
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

    # Auto-generate <actor> entries
    for key, role in METADATA_PEOPLE_ROLES.items():
        value = metadata.get(key, "")
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
    return "\n".join(lines) + "\n"


class BatchMetadataDialog(QDialog):
    """
    Dialog for editing NFO metadata across multiple files at once.

    Only filled fields are applied. Empty fields preserve existing per-file values.
    Episode # auto-increments from the starting value based on file order.
    """

    def __init__(
        self,
        parent: QWidget,
        remote_paths: List[str],
        sftp: object,
    ) -> None:
        super().__init__(parent)
        self._remote_paths = sorted(remote_paths)
        self._sftp = sftp
        self._fields: Dict[str, QLineEdit] = {}

        self.setWindowTitle(f"Batch Edit Metadata — {len(remote_paths)} files")
        self.setMinimumSize(500, 520)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel(
            f"Editing metadata for <b>{len(self._remote_paths)} files</b>.\n"
            "Only filled fields will be applied. Empty fields are left unchanged."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # File list summary
        file_names = [os.path.basename(p) for p in self._remote_paths[:5]]
        if len(self._remote_paths) > 5:
            file_names.append(f"... and {len(self._remote_paths) - 5} more")
        files_label = QLabel("\n".join(file_names))
        files_label.setObjectName("secondary_label")
        files_label.setWordWrap(True)
        layout.addWidget(files_label)

        layout.addWidget(QLabel(""))

        # Scrollable fields area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        fields_widget = QWidget()
        grid = QGridLayout(fields_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        row = 0
        for key, label_text in BATCH_FIELDS:
            label = QLabel(f"{label_text}:")
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(label, row, 0)

            field = QLineEdit()
            hints = METADATA_FIELD_HINTS.get(key)
            if hints:
                field.setPlaceholderText(hints[0])
                field.setToolTip(hints[1])
            self._fields[key] = field
            grid.addWidget(field, row, 1)
            row += 1

        # Auto-increment checkbox for episode and sort title
        self._auto_increment = QCheckBox(
            "Auto-increment Episode # and Sort Title for each file"
        )
        self._auto_increment.setChecked(True)
        self._auto_increment.setToolTip(
            "If checked, each file gets an incrementing number.\n"
            "e.g., start=1 → file1 gets 1, file2 gets 2, file3 gets 3...\n"
            "Applies to both Episode # and Sort Title."
        )
        grid.addWidget(self._auto_increment, row, 0, 1, 2)
        row += 1

        scroll.setWidget(fields_widget)
        layout.addWidget(scroll, stretch=1)

        # Note
        note = QLabel(
            "Existing .nfo files will be updated (merged). New .nfo files will be created.\n"
            "Per-file values like Title are preserved unless you fill them here."
        )
        note.setObjectName("secondary_label")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Buttons
        btn_row = QWidget()
        btn_row_layout = QGridLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 8, 0, 0)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row_layout.addWidget(cancel_btn, 0, 0)

        save_btn = QPushButton(f"Save {len(self._remote_paths)} NFO Files")
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self._on_save)
        btn_row_layout.addWidget(save_btn, 0, 1)

        layout.addWidget(btn_row)

    def _on_save(self) -> None:
        """Apply batch metadata to all selected files."""
        # Collect filled fields
        batch_values: Dict[str, str] = {}
        for key, field in self._fields.items():
            value = field.text().strip()
            if value:
                batch_values[key] = value

        if not batch_values:
            QMessageBox.information(
                self,
                "No Fields Filled",
                "Fill in at least one field to apply to the selected files.",
            )
            return

        # Get episode start number
        episode_start: Optional[int] = None
        if "episode_sort" in batch_values:
            try:
                episode_start = int(batch_values["episode_sort"])
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Episode Number",
                    "Episode # must be a number (e.g., 1, 6, 10).",
                )
                return

        # Get sort title start number
        sort_title_start: Optional[int] = None
        if "sort_name" in batch_values:
            try:
                sort_title_start = int(batch_values["sort_name"])
            except ValueError:
                # Non-numeric sort title — apply as-is (no increment)
                sort_title_start = None

        success_count = 0
        error_count = 0

        for i, remote_path in enumerate(self._remote_paths):
            nfo_path = os.path.splitext(remote_path)[0] + ".nfo"

            # Read existing NFO (if any) to preserve per-file fields
            existing = _read_existing_nfo(self._sftp, nfo_path)

            # Merge batch values into existing metadata
            merged = dict(existing)
            for key, value in batch_values.items():
                if key == "episode_sort" and episode_start is not None:
                    # Auto-increment episode number
                    if self._auto_increment.isChecked():
                        merged[key] = str(episode_start + i)
                    else:
                        merged[key] = value
                elif key == "sort_name" and sort_title_start is not None:
                    # Auto-increment sort title
                    if self._auto_increment.isChecked():
                        merged[key] = str(sort_title_start + i)
                    else:
                        merged[key] = value
                else:
                    merged[key] = value

            # Auto-populate title from filename if not set
            if not merged.get("title"):
                filename = os.path.splitext(os.path.basename(remote_path))[0]
                # Strip SxxExx pattern from beginning
                import re

                title = re.sub(r"^S\d+E\d+\s*[-–—]\s*", "", filename).strip()
                if title:
                    merged["title"] = title

            # Build and write NFO
            nfo_content = _build_nfo_xml(merged)
            try:
                with self._sftp.open(nfo_path, "w") as f:  # type: ignore
                    f.write(nfo_content.encode("utf-8"))
                success_count += 1
            except Exception as e:
                logger.error(
                    f"Batch NFO write failed for {os.path.basename(nfo_path)}: {e}"
                )
                error_count += 1

        # Report results
        if error_count == 0:
            logger.success(f"Batch metadata: {success_count} NFO files saved")
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Saved {success_count} files, {error_count} failed.\n"
                "Check the diagnostics log for details.",
            )
            if success_count > 0:
                self.accept()
