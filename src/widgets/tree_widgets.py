from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QMimeData, QPoint, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDrag,
    QMouseEvent,
)
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from src.utils.constants import MAX_DRAG_BYTES


class DragDropTreeWidget(QTreeWidget):
    """Custom QTreeWidget that supports drag-drop, multi-select, and slow-click rename."""

    # Emitted when user slow-clicks to rename: (item, column)
    slow_click_rename = Signal(QTreeWidgetItem, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drag_start_pos: Optional[QPoint] = None

        # Slow-click rename state
        self._last_clicked_item: Optional[QTreeWidgetItem] = None
        self._pressed_item: Optional[QTreeWidgetItem] = None
        self._rename_timer = QTimer(self)
        self._rename_timer.setSingleShot(True)
        self._rename_timer.timeout.connect(self._trigger_rename)
        self._rename_pending_item: Optional[QTreeWidgetItem] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Track mouse press for potential drag or slow-click rename."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()

            # Cancel any pending rename immediately on new press
            # (rename only triggers after mouse release + delay)
            self._rename_timer.stop()
            self._rename_pending_item = None

            self._pressed_item = self.itemAt(event.pos())

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Start rename timer only on release (avoids conflict with drag)."""
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if (
                item
                and item == self._pressed_item
                and item == self._last_clicked_item
                and len(self.selectedItems()) == 1
                and self._drag_start_pos is not None
                and (event.pos() - self._drag_start_pos).manhattanLength() < 4
            ):
                # Click-release on same item without dragging: start rename timer
                self._rename_pending_item = item
                self._rename_timer.start(600)

            self._last_clicked_item = item
            self._pressed_item = None

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-click cancels rename timer and navigates."""
        self._rename_timer.stop()
        self._rename_pending_item = None
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Initiate drag when mouse moves far enough from press point."""
        if (
            not (event.buttons() & Qt.MouseButton.LeftButton)
            or self._drag_start_pos is None
        ):
            super().mouseMoveEvent(event)
            return

        # Only start drag if moved at least 4 pixels (Qt standard)
        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance < 4:
            super().mouseMoveEvent(event)
            return

        # Cancel rename if dragging
        self._rename_timer.stop()
        self._rename_pending_item = None

        # Get selected items
        selected_items = self.selectedItems()
        if not selected_items:
            super().mouseMoveEvent(event)
            return

        # Create MIME data with selected item names
        mime_data = QMimeData()
        item_names = [item.text(0) for item in selected_items]
        mime_data.setText(" | ".join(item_names))
        mime_data.setData("application/x-explorer-items", b"")

        # For external drag (to Finder): provide file URLs if available
        # For remote files, download small files to temp dir.
        # Files over 10MB are skipped (user should use right-click → Download).
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, "is_remote"):
            if parent_widget.is_remote and parent_widget.sftp:
                import atexit
                import tempfile

                # Calculate total size to decide if we should download for drag
                downloadable = []
                for item_name in item_names:
                    remote_path = os.path.join(parent_widget.current_path, item_name)
                    try:
                        st = parent_widget.sftp.stat(remote_path)
                        size = st.st_size if st.st_size else 0
                        if size <= MAX_DRAG_BYTES:
                            downloadable.append((item_name, remote_path))
                    except Exception:
                        pass  # Can't stat: skip

                if downloadable:
                    temp_dir = tempfile.mkdtemp(prefix="filesling_drag_")
                    atexit.register(
                        lambda d=temp_dir: __import__("shutil").rmtree(
                            d, ignore_errors=True
                        )
                    )
                    urls = []
                    for item_name, remote_path in downloadable:
                        local_temp = os.path.join(temp_dir, item_name)
                        try:
                            parent_widget.sftp.get(remote_path, local_temp)
                            urls.append(QUrl.fromLocalFile(local_temp))
                        except Exception:
                            pass  # Skip files that fail to download
                    if urls:
                        mime_data.setUrls(urls)
            elif not parent_widget.is_remote:
                # Local files: provide URLs directly
                urls = []
                for item_name in item_names:
                    full_path = os.path.join(parent_widget.current_path, item_name)
                    if os.path.exists(full_path):
                        urls.append(QUrl.fromLocalFile(full_path))
                if urls:
                    mime_data.setUrls(urls)

        # Start drag operation
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)

        self._drag_start_pos = None

    def _trigger_rename(self) -> None:
        """Trigger inline rename after slow-click delay."""
        if self._rename_pending_item:
            self.slow_click_rename.emit(self._rename_pending_item, 0)
            self._rename_pending_item = None


class SortableTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem that sorts the Size column numerically using stored byte values."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if column == 1:
            # Sort by raw byte value stored in UserRole
            self_bytes = self.data(1, Qt.ItemDataRole.UserRole)
            other_bytes = other.data(1, Qt.ItemDataRole.UserRole)
            self_bytes = -1 if self_bytes is None else self_bytes
            other_bytes = -1 if other_bytes is None else other_bytes
            return self_bytes < other_bytes
        # Default: case-insensitive alphabetical sort for Name column
        return self.text(column).lower() < other.text(column).lower()
