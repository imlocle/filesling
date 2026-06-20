"""
Batch rename dialog — find/replace across multiple filenames.

Shows a live preview of renames, handles collisions with numeric suffixes,
and records successful renames in activity history.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from src.utils.logging_signal import logger


class BatchRenameDialog(QDialog):
    """
    Dialog for batch renaming files with find/replace.

    Shows a live preview as the user types.
    Returns (find_text, replace_text) on accept, or None on cancel.
    """

    def __init__(self, parent: QWidget, paths: List[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Batch Rename ({len(paths)} items)")
        self.setMinimumSize(450, 350)

        self._basenames = [os.path.basename(p) for p in paths]
        self.find_text: str = ""
        self.replace_text: str = ""

        layout = QVBoxLayout(self)

        # Find & Replace inputs
        grid = QGridLayout()
        grid.addWidget(QLabel("Find:"), 0, 0)
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Text to find in filenames")
        grid.addWidget(self._find_input, 0, 1)

        grid.addWidget(QLabel("Replace:"), 1, 0)
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText(
            "Replacement text (leave empty to remove)"
        )
        grid.addWidget(self._replace_input, 1, 1)
        layout.addLayout(grid)

        # Preview list
        layout.addWidget(QLabel("Preview:"))
        self._preview_list = QListWidget()
        self._preview_list.setMinimumHeight(150)
        layout.addWidget(self._preview_list)

        # Populate initial preview
        for name in self._basenames:
            self._preview_list.addItem(f"{name} → {name}")

        self._find_input.textChanged.connect(self._update_preview)
        self._replace_input.textChanged.connect(self._update_preview)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_preview(self) -> None:
        """Update preview list as user types."""
        find_text = self._find_input.text()
        self._preview_list.clear()
        for name in self._basenames:
            if find_text:
                new_name = name.replace(find_text, self._replace_input.text())
            else:
                new_name = name
            if new_name != name:
                self._preview_list.addItem(f"{name} → {new_name}")
            else:
                self._preview_list.addItem(f"{name} (unchanged)")

    def _on_accept(self) -> None:
        """Store results and accept."""
        self.find_text = self._find_input.text()
        self.replace_text = self._replace_input.text()
        self.accept()


def execute_batch_rename(
    parent: QWidget,
    paths: List[str],
    is_remote: bool,
    sftp: object = None,
    settings: object = None,
) -> int:
    """
    Show batch rename dialog and execute renames.

    Returns the number of files successfully renamed.
    """
    dialog = BatchRenameDialog(parent, paths)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return 0

    find_text = dialog.find_text
    if not find_text:
        return 0

    replace_text = dialog.replace_text

    # Perform renames with collision handling
    renamed = 0
    collisions = []
    rename_records: List[Tuple[str, str]] = []

    for path in paths:
        old_name = os.path.basename(path)
        new_name = old_name.replace(find_text, replace_text)
        if new_name == old_name:
            continue

        new_path = os.path.join(os.path.dirname(path), new_name)

        # Check collision
        exists = False
        try:
            if is_remote and sftp:
                sftp.stat(new_path)
                exists = True
            elif not is_remote:
                exists = os.path.exists(new_path)
        except (IOError, OSError):
            pass

        if exists:
            base, ext = os.path.splitext(new_name)
            suffix_num = 2
            while exists:
                candidate = f"{base}_{suffix_num}{ext}"
                candidate_path = os.path.join(os.path.dirname(path), candidate)
                exists = False
                try:
                    if is_remote and sftp:
                        sftp.stat(candidate_path)
                        exists = True
                    elif not is_remote:
                        exists = os.path.exists(candidate_path)
                except (IOError, OSError):
                    pass
                if exists:
                    suffix_num += 1
                else:
                    new_path = candidate_path
                    collisions.append(f"{new_name} → {candidate}")
                    break

        try:
            if is_remote and sftp:
                sftp.rename(path, new_path)
            elif not is_remote:
                os.rename(path, new_path)
            renamed += 1
            rename_records.append((path, new_path))
        except Exception as e:
            logger.error(f"Rename failed: {old_name}: {e}")

    if renamed == 0 and sftp is None and is_remote:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            parent,
            "Rename Failed",
            "Connection lost — no files were renamed.",
            QMessageBox.StandardButton.Ok,
        )
        return 0

    if collisions:
        logger.warn(f"Batch rename: {len(collisions)} name collisions resolved")

    if renamed > 0:
        logger.success(f"Batch rename: {renamed} files renamed")

        # Record in activity history
        from src.services.activity_history_service import ActivityHistoryService

        history = ActivityHistoryService()
        server_name = ""
        if settings and hasattr(settings, "config"):
            server_name = settings.config.current_server_id
        for old_path, new_path in rename_records:
            history.add(
                filename=os.path.basename(old_path),
                action="rename",
                source=old_path,
                destination=new_path,
                server_name=server_name,
            )

    return renamed
