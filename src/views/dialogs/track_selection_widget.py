"""Reusable stream selection control for subtitle and audio tracks."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class StreamTrack(Protocol):
    """Fields shared by ffprobe audio and subtitle tracks."""

    index: int
    language: str
    codec: str
    title: str


class TrackSelectionWidget(QWidget):
    """Offer an optional remove-all or keep-selected stream filter."""

    def __init__(
        self,
        stream_name: str,
        tracks: Sequence[StreamTrack],
        default_selected: set[int],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = list(tracks)
        self._expanded = False
        self._track_checks: list[tuple[int, QCheckBox]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.remove_check = QCheckBox(f"Remove {stream_name} tracks")
        layout.addWidget(self.remove_check)

        self.expand_button = QPushButton(
            f"▶ Choose which to keep ({len(self._tracks)} tracks)"
        )
        self.expand_button.setObjectName("subtle_btn")
        self.expand_button.setStyleSheet(
            "text-align: left; padding: 4px 8px; font-size: 12px;"
        )
        self.expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_button.setVisible(False)
        layout.addWidget(self.expand_button)

        self._tracks_frame = QFrame()
        self._tracks_frame.setVisible(False)
        tracks_layout = QVBoxLayout(self._tracks_frame)
        tracks_layout.setContentsMargins(24, 0, 0, 0)
        tracks_layout.setSpacing(4)
        hint = QLabel("Checked tracks will be kept:")
        hint.setObjectName("secondary_label")
        hint.setStyleSheet("font-size: 11px;")
        tracks_layout.addWidget(hint)

        for track in self._tracks:
            label = track.language
            if track.title:
                label += f": {track.title}"
            label += f" ({track.codec})"
            check = QCheckBox(label)
            check.setChecked(track.index in default_selected)
            tracks_layout.addWidget(check)
            self._track_checks.append((track.index, check))

        layout.addWidget(self._tracks_frame)
        self.remove_check.toggled.connect(self._on_remove_toggled)
        self.expand_button.clicked.connect(self._toggle_expanded)

    @property
    def expanded(self) -> bool:
        """Whether the stream list is expanded."""
        return self._expanded

    @property
    def checkboxes(self) -> list[QCheckBox]:
        """Return the per-stream selection controls in probe order."""
        return [check for _, check in self._track_checks]

    @property
    def tracks_frame(self) -> QFrame:
        """Return the expandable stream list frame."""
        return self._tracks_frame

    def toggle_expanded(self) -> None:
        """Expand or collapse the list of streams."""
        self._toggle_expanded()

    def get_selection(self) -> tuple[bool, Optional[list[int]]]:
        """Return remove-all state and optional kept stream indexes."""
        if not self.remove_check.isChecked():
            return False, None
        if not self._track_checks or not self._expanded:
            return True, None

        selected = [index for index, check in self._track_checks if check.isChecked()]
        if not selected:
            return True, None
        if len(selected) == len(self._track_checks):
            return False, None
        return False, selected

    def _on_remove_toggled(self, checked: bool) -> None:
        self.expand_button.setVisible(checked and bool(self._track_checks))
        if not checked:
            self._expanded = False
            self._tracks_frame.setVisible(False)
            self._update_button_text()

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._tracks_frame.setVisible(self._expanded)
        self._update_button_text()
        self.window().adjustSize()

    def _update_button_text(self) -> None:
        arrow = "▼" if self._expanded else "▶"
        self.expand_button.setText(
            f"{arrow} Choose which to keep ({len(self._tracks)} tracks)"
        )
