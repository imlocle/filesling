"""
Bookmarks bar widget: displays bookmark buttons for quick folder navigation.

Provides add/remove/toggle-default bookmark functionality with visual
indicators for the default folder.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

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

        # Back button is managed by the parent: just add stretch
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

            btn = QPushButton(label)
            btn.setObjectName("bookmark_btn")
            if is_default:
                btn.setStyleSheet(
                    "QPushButton#bookmark_btn { background-color: #0077ff; "
                    "border-color: #0077ff; color: white; }"
                )
            btn.setMaximumHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(path)
            btn.clicked.connect(lambda checked, p=path: self.bookmark_clicked.emit(p))

            # Right-click → edit / set default / remove
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, p=path, b=btn: self._show_context_menu(b, p)
            )
            self._layout.insertWidget(self._layout.count() - 1, btn)

    # ------------------------------------------------------------------
    # Context menu (right-click a pill)
    # ------------------------------------------------------------------
    def _show_context_menu(self, button: QPushButton, path: str) -> None:
        """Show the right-click menu for a bookmark pill."""
        menu = QMenu(self)
        is_default = path == self._settings.get_default_bookmark()

        if is_default:
            default_action = menu.addAction("Clear Default")
        else:
            default_action = menu.addAction("Set as Default")
        edit_action = menu.addAction("Edit Path…")
        menu.addSeparator()
        remove_action = menu.addAction("Remove Bookmark")

        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is None:
            return

        if chosen == default_action:
            self.toggle_default(path)
        elif chosen == edit_action:
            self._edit_bookmark(path)
        elif chosen == remove_action:
            self._remove_bookmark(path)

    def _edit_bookmark(self, path: str) -> None:
        """Prompt for a new path and update the bookmark in place."""
        new_path, ok = QInputDialog.getText(
            self,
            "Edit Bookmark",
            "Folder path:",
            text=path,
        )
        if not ok:
            return
        new_path = new_path.strip()
        if not new_path or new_path == path:
            return

        bookmarks = self._settings.get_bookmarks()
        if new_path in bookmarks:
            QMessageBox.information(
                self,
                "Bookmark Exists",
                "A bookmark for that path already exists.",
            )
            return

        # Replace in place to preserve ordering
        updated = [new_path if b == path else b for b in bookmarks]
        self._settings.set_bookmarks(updated)

        # Move the default pointer along with the path if needed
        if path == self._settings.get_default_bookmark():
            self._settings.set_default_bookmark(new_path)

        self.refresh()

    def _remove_bookmark(self, path: str) -> None:
        """Remove a bookmark (delegates to toggle_bookmark, which removes if present)."""
        self.toggle_bookmark(path)

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
