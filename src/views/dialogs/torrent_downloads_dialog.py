"""Manage torrent downloads running on the selected SSH server."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.models.torrent import TorrentInfo
from src.utils.file_size import format_bytes


class TorrentDownloadsDialog(QDialog):
    """Show remote torrent status and collect qBittorrent actions."""

    refresh_requested = Signal()
    add_magnet_requested = Signal(str, str)
    add_file_requested = Signal(str, str)
    pause_requested = Signal(str)
    resume_requested = Signal(str)
    remove_requested = Signal(str)
    delete_data_requested = Signal(str)
    move_requested = Signal(str, str)
    settings_requested = Signal()

    def __init__(
        self,
        parent: QWidget,
        server_name: str,
        default_path: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Remote Torrent Downloads")
        self.setMinimumSize(760, 480)
        self._torrents: dict[str, TorrentInfo] = {}
        self._busy = False
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(10000)
        self._auto_refresh_timer.timeout.connect(self.refresh_requested.emit)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel(f"Downloads on {server_name}")
        header.setObjectName("title_label")
        layout.addWidget(header)
        description = QLabel(
            "qBittorrent on the server downloads the media directly and can keep "
            "seeding after FileSling closes."
        )
        description.setWordWrap(True)
        description.setObjectName("secondary_label")
        layout.addWidget(description)

        entry_row = QHBoxLayout()
        self.magnet_input = QLineEdit()
        self.magnet_input.setPlaceholderText("Paste a magnet link")
        self.magnet_input.returnPressed.connect(self._add_magnet)
        self.add_magnet_button = QPushButton("Add Magnet")
        self.add_magnet_button.clicked.connect(self._add_magnet)
        self.add_file_button = QPushButton("Add .torrent File")
        self.add_file_button.clicked.connect(self._choose_torrent_file)
        entry_row.addWidget(self.magnet_input, stretch=1)
        entry_row.addWidget(self.add_magnet_button)
        entry_row.addWidget(self.add_file_button)
        layout.addLayout(entry_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Download folder on server"))
        self.save_path_input = QLineEdit(default_path)
        self.save_path_input.setPlaceholderText(
            "Leave empty to use qBittorrent's default folder"
        )
        path_row.addWidget(self.save_path_input, stretch=1)
        self.move_button = QPushButton("Move Selected")
        self.move_button.setToolTip(
            "Move the selected torrent and its data to this server folder"
        )
        self.move_button.clicked.connect(self._move_selected)
        path_row.addWidget(self.move_button)
        self.save_path_input.textChanged.connect(self._update_action_buttons)
        layout.addLayout(path_row)

        self.torrent_table = QTableWidget(0, 5)
        self.torrent_table.setHorizontalHeaderLabels(
            ["Name", "Status", "Progress", "Download", "Upload"]
        )
        self.torrent_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.torrent_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.torrent_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.torrent_table.verticalHeader().setVisible(False)
        header_view = self.torrent_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, self.torrent_table.columnCount()):
            header_view.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.torrent_table.itemSelectionChanged.connect(self._update_action_buttons)
        layout.addWidget(self.torrent_table, stretch=1)

        action_row = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._pause_selected)
        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self._resume_selected)
        self.remove_button = QPushButton("Remove Job, Keep Data")
        self.remove_button.clicked.connect(self._remove_selected)
        self.delete_data_button = QPushButton("Delete Job + Data")
        self.delete_data_button.clicked.connect(self._delete_selected)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        action_row.addWidget(self.pause_button)
        action_row.addWidget(self.resume_button)
        action_row.addWidget(self.remove_button)
        action_row.addWidget(self.delete_data_button)
        action_row.addStretch()
        action_row.addWidget(self.refresh_button)
        layout.addLayout(action_row)

        footer = QHBoxLayout()
        self.status_label = QLabel("Connecting to qBittorrent over SSH...")
        self.status_label.setObjectName("secondary_label")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, stretch=1)
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.settings_requested.emit)
        footer.addWidget(settings_button)
        self.settings_button = settings_button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self._hide_dialog)
        footer.addWidget(close_button)
        layout.addLayout(footer)

        self._update_action_buttons()

    def save_path(self) -> str:
        """Return the optional server-side folder entered by the user."""
        return self.save_path_input.text().strip()

    def set_torrents(self, torrents: list[TorrentInfo]) -> None:
        """Replace the visible list while preserving the selected torrent."""
        selected_hash = self.selected_hash()
        self._torrents = {torrent.hash: torrent for torrent in torrents}
        self.torrent_table.setRowCount(len(torrents))
        selected_row: Optional[int] = None
        for row, torrent in enumerate(torrents):
            values = (
                torrent.name,
                self._state_label(torrent.state, torrent.progress),
                f"{torrent.progress * 100:.1f}%",
                f"{format_bytes(torrent.download_speed)}/s",
                f"{format_bytes(torrent.upload_speed)}/s",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, torrent.hash)
                    item.setToolTip(torrent.save_path)
                elif column == 1 and torrent.state.lower() == "error":
                    item.setToolTip(
                        "qBittorrent stopped this job because of an error. "
                        "Resume to retry. If it returns to Error, check the "
                        "server folder permissions and qBittorrent logs."
                    )
                self.torrent_table.setItem(row, column, item)
            if torrent.hash == selected_hash:
                selected_row = row
        if selected_row is not None:
            self.torrent_table.selectRow(selected_row)
        self._update_action_buttons()

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_busy(
        self, busy: bool, message: str = "", allow_add: bool = False
    ) -> None:
        self._busy = busy
        if message:
            self.set_status(message)
        add_controls = (
            self.magnet_input,
            self.add_magnet_button,
            self.add_file_button,
            self.save_path_input,
        )
        for widget in add_controls:
            widget.setEnabled(not busy or allow_add)
        for widget in (
            self.move_button,
            self.refresh_button,
            self.settings_button,
        ):
            widget.setEnabled(not busy)
        self._update_action_buttons()

    def start_auto_refresh(self) -> None:
        self._auto_refresh_timer.start()

    def stop_auto_refresh(self) -> None:
        self._auto_refresh_timer.stop()

    def selected_hash(self) -> str:
        row = self.torrent_table.currentRow()
        if row < 0:
            return ""
        item = self.torrent_table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.stop_auto_refresh()
        event.ignore()
        self.hide()

    def accept(self) -> None:
        self._hide_dialog()

    def reject(self) -> None:
        self._hide_dialog()

    def _add_magnet(self) -> None:
        magnet = self.magnet_input.text().strip()
        if not magnet:
            self.set_status("Paste a magnet link first.")
            return
        self.add_magnet_requested.emit(magnet, self.save_path())

    def _hide_dialog(self) -> None:
        self.stop_auto_refresh()
        self.hide()

    def _choose_torrent_file(self) -> None:
        torrent_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a Torrent File",
            "",
            "Torrent files (*.torrent);;All files (*)",
        )
        if torrent_path:
            self.add_file_requested.emit(torrent_path, self.save_path())

    def _pause_selected(self) -> None:
        torrent_hash = self.selected_hash()
        if torrent_hash:
            self.pause_requested.emit(torrent_hash)

    def _resume_selected(self) -> None:
        torrent_hash = self.selected_hash()
        if torrent_hash:
            self.resume_requested.emit(torrent_hash)

    def _remove_selected(self) -> None:
        torrent_hash = self.selected_hash()
        if not torrent_hash:
            return
        reply = QMessageBox.question(
            self,
            "Remove Torrent Job",
            "Remove this job from qBittorrent? Downloaded files will stay on "
            "the server.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.remove_requested.emit(torrent_hash)

    def _delete_selected(self) -> None:
        torrent_hash = self.selected_hash()
        if not torrent_hash:
            return
        torrent = self._torrents[torrent_hash]
        reply = QMessageBox.question(
            self,
            "Delete Torrent and Data",
            f"Permanently delete '{torrent.name}' and all downloaded data from "
            "the server? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_data_requested.emit(torrent_hash)

    def _move_selected(self) -> None:
        torrent_hash = self.selected_hash()
        save_path = self.save_path()
        if not torrent_hash:
            return
        if not save_path:
            self.set_status("Enter a server folder before moving this torrent.")
            return

        torrent = self._torrents[torrent_hash]
        reply = QMessageBox.question(
            self,
            "Move Torrent Data",
            f"Move '{torrent.name}' and its data to:\n{save_path}?\n\n"
            "qBittorrent will manage the move and continue tracking this torrent.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.move_requested.emit(torrent_hash, save_path)

    def _update_action_buttons(self) -> None:
        torrent = self._torrents.get(self.selected_hash())
        has_selection = torrent is not None
        is_paused = bool(
            torrent
            and (
                torrent.state.lower().startswith("paused")
                or torrent.state.lower() == "error"
            )
        )
        self.pause_button.setEnabled(has_selection and not is_paused and not self._busy)
        self.resume_button.setEnabled(has_selection and is_paused and not self._busy)
        self.remove_button.setEnabled(has_selection and not self._busy)
        self.delete_data_button.setEnabled(has_selection and not self._busy)
        self.move_button.setEnabled(
            has_selection and bool(self.save_path()) and not self._busy
        )

    @staticmethod
    def _state_label(state: str, progress: float) -> str:
        normalized_state = state.lower()
        if normalized_state in ("error", "missingfiles"):
            return "Missing files" if normalized_state == "missingfiles" else "Error"
        if normalized_state.startswith("checking"):
            return "Checking"
        if progress >= 0.999:
            if normalized_state.startswith("paused"):
                return "Complete, paused"
            if normalized_state == "queuedup":
                return "Complete, queued to seed"
            if normalized_state in ("uploading", "stalledup"):
                return "Complete, seeding"
            return "Complete"
        labels = {
            "downloading": "Downloading",
            "stalleddl": "Stalled",
            "queuedl": "Queued",
            "uploading": "Seeding",
            "pauseddl": "Paused",
            "pausedup": "Paused",
            "stalledup": "Seeding, idle",
            "queuedup": "Queued to seed",
            "checkingdl": "Checking",
            "checkingup": "Checking",
            "error": "Error",
            "missingfiles": "Missing files",
        }
        return labels.get(normalized_state, state.replace("_", " ").capitalize())
