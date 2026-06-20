"""
Quick Fix dialog — repackage a video file without re-encoding.

Combines multiple fix operations (container change, timestamp repair,
subtitle removal) into a single dialog so users can apply them all at once.
All operations are instant — no video re-encoding is performed.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


@dataclass
class QuickFixOptions:
    """Options selected by the user."""

    to_mp4: bool = False
    fix_timestamps: bool = False
    strip_subtitles: bool = False


class QuickFixDialog(QDialog):
    """
    Dialog for quick video fixes (no re-encoding).

    All operations copy the video/audio streams as-is and only
    modify the container. This makes them instant regardless of file size.
    """

    def __init__(self, parent: QWidget, filename: str, current_ext: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Quick Fix — {filename}")
        self.setMinimumSize(420, 320)

        self.options = QuickFixOptions()

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
        layout.addWidget(self._subs_check)

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

    def _on_accept(self) -> None:
        self.options = QuickFixOptions(
            to_mp4=self._mp4_check.isChecked() and self._mp4_check.isEnabled(),
            fix_timestamps=self._timestamps_check.isChecked(),
            strip_subtitles=self._subs_check.isChecked(),
        )

        # Must select at least one option
        if not (
            self.options.to_mp4
            or self.options.fix_timestamps
            or self.options.strip_subtitles
        ):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "No Options Selected",
                "Select at least one fix to apply.",
            )
            return

        self.accept()
