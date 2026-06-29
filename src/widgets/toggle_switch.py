"""
Toggle switch widget — macOS-style on/off switch.

A custom QCheckBox replacement that renders as a pill-shaped toggle
with a sliding circular knob, matching the macOS System Settings style.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox


class ToggleSwitch(QCheckBox):
    """
    macOS-style toggle switch.

    Drop-in replacement for QCheckBox with a pill-shaped track and
    sliding circular knob. Uses Qt property animation for smooth transitions.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(44, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Animation for knob position
        self._knob_position: float = 0.0
        self._animation = QPropertyAnimation(self, b"knob_position")
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.stateChanged.connect(self._on_state_changed)

        # Set initial position
        if self.isChecked():
            self._knob_position = 1.0

    def _get_knob_position(self) -> float:
        return self._knob_position

    def _set_knob_position(self, pos: float) -> None:
        self._knob_position = pos
        self.update()

    knob_position = Property(float, _get_knob_position, _set_knob_position)

    def _on_state_changed(self, state: int) -> None:
        """Animate the knob when toggled."""
        self._animation.stop()
        self._animation.setStartValue(self._knob_position)
        self._animation.setEndValue(1.0 if self.isChecked() else 0.0)
        self._animation.start()

    def sizeHint(self) -> QSize:
        return QSize(44, 26)

    def hitButton(self, pos) -> bool:
        """Make the entire widget clickable."""
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 2
        knob_diameter = h - (margin * 2) - 2
        track_radius = h // 2

        # Track colors
        if self._knob_position > 0.5:
            # Blend towards green
            track_color = QColor(48, 209, 88)  # #30d158 (macOS green)
        else:
            track_color = QColor(57, 57, 61)  # #39393d (dark grey)

        border_color = QColor(72, 72, 74) if self._knob_position < 0.5 else track_color

        # Draw track
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(track_color)
        painter.drawRoundedRect(QRect(1, 1, w - 2, h - 2), track_radius, track_radius)

        # Draw knob
        knob_x = (
            margin + 1 + self._knob_position * (w - knob_diameter - (margin * 2) - 2)
        )
        knob_y = margin + 1

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(int(knob_x), int(knob_y), knob_diameter, knob_diameter)

        painter.end()
