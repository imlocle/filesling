"""
Folder picker dialog — lets users choose a destination folder for move operations.

Provides a lazy-loading tree view of the remote (or local) filesystem
with auto-expansion to the current directory.
"""

from __future__ import annotations

import os
from stat import S_ISDIR
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FolderPickerDialog(QDialog):
    """
    Modal dialog for picking a destination folder.

    Shows a lazy-loading folder tree starting from root_path.
    Auto-expands to the current directory of the items being moved.
    """

    def __init__(
        self,
        parent: QWidget,
        title: str,
        label_text: str,
        root_path: str,
        current_dir: str,
        is_remote: bool,
        sftp: object = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 400)

        self._root_path = root_path
        self._is_remote = is_remote
        self._sftp = sftp
        self._selected_path: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label_text))

        # Folder tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self._tree)

        # Populate root
        root_item = QTreeWidgetItem([os.path.basename(root_path) or "/"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, root_path)
        self._tree.addTopLevelItem(root_item)
        self._load_folder(root_item, root_path)

        # Add placeholders for lazy loading
        for i in range(root_item.childCount()):
            child = root_item.child(i)
            placeholder = QTreeWidgetItem([""])
            child.addChild(placeholder)

        root_item.setExpanded(True)

        # Auto-expand to current directory
        self._expand_to_path(root_item, current_dir)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_path(self) -> Optional[str]:
        """The path selected by the user, or None if cancelled."""
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        selected = self._tree.currentItem()
        if not selected:
            return None
        return selected.data(0, Qt.ItemDataRole.UserRole)

    def _load_folder(self, parent_item: QTreeWidgetItem, path: str) -> None:
        """Load subfolders into a tree item."""
        try:
            if self._is_remote and self._sftp:
                attrs = self._sftp.listdir_attr(path)
                folders = sorted(
                    [
                        a.filename
                        for a in attrs
                        if not a.filename.startswith(".")
                        and a.st_mode is not None
                        and S_ISDIR(a.st_mode)
                    ],
                    key=str.lower,
                )
            else:
                entries = os.listdir(path)
                folders = sorted(
                    [
                        e
                        for e in entries
                        if not e.startswith(".")
                        and os.path.isdir(os.path.join(path, e))
                    ],
                    key=str.lower,
                )
            for folder in folders:
                child = QTreeWidgetItem([folder])
                child.setData(0, Qt.ItemDataRole.UserRole, os.path.join(path, folder))
                parent_item.addChild(child)
        except Exception:
            pass

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Lazy-load subfolders when expanded."""
        if item.childCount() == 1 and item.child(0).text(0) == "":
            item.removeChild(item.child(0))
            folder_path = item.data(0, Qt.ItemDataRole.UserRole)
            self._load_folder(item, folder_path)
            for i in range(item.childCount()):
                child = item.child(i)
                placeholder = QTreeWidgetItem([""])
                child.addChild(placeholder)

    def _expand_to_path(self, root_item: QTreeWidgetItem, target_path: str) -> None:
        """Expand the tree down to target_path and select it."""
        if not target_path or not target_path.startswith(self._root_path):
            return

        rel = os.path.relpath(target_path, self._root_path)
        if rel == ".":
            self._tree.setCurrentItem(root_item)
            return

        segments = rel.replace("\\", "/").split("/")
        current_item = root_item

        for segment in segments:
            current_item.setExpanded(True)

            if current_item.childCount() == 1 and current_item.child(0).text(0) == "":
                current_item.removeChild(current_item.child(0))
                folder_path = current_item.data(0, Qt.ItemDataRole.UserRole)
                self._load_folder(current_item, folder_path)
                for i in range(current_item.childCount()):
                    child = current_item.child(i)
                    placeholder = QTreeWidgetItem([""])
                    child.addChild(placeholder)

            found = False
            for i in range(current_item.childCount()):
                child = current_item.child(i)
                if child.text(0) == segment:
                    current_item = child
                    found = True
                    break

            if not found:
                break

        self._tree.setCurrentItem(current_item)
        self._tree.scrollToItem(current_item)


def show_move_dialog(
    parent: QWidget,
    src_paths: List[str],
    root_path: str,
    is_remote: bool,
    sftp: object = None,
) -> Optional[List[Tuple[str, str]]]:
    """
    Show a folder picker dialog for moving files.

    Returns a list of (src, dest) tuples, or None if cancelled.
    Filters out self-moves automatically.
    """
    count = len(src_paths)
    if count == 1:
        basename = os.path.basename(src_paths[0])
        title = f"Move '{basename}' to..."
        label = f"Select destination folder for '{basename}':"
    else:
        names = [os.path.basename(p) for p in src_paths[:3]]
        display = ", ".join(names)
        if count > 3:
            display += f" (+{count - 3} more)"
        title = f"Move {count} items to..."
        label = f"Select destination folder for {count} items:\n{display}"

    current_dir = os.path.dirname(src_paths[0])

    dialog = FolderPickerDialog(
        parent=parent,
        title=title,
        label_text=label,
        root_path=root_path,
        current_dir=current_dir,
        is_remote=is_remote,
        sftp=sftp,
    )

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    dest_dir = dialog.selected_path
    if not dest_dir:
        return None

    # Build moves, filtering out self-moves
    moves = []
    skipped = []
    for src_path in src_paths:
        basename = os.path.basename(src_path)
        dest_path = os.path.join(dest_dir, basename)
        if dest_path.startswith(src_path + "/") or src_path == dest_dir:
            skipped.append(basename)
        else:
            moves.append((src_path, dest_path))

    if skipped:
        skipped_display = ", ".join(skipped[:5])
        if len(skipped) > 5:
            skipped_display += f" (+{len(skipped) - 5} more)"
        QMessageBox.warning(
            parent,
            "Move Skipped",
            f"Cannot move items into themselves:\n{skipped_display}",
            QMessageBox.StandardButton.Ok,
        )

    return moves if moves else None
