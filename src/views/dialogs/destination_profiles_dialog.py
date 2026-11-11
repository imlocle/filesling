"""Dialog for creating and editing saved upload destinations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings
from src.controllers.destination_profile_controller import (
    DestinationProfileController,
)


class DestinationProfilesDialog(QDialog):
    """Manage named connection, folder, and duplicate handling presets."""

    def __init__(
        self, settings: Settings, controller: DestinationProfileController
    ) -> None:
        super().__init__()
        self._settings = settings
        self._controller = controller
        self._editing_profile_id = ""
        self.setWindowTitle("Destination Profiles")
        self.setMinimumSize(680, 440)

        layout = QVBoxLayout(self)
        content = QHBoxLayout()

        left = QVBoxLayout()
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self._load_selected_profile)
        left.addWidget(QLabel("Saved destinations"))
        left.addWidget(self.profile_list, stretch=1)
        self.new_button = QPushButton("New Destination")
        self.new_button.clicked.connect(self._start_new_profile)
        left.addWidget(self.new_button)
        content.addLayout(left, 1)

        right_widget = QWidget()
        form = QFormLayout(right_widget)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Jellyfin Movies")
        self.server_combo = QComboBox()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("/media/movies")
        self.server_combo.currentIndexChanged.connect(self._set_default_path)
        self.duplicate_combo = QComboBox()
        self.duplicate_combo.addItem("Ask each time", "ask")
        self.duplicate_combo.addItem("Skip existing files", "skip")
        self.duplicate_combo.addItem("Overwrite existing files", "overwrite")
        self.jellyfin_combo = QComboBox()
        self.jellyfin_combo.addItem("Use connection setting", None)
        self.jellyfin_combo.addItem("Scan after uploads", True)
        self.jellyfin_combo.addItem("Do not scan", False)
        form.addRow("Name", self.name_input)
        form.addRow("Connection", self.server_combo)
        form.addRow("Destination folder", self.path_input)
        form.addRow("If a file already exists", self.duplicate_combo)
        form.addRow("Jellyfin scan", self.jellyfin_combo)

        info = QLabel(
            "Profiles use the saved connection credentials. Uploads remain checksum "
            "verified. Choose whether Jellyfin scans follow the connection setting, "
            "always run, or stay off."
        )
        info.setWordWrap(True)
        info.setObjectName("secondary_label")
        form.addRow("", info)
        form.addRow(QWidget())

        actions = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected_profile)
        self.save_button = QPushButton("Save Destination")
        self.save_button.clicked.connect(self._save_profile)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.save_button)
        form.addRow(actions)
        content.addWidget(right_widget, 2)
        layout.addLayout(content, stretch=1)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(self.close_button)
        layout.addLayout(close_row)

        self._populate_servers()
        self._refresh_profile_list()
        self._start_new_profile()

    def _populate_servers(self) -> None:
        self.server_combo.blockSignals(True)
        self.server_combo.clear()
        for server_id, config in self._settings.get_servers().items():
            label = str(config.get("name") or server_id)
            self.server_combo.addItem(label, server_id)
        self.server_combo.blockSignals(False)

    def _refresh_profile_list(self, selected_id: str = "") -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected_row = -1
        for row, profile in enumerate(self._controller.list_profiles()):
            self.profile_list.addItem(profile.name)
            self.profile_list.item(row).setData(
                Qt.ItemDataRole.UserRole, profile.profile_id
            )
            if profile.profile_id == selected_id:
                selected_row = row
        self.profile_list.blockSignals(False)
        if selected_row >= 0:
            self.profile_list.setCurrentRow(selected_row)

    def _load_selected_profile(self, row: int) -> None:
        if row < 0:
            return
        item = self.profile_list.item(row)
        profile = self._controller.get_profile(
            str(item.data(Qt.ItemDataRole.UserRole))
        )
        if profile is None:
            return
        self._editing_profile_id = profile.profile_id
        self.name_input.setText(profile.name)
        self.path_input.setText(profile.remote_path)
        self._set_combo_data(self.server_combo, profile.server_id)
        self._set_combo_data(self.duplicate_combo, profile.duplicate_policy)
        self._set_combo_data(self.jellyfin_combo, profile.refresh_jellyfin)
        self.delete_button.setEnabled(True)

    def _start_new_profile(self) -> None:
        self._editing_profile_id = ""
        self.profile_list.clearSelection()
        self.profile_list.setCurrentRow(-1)
        self.name_input.clear()
        self.path_input.clear()
        self._set_combo_data(
            self.server_combo, self._settings.config.current_server_id
        )
        self._set_default_path()
        self._set_combo_data(self.duplicate_combo, "ask")
        self._set_combo_data(self.jellyfin_combo, None)
        self.delete_button.setEnabled(False)
        self.name_input.setFocus()

    def _set_default_path(self, _index: int = -1) -> None:
        if self._editing_profile_id:
            return
        server_id = str(self.server_combo.currentData() or "")
        server = self._settings.get_server(server_id) or {}
        self.path_input.setText(
            str(server.get("remote_base_dir") or self._settings.remote_base_dir)
        )

    def _save_profile(self) -> None:
        try:
            profile = self._controller.save_profile(
                profile_id=self._editing_profile_id,
                name=self.name_input.text(),
                server_id=str(self.server_combo.currentData() or ""),
                remote_path=self.path_input.text(),
                duplicate_policy=str(self.duplicate_combo.currentData() or "ask"),
                refresh_jellyfin=self.jellyfin_combo.currentData(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Destination", str(error))
            return
        except Exception as error:
            QMessageBox.critical(
                self, "Save Failed", f"Could not save destination: {error}"
            )
            return

        self._refresh_profile_list(profile.profile_id)

    def _delete_selected_profile(self) -> None:
        if not self._editing_profile_id:
            return
        reply = QMessageBox.question(
            self,
            "Delete Destination",
            f"Delete '{self.name_input.text()}'?",
            QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Delete:
            return
        try:
            self._controller.delete_profile(self._editing_profile_id)
        except Exception as error:
            QMessageBox.critical(
                self, "Delete Failed", f"Could not delete destination: {error}"
            )
            return
        self._refresh_profile_list()
        self._start_new_profile()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
