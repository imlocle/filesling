"""
Inline rename editor — QLineEdit overlay for in-place file renaming.

Shows a text field over the tree item, commits on Enter/focus-lost,
and records the rename in activity history.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem

from src.config.settings import Settings
from src.utils.logging_signal import logger


class InlineRenameEditor:
    """
    Manages inline rename operations on a tree widget.

    Creates a QLineEdit overlay positioned over the selected item,
    commits the rename on Enter or focus loss, and handles cleanup.
    """

    def __init__(
        self,
        tree_widget: QTreeWidget,
        settings: Settings,
        is_remote: bool = False,
        sftp: object = None,
        get_current_path: Optional[callable] = None,
    ) -> None:
        self._tree = tree_widget
        self._settings = settings
        self._is_remote = is_remote
        self._sftp = sftp
        self._get_current_path = get_current_path

        # State
        self._editor: Optional[QLineEdit] = None
        self._item: Optional[QTreeWidgetItem] = None
        self._old_name: str = ""
        self.in_progress: bool = False

    def update_sftp(self, sftp: object) -> None:
        """Update the SFTP client reference (after reconnect)."""
        self._sftp = sftp

    def start(self, item: QTreeWidgetItem, column: int) -> None:
        """Start inline editing on the given item."""
        self._item = item
        self._old_name = item.text(0)
        self.in_progress = True

        rect = self._tree.visualItemRect(item)
        header_height = self._tree.header().height()

        self._editor = QLineEdit(self._tree)
        self._editor.setText(item.text(0))
        self._editor.selectAll()
        self._editor.setGeometry(
            rect.x() + 24,
            rect.y() + header_height,
            rect.width() - 24,
            rect.height(),
        )
        self._editor.show()
        self._editor.setFocus()

        self._editor.returnPressed.connect(self.commit)
        self._editor.editingFinished.connect(self.commit)

    def commit(self) -> None:
        """Commit the inline rename."""
        if not self.in_progress:
            return
        self.in_progress = False

        new_name = self._editor.text().strip() if self._editor else ""

        # Clean up editor
        if self._editor:
            self._editor.hide()
            self._editor.deleteLater()
            self._editor = None

        item = self._item
        old_name = self._old_name
        self._item = None

        if not new_name or new_name == old_name:
            return

        current_path = self._get_current_path() if self._get_current_path else ""
        old_path = os.path.join(current_path, old_name)
        new_path = os.path.join(current_path, new_name)

        try:
            if self._is_remote:
                if self._sftp:
                    self._sftp.rename(old_path, new_path)
            else:
                os.rename(old_path, new_path)

            # Update item text directly
            self._tree.blockSignals(True)
            item.setText(0, new_name)  # type: ignore
            self._tree.blockSignals(False)
            logger.success(f"Renamed: {old_name} → {new_name}")

            # Record in history
            from src.services.activity_history_service import ActivityHistoryService

            history = ActivityHistoryService()
            history.add(
                filename=old_name,
                action="rename",
                source=old_path,
                destination=new_path,
                server_name=(
                    self._settings.config.current_server_id
                    if hasattr(self._settings, "config")
                    else ""
                ),
            )
        except Exception as e:
            logger.error(f"Rename failed: {e}")

    def cancel(self) -> None:
        """Cancel inline rename without committing."""
        self.in_progress = False
        if self._editor:
            self._editor.hide()
            self._editor.deleteLater()
            self._editor = None
        self._item = None
