"""
Quick Fix dialog: repackage a video file without re-encoding.

Combines multiple fix operations (container change, timestamp repair,
selective audio and subtitle removal) into a single dialog so users can apply
them all at once. All operations are instant: no video re-encoding.

Features:
- Change container to MP4 (disabled if already MP4)
- Fix timestamps (regenerate PTS for correct seeking)
- Remove/keep specific subtitle tracks (collapsible picker)
- Remove/keep specific audio tracks (collapsible picker)
- English subtitles pre-checked by default

Runs on a background thread via QuickFixWorker in src/workers/.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.models.media import AudioTrack, QuickFixOptions, SubtitleTrack
from src.views.dialogs.track_selection_widget import TrackSelectionWidget


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
        audio_tracks: Optional[List[AudioTrack]] = None,
        batch_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Quick Fix: {filename}")
        self.setMinimumSize(420, 320)

        self.options = QuickFixOptions()
        self._subtitle_tracks = subtitle_tracks or []
        self._audio_tracks = audio_tracks or []
        self._batch_mode = batch_mode

        self._setup_ui(current_ext)

    def _setup_ui(self, current_ext: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel(
            "Choose the fixes to apply to all selected videos.\n"
            "The video streams are copied without re-encoding."
            if self._batch_mode
            else "Fix common video issues without re-encoding.\n"
            "The video streams are copied without re-encoding."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(QLabel(""))

        # --- Container ---
        self._mp4_check = QCheckBox("Change container to MP4")
        self._mp4_check.setToolTip(
            "Repackages the video into an MP4 file.\n\n"
            "MP4 is the most compatible format: plays on all devices,\n"
            "browsers, TVs, and media servers.\n\n"
            "Use this if your file is .mkv or .avi and some device\n"
            "won't play it. The video itself is not changed."
        )
        # Only enable if not already MP4
        if not self._batch_mode and current_ext.lower() in (".mp4", ".m4v"):
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

        # --- Stream selection ---
        subtitle_defaults = {
            track.index
            for track in self._subtitle_tracks
            if track.language.lower() in ("eng", "english")
        }
        self._subtitle_picker = TrackSelectionWidget(
            "subtitle", self._subtitle_tracks, subtitle_defaults, self
        )
        self._subtitle_picker.remove_check.setToolTip(
            "Remove embedded subtitles or choose which tracks to keep."
        )
        layout.addWidget(self._subtitle_picker)

        audio_defaults = {self._audio_tracks[0].index} if self._audio_tracks else set()
        self._audio_picker = TrackSelectionWidget(
            "audio", self._audio_tracks, audio_defaults, self
        )
        self._audio_picker.remove_check.setToolTip(
            "Remove audio or keep only the selected audio tracks."
        )
        layout.addWidget(self._audio_picker)
        if self._batch_mode:
            self._subtitle_picker.hide()
            self._audio_picker.hide()

        # Preserve aliases used by existing dialog integration code.
        self._subs_check = self._subtitle_picker.remove_check
        self._sub_expand_btn = self._subtitle_picker.expand_button
        self._sub_tracks_frame = self._subtitle_picker.tracks_frame
        self._sub_checkboxes = self._subtitle_picker.checkboxes

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

    def _toggle_sub_picker(self) -> None:
        """Expand or collapse the subtitle track list."""
        self._subtitle_picker.toggle_expanded()

    @property
    def _sub_picker_expanded(self) -> bool:
        """Compatibility access to the subtitle picker expansion state."""
        return self._subtitle_picker.expanded

    def _on_accept(self) -> None:
        strip_subtitles, keep_subtitle_indices = (
            self._subtitle_picker.get_selection()
        )
        strip_audio, keep_audio_indices = self._audio_picker.get_selection()
        if keep_subtitle_indices is not None:
            strip_subtitles = True
        if keep_audio_indices is not None:
            strip_audio = True

        self.options = QuickFixOptions(
            to_mp4=self._mp4_check.isChecked() and self._mp4_check.isEnabled(),
            fix_timestamps=self._timestamps_check.isChecked(),
            strip_subtitles=strip_subtitles,
            keep_subtitle_indices=keep_subtitle_indices,
            strip_audio=strip_audio,
            keep_audio_indices=keep_audio_indices,
        )

        # Must select at least one option
        if not (
            self.options.to_mp4
            or self.options.fix_timestamps
            or self.options.strip_subtitles
            or self.options.keep_subtitle_indices is not None
            or self.options.strip_audio
            or self.options.keep_audio_indices is not None
        ):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "No Options Selected",
                "Select at least one fix to apply.",
            )
            return

        self.accept()
