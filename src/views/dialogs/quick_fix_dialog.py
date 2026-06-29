"""
Quick Fix dialog — repackage a video file without re-encoding.

Combines multiple fix operations (container change, timestamp repair,
subtitle removal) into a single dialog so users can apply them all at once.
All operations are instant — no video re-encoding is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class SubtitleTrack:
    """Represents a subtitle stream in the video file."""

    index: int  # Stream index (relative to subtitle streams, 0-based)
    language: str  # e.g., "eng", "jpn", "ara"
    codec: str  # e.g., "ass", "srt", "subrip"
    title: str = ""  # Optional track title


@dataclass
class QuickFixOptions:
    """Options selected by the user."""

    to_mp4: bool = False
    fix_timestamps: bool = False
    strip_subtitles: bool = False
    # Selective subtitle removal: indices of subtitle streams to KEEP
    # If None, strip_subtitles controls all-or-nothing behavior
    # If a list, only these subtitle stream indices are kept
    keep_subtitle_indices: Optional[List[int]] = None


class QuickFixDialog(QDialog):
    """
    Dialog for quick video fixes (no re-encoding).

    All operations copy the video/audio streams as-is and only
    modify the container. This makes them instant regardless of file size.
    """

    def __init__(
        self,
        parent: QWidget,
        filename: str,
        current_ext: str,
        subtitle_tracks: Optional[List[SubtitleTrack]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Quick Fix — {filename}")
        self.setMinimumSize(420, 320)

        self.options = QuickFixOptions()
        self._subtitle_tracks = subtitle_tracks or []
        self._sub_checkboxes: List[QCheckBox] = []
        self._sub_picker_expanded = False

        self._setup_ui(current_ext)

    def _setup_ui(self, current_ext: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel(
            "Fix common video issues without re-encoding.\n"
            "These operations are instant — the video quality is unchanged."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(QLabel(""))

        # --- Container ---
        self._mp4_check = QCheckBox("Change container to MP4")
        self._mp4_check.setToolTip(
            "Repackages the video into an MP4 file.\n\n"
            "MP4 is the most compatible format — plays on all devices,\n"
            "browsers, TVs, and media servers.\n\n"
            "Use this if your file is .mkv or .avi and some device\n"
            "won't play it. The video itself is not changed."
        )
        # Only enable if not already MP4
        if current_ext.lower() in (".mp4", ".m4v"):
            self._mp4_check.setEnabled(False)
            self._mp4_check.setText("Change container to MP4 (already MP4)")
        layout.addWidget(self._mp4_check)

        # --- Timestamps ---
        self._timestamps_check = QCheckBox("Fix timestamps")
        self._timestamps_check.setToolTip(
            "Regenerates the internal timing data in the file.\n\n"
            "Fixes these problems:\n"
            "• Seeking jumps to wrong position\n"
            "• Duration shows wrong time (e.g., 46:00 for a 23-min video)\n"
            "• Progress bar behaves erratically\n"
            "• Player shows different time than actual position\n\n"
            "Common with downloaded MKV files from the internet."
        )
        layout.addWidget(self._timestamps_check)

        # --- Subtitles ---
        self._subs_check = QCheckBox("Remove subtitle tracks")
        self._subs_check.setToolTip(
            "Strips all subtitle streams from the file.\n\n"
            "The video and audio are untouched. Only use this if you\n"
            "don't need the embedded subtitles (e.g., you use external\n"
            ".srt files or don't need subtitles at all).\n\n"
            "Subtitles are kept by default."
        )
        self._subs_check.toggled.connect(self._on_subs_check_toggled)
        layout.addWidget(self._subs_check)

        # --- Collapsible subtitle track picker ---
        if self._subtitle_tracks:
            self._sub_picker_container = QWidget()
            self._sub_picker_container.setVisible(False)
            picker_layout = QVBoxLayout(self._sub_picker_container)
            picker_layout.setContentsMargins(24, 4, 0, 4)
            picker_layout.setSpacing(4)

            # Toggle arrow button
            self._sub_expand_btn = QPushButton(
                f"▶ Choose which to keep ({len(self._subtitle_tracks)} tracks)"
            )
            self._sub_expand_btn.setObjectName("subtle_btn")
            self._sub_expand_btn.setStyleSheet(
                "text-align: left; padding: 4px 8px; font-size: 12px;"
            )
            self._sub_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._sub_expand_btn.clicked.connect(self._toggle_sub_picker)
            self._sub_expand_btn.setVisible(False)
            layout.addWidget(self._sub_expand_btn)

            # Track checkboxes
            self._sub_tracks_frame = QFrame()
            self._sub_tracks_frame.setVisible(False)
            tracks_layout = QVBoxLayout(self._sub_tracks_frame)
            tracks_layout.setContentsMargins(24, 0, 0, 0)
            tracks_layout.setSpacing(4)

            hint = QLabel("Checked tracks will be kept:")
            hint.setObjectName("secondary_label")
            hint.setStyleSheet("font-size: 11px;")
            tracks_layout.addWidget(hint)

            for track in self._subtitle_tracks:
                label = f"{track.language}"
                if track.title:
                    label += f" — {track.title}"
                label += f" ({track.codec})"

                cb = QCheckBox(label)
                cb.setChecked(track.language.lower() in ("eng", "english"))
                self._sub_checkboxes.append(cb)
                tracks_layout.addWidget(cb)

            layout.addWidget(self._sub_tracks_frame)

        layout.addWidget(QLabel(""))

        note = QLabel(
            "The original file will be replaced. No video quality is lost\n"
            "because the video and audio streams are copied as-is."
        )
        note.setObjectName("secondary_label")
        note.setWordWrap(True)
        layout.addWidget(note)

        # --- Buttons ---
        layout.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply Fix")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_subs_check_toggled(self, checked: bool) -> None:
        """Show/hide the expand button when 'Remove subtitles' is toggled."""
        if self._subtitle_tracks:
            self._sub_expand_btn.setVisible(checked)
            if not checked:
                self._sub_picker_expanded = False
                self._sub_tracks_frame.setVisible(False)
                self._sub_expand_btn.setText(
                    f"▶ Choose which to keep ({len(self._subtitle_tracks)} tracks)"
                )

    def _toggle_sub_picker(self) -> None:
        """Expand or collapse the subtitle track list."""
        self._sub_picker_expanded = not self._sub_picker_expanded
        self._sub_tracks_frame.setVisible(self._sub_picker_expanded)
        if self._sub_picker_expanded:
            self._sub_expand_btn.setText(
                f"▼ Choose which to keep ({len(self._subtitle_tracks)} tracks)"
            )
        else:
            self._sub_expand_btn.setText(
                f"▶ Choose which to keep ({len(self._subtitle_tracks)} tracks)"
            )
        # Resize dialog to fit
        self.adjustSize()

    def _on_accept(self) -> None:
        strip_all = self._subs_check.isChecked() and self._subs_check.isEnabled()

        # Determine subtitle handling
        keep_indices = None
        if strip_all and self._subtitle_tracks and self._sub_picker_expanded:
            # User expanded the picker — use selective removal
            keep_indices = [
                i for i, cb in enumerate(self._sub_checkboxes) if cb.isChecked()
            ]
            # If all are unchecked, it's a full strip
            if not keep_indices:
                keep_indices = None  # Falls back to strip_subtitles=True
            # If all are checked, don't strip anything
            elif len(keep_indices) == len(self._subtitle_tracks):
                strip_all = False
                keep_indices = None

        self.options = QuickFixOptions(
            to_mp4=self._mp4_check.isChecked() and self._mp4_check.isEnabled(),
            fix_timestamps=self._timestamps_check.isChecked(),
            strip_subtitles=strip_all,
            keep_subtitle_indices=keep_indices,
        )

        # Must select at least one option
        if not (
            self.options.to_mp4
            or self.options.fix_timestamps
            or self.options.strip_subtitles
            or self.options.keep_subtitle_indices is not None
        ):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "No Options Selected",
                "Select at least one fix to apply.",
            )
            return

        self.accept()
