"""Animated loading indicator shared by explorer views."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget


class LoadingSpinner(QWidget):
    """A modern spinning arc loading indicator, centered over the parent widget."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setVisible(False)

        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

        # Spinner appearance
        self._arc_length = 270  # degrees
        self._line_width = 3
        self._spinner_size = 32
        self._color = QColor(0, 120, 215)  # Blue accent

    def start(self) -> None:
        """Show spinner and start animation."""
        self._angle = 0
        self.setVisible(True)
        self._timer.start(16)  # ~60fps
        self.raise_()

    def stop(self) -> None:
        """Hide spinner and stop animation."""
        self._timer.stop()
        self.setVisible(False)

    def _rotate(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Center the spinner
        cx = self.width() // 2
        cy = self.height() // 2
        half = self._spinner_size // 2

        rect = QRectF(cx - half, cy - half, self._spinner_size, self._spinner_size)

        # Draw spinning arc
        pen = QPen(
            self._color,
            self._line_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Qt uses 1/16th of a degree for arc angles
        start_angle = self._angle * 16
        span_angle = self._arc_length * 16
        painter.drawArc(rect, start_angle, span_angle)

        painter.end()
