"""
Bookmarks bar widget — displays bookmark buttons for quick folder navigation.

Provides add/remove/toggle-default bookmark functionality with visual
indicators for the default folder.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from src.config.settings import Settings


class BookmarksBar(QWidget):
    """
    Horizontal bar of bookmark buttons for quick folder navigation.

    Signals:
        bookmark_clicked(str): Emitted with the bookmark path when a button is clicked.
    """

    bookmark_clicked = Signal(str)

    def __init__(self, settings: Settings, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._settings = settings

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(4)

        # Back button is managed by the parent — just add stretch
        self._layout.addStretch()

    def refresh(self) -> None:
        """Rebuild bookmark buttons from settings."""
        # Clear existing buttons (keep the stretch at the end)
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        bookmarks = self._settings.get_bookmarks()
        if not bookmarks:
            return

        for path in bookmarks:
            name = os.path.basename(path.rstrip("/")) or path
            is_default = path == self._settings.get_default_bookmark()
            label = f"● {name}" if is_default else name

            from PySide6.QtWidgets import QPushButton

            btn = QPushButton(label)
            btn.setObjectName("bookmark_btn")
            if is_default:
                btn.setStyleSheet(
                    "QPushButton#bookmark_btn { background-color: #0077ff; "
                    "border-color: #0077ff; color: white; }"
                )
            btn.setMaximumHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, p=path: self.bookmark_clicked.emit(p))
            self._layout.insertWidget(self._layout.count() - 1, btn)

    def toggle_bookmark(self, path: str) -> None:
        """Add or remove a bookmark."""
        bookmarks = self._settings.get_bookmarks()
        if path in bookmarks:
            bookmarks.remove(path)
            if path == self._settings.get_default_bookmark():
                self._settings.set_default_bookmark("")
        else:
            bookmarks.append(path)
        self._settings.set_bookmarks(bookmarks)
        self.refresh()

    def toggle_default(self, path: str) -> None:
        """Set or clear the default bookmark for this server."""
        if path == self._settings.get_default_bookmark():
            self._settings.set_default_bookmark("")
        else:
            bookmarks = self._settings.get_bookmarks()
            if path not in bookmarks:
                bookmarks.append(path)
                self._settings.set_bookmarks(bookmarks)
            self._settings.set_default_bookmark(path)
        self.refresh()
