"""
Batch rename dialog: find/replace across multiple filenames.

Shows a live preview of the requested find/replace operation.
"""

from __future__ import annotations

import os
from typing import List

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
