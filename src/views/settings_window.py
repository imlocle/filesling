"""
Settings window with tabbed interface.
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings, SettingsConfig
from src.models.errors import (
    ConfigurationSaveError,
    InvalidConfigurationError,
    IPAddressValidationError,
    PathValidationError,
    SSHKeyValidationError,
)
from src.utils.constants import (
    CONN_TYPE_ADB,
    CONN_TYPE_KEY,
    CONN_TYPE_SSH,
    DEFAULT_REMOTE_BASE_DIR,
    SOFTWARE_NAME,
)
from src.utils.logging_signal import logger
from src.widgets.connection_form_widget import ConnectionFormWidget
from src.widgets.toggle_switch import ToggleSwitch


class SettingsWindow(QDialog):
    """Settings dialog with tabbed interface."""

    def __init__(
        self,
        settings: Settings,
        server_mode: bool = False,
        server_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"{SOFTWARE_NAME} - Settings")
        self.setMinimumSize(550, 600)

        self.settings = settings
        self.server_mode = server_mode
        self.server_id = server_id
        self.server_config = {}

        if server_mode and server_id:
            self.server_config = settings.get_server(server_id) or {}

        self.server_name_input = None

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        self._setup_connection_tab()
        if not server_mode:
            self._setup_files_tab()
            self._setup_appearance_tab()

        main_layout.addWidget(self.tab_widget, stretch=1)
        self._setup_footer(main_layout)

    # ------------------------------------------------------------------
    # Connection Tab
    # ------------------------------------------------------------------
    def _setup_connection_tab(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Server name (server mode only)
        if self.server_mode:
            layout.addWidget(QLabel("Name"))
            self.server_name_input = QLineEdit(self.server_config.get("name", ""))
            self.server_name_input.setPlaceholderText("e.g., Living Room Server")
            layout.addWidget(self.server_name_input)

        # Connection form widget (handles SSH/ADB fields + test)
        config = (
            self.server_config
            if self.server_mode
            else {
                CONN_TYPE_KEY: CONN_TYPE_SSH,
                "username": self.settings.username,
                "host": self.settings.host,
                "ssh_port": self.settings.ssh_port,
                "ssh_key_path": self.settings.ssh_key_path,
                "remote_base_dir": self.settings.remote_base_dir,
            }
        )
        self.connection_form = ConnectionFormWidget(config=config)
        layout.addWidget(self.connection_form)

        # Per-server settings (server mode only)
        if self.server_mode:
            layout.addWidget(QLabel(""))
            layout.addWidget(QLabel("Server-Specific Settings"))

            # Per-server download directory
            dl_row = QHBoxLayout()
            dl_row.setSpacing(8)
            self.server_download_dir_input = QLineEdit(
                self.server_config.get("download_directory", "")
            )
            self.server_download_dir_input.setPlaceholderText(
                "Leave empty to use global setting"
            )
            dl_row.addWidget(QLabel("Download to:"))
            dl_row.addWidget(self.server_download_dir_input)
            layout.addLayout(dl_row)

            # Per-server file extension filter
            layout.addWidget(QLabel("File Extension Filter"))
            self.server_filter_input = QLineEdit(
                self.server_config.get("extension_filter", "")
            )
            self.server_filter_input.setPlaceholderText(
                "e.g., .mp4, .mkv, .avi (leave empty for all)"
            )
            layout.addWidget(self.server_filter_input)

        layout.addStretch()
        scroll.setWidget(tab)
        self.tab_widget.addTab(scroll, "Connection")

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Files & Behavior Tab
    # ------------------------------------------------------------------
    def _setup_files_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Transfer behavior
        layout.addWidget(QLabel("Transfer Behavior"))

        self.delete_after_transfer_checkbox = ToggleSwitch()
        self.delete_after_transfer_checkbox.setChecked(
            self.settings.delete_after_transfer
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Move to trash after transfer"))
        row.addStretch()
        row.addWidget(self.delete_after_transfer_checkbox)
        layout.addLayout(row)

        info = QLabel(
            "When enabled, local files are moved to the Trash after a successful upload."
        )
        info.setObjectName("secondary_label")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Download directory
        layout.addWidget(QLabel("Download Directory"))
        download_row = QHBoxLayout()
        download_row.setSpacing(8)
        self.download_dir_input = QLineEdit(self.settings.download_directory)
        self.download_dir_input.setPlaceholderText("~/Downloads")
        download_row.addWidget(self.download_dir_input)

        browse_btn = QPushButton("Browse")
        browse_btn.setMaximumWidth(80)
        browse_btn.clicked.connect(self._browse_download_dir)
        download_row.addWidget(browse_btn)
        layout.addLayout(download_row)

        self.reveal_in_finder_checkbox = ToggleSwitch()
        self.reveal_in_finder_checkbox.setChecked(
            self.settings.config.reveal_in_finder_after_download
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Open in Finder after download"))
        row.addStretch()
        row.addWidget(self.reveal_in_finder_checkbox)
        layout.addLayout(row)

        self.notify_checkbox = ToggleSwitch()
        self.notify_checkbox.setChecked(
            self.settings.config.notify_on_transfer_complete
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Notify when transfers complete"))
        row.addStretch()
        row.addWidget(self.notify_checkbox)
        layout.addLayout(row)

        self.notify_sound_checkbox = ToggleSwitch()
        self.notify_sound_checkbox.setChecked(self.settings.config.notify_sound)
        row = QHBoxLayout()
        row.addWidget(QLabel("Play sound on completion"))
        row.addStretch()
        row.addWidget(self.notify_sound_checkbox)
        layout.addLayout(row)

        self.prevent_sleep_checkbox = ToggleSwitch()
        self.prevent_sleep_checkbox.setChecked(
            self.settings.config.prevent_sleep_during_transfer
        )
        self.prevent_sleep_checkbox.setToolTip(
            "When enabled, your Mac won't go to sleep while uploads,\n"
            "downloads, or conversions are active."
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Prevent sleep during transfers"))
        row.addStretch()
        row.addWidget(self.prevent_sleep_checkbox)
        layout.addLayout(row)

        # Hide NFO files
        self.hide_nfo_checkbox = ToggleSwitch()
        self.hide_nfo_checkbox.setChecked(self.settings.config.hide_nfo_files)
        self.hide_nfo_checkbox.setToolTip(
            "When enabled, .nfo sidecar files are hidden in the file browser.\n"
            "They still exist on the server and Jellyfin still reads them."
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Hide .nfo metadata files in explorer"))
        row.addStretch()
        row.addWidget(self.hide_nfo_checkbox)
        layout.addLayout(row)

        # Detail panel
        self.detail_panel_checkbox = ToggleSwitch()
        self.detail_panel_checkbox.setChecked(self.settings.config.show_detail_panel)
        self.detail_panel_checkbox.setToolTip(
            "Show the file info panel on the right side of the explorer.\n"
            "You can always toggle it with ⌘I."
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Show detail panel on startup"))
        row.addStretch()
        row.addWidget(self.detail_panel_checkbox)
        layout.addLayout(row)

        # Skip patterns
        layout.addWidget(QLabel("Skip Patterns"))
        self.skip_patterns_input = QTextEdit(
            ", ".join(sorted(self.settings.skip_patterns))
        )
        self.skip_patterns_input.setMaximumHeight(80)
        self.skip_patterns_input.setAcceptRichText(False)
        self.skip_patterns_input.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.skip_patterns_input.setPlaceholderText(".DS_Store, Thumbs.db, ._*")
        layout.addWidget(self.skip_patterns_input)

        info = QLabel("Hidden files (starting with .) are automatically skipped.")
        info.setObjectName("secondary_label")
        layout.addWidget(info)

        layout.addStretch()
        self.tab_widget.addTab(tab, "Files")

    def _setup_appearance_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Appearance"))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Follow System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")

        current_theme = self.settings.config.theme_mode
        index = self.theme_combo.findData(current_theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        layout.addWidget(self.theme_combo)

        info = QLabel("Theme applies immediately.")
        info.setObjectName("secondary_label")
        layout.addWidget(info)

        # Export / Import
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("Configuration"))

        export_import_row = QHBoxLayout()
        export_btn = QPushButton("Export Settings")
        export_btn.clicked.connect(self._export_settings)
        export_import_row.addWidget(export_btn)

        import_btn = QPushButton("Import Settings")
        import_btn.clicked.connect(self._import_settings)
        export_import_row.addWidget(import_btn)
        layout.addLayout(export_import_row)

        info = QLabel("Export your config to share between machines.")
        info.setObjectName("secondary_label")
        layout.addWidget(info)

        layout.addStretch()
        self.tab_widget.addTab(tab, "Appearance")

    def _on_theme_changed(self, index: int) -> None:
        """Apply theme immediately when user changes the dropdown."""
        from PySide6.QtWidgets import QApplication

        from src.utils.theme import apply_theme

        theme_mode = self.theme_combo.currentData()
        app = QApplication.instance()
        if app:
            apply_theme(app, theme_mode)

    def _browse_download_dir(self) -> None:
        """Open folder picker for download directory."""
        from PySide6.QtWidgets import QFileDialog

        current = self.download_dir_input.text() or os.path.expanduser("~/Downloads")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", current
        )
        if folder:
            self.download_dir_input.setText(folder)

    def _export_settings(self) -> None:
        """Export settings to a JSON file."""
        import json

        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Settings",
            os.path.expanduser(f"~/{SOFTWARE_NAME}_settings.json"),
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            config_data = self.settings._config_to_dict()
            with open(path, "w") as f:
                json.dump(config_data, f, indent=2)
            logger.success(f"Settings exported to: {path}")
            QMessageBox.information(
                self, "Export Complete", f"Settings exported to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Failed", f"Failed to export settings:\n{e}"
            )

    def _import_settings(self) -> None:
        """Import settings from a JSON file."""
        import json

        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Settings",
            os.path.expanduser("~"),
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            with open(path, "r") as f:
                config_data = json.load(f)

            # Validate before applying
            SettingsConfig.from_json(config_data)
            self.settings.save_config(config_data)

            # Reload config in-place so all existing references stay valid
            self.settings.reload_config(config_data)

            logger.success(f"Settings imported from: {path}")
            QMessageBox.information(
                self,
                "Import Complete",
                "Settings imported successfully.\n\n"
                f"Please restart {SOFTWARE_NAME} for all changes to take effect.",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self, "Import Failed", f"Failed to import settings:\n{e}"
            )

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    def _setup_footer(self, layout: QVBoxLayout) -> None:
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setSpacing(8)
        footer_layout.setContentsMargins(16, 8, 16, 12)

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        footer_layout.addWidget(test_btn)

        footer_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self.save_settings)

        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)
        layout.addWidget(footer)

    def _test_connection(self) -> None:
        """Delegate test connection to the connection form widget."""
        if hasattr(self, "connection_form"):
            self.connection_form.test_connection()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_settings(self) -> None:
        if self.server_mode:
            self._save_server_config()
        else:
            self._save_global_settings()

    def _save_server_config(self) -> None:
        if not self.server_id:
            self.server_id = str(uuid.uuid4())[:8]

        server_name = (
            self.server_name_input.text().strip()
            if self.server_name_input
            else f"Server {self.server_id}"
        )
        if not server_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a server name.")
            return

        try:
            config = self.connection_form.get_config()
            config["name"] = server_name
            existing_config = self.settings.get_server(self.server_id) or {}
            config["bookmarks"] = existing_config.get("bookmarks", [])
            config["default_bookmark"] = existing_config.get("default_bookmark", "")

            # Per-server settings
            if hasattr(self, "server_download_dir_input"):
                dl_dir = self.server_download_dir_input.text().strip()
                if dl_dir:
                    config["download_directory"] = dl_dir
            if hasattr(self, "server_filter_input"):
                ext_filter = self.server_filter_input.text().strip()
                if ext_filter:
                    config["extension_filter"] = ext_filter

            # Validate SSH config
            if config.get(CONN_TYPE_KEY) == CONN_TYPE_SSH:
                SettingsConfig.from_json(
                    {
                        **config,
                        "skip_patterns": list(self.settings.skip_patterns),
                    }
                )
            elif config.get(CONN_TYPE_KEY) == CONN_TYPE_ADB and not config.get(
                "device_id"
            ):
                QMessageBox.warning(
                    self, "No Device", "Please connect and select a device."
                )
                return

            self.settings.add_server(self.server_id, config)
            logger.success(f"Server '{server_name}' saved")
            self.accept()

        except (
            IPAddressValidationError,
            SSHKeyValidationError,
            PathValidationError,
        ) as e:
            QMessageBox.warning(self, "Validation Error", f"{e.message}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def _save_global_settings(self) -> None:
        try:
            conn_config = self.connection_form.get_config()

            config_data = {
                "servers": self.settings.config.servers,
                "current_server_id": self.settings.config.current_server_id,
                "default_server_id": self.settings.config.default_server_id,
                "username": conn_config.get("username", ""),
                "host": conn_config.get("host", ""),
                "ssh_key_path": conn_config.get("ssh_key_path", ""),
                "ssh_port": conn_config.get("ssh_port", 22),
                "remote_base_dir": conn_config.get(
                    "remote_base_dir", DEFAULT_REMOTE_BASE_DIR
                ),
                "delete_after_transfer": self.delete_after_transfer_checkbox.isChecked(),
                "download_directory": self.download_dir_input.text().strip()
                or os.path.expanduser("~/Downloads"),
                "reveal_in_finder_after_download": self.reveal_in_finder_checkbox.isChecked(),
                "notify_on_transfer_complete": self.notify_checkbox.isChecked(),
                "notify_sound": self.notify_sound_checkbox.isChecked(),
                "hide_nfo_files": self.hide_nfo_checkbox.isChecked(),
                "show_detail_panel": self.detail_panel_checkbox.isChecked(),
                "prevent_sleep_during_transfer": self.prevent_sleep_checkbox.isChecked(),
                "skip_exit_confirm": self.settings.config.skip_exit_confirm,
                "bookmarks": self.settings.config.bookmarks,
                "skip_patterns": [
                    f.strip()
                    for f in self.skip_patterns_input.toPlainText().split(",")
                    if f.strip()
                ],
                "theme_mode": self.theme_combo.currentData(),
                "last_modified": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
            }

            SettingsConfig.from_json(config_data)
            self.settings.save_config(config_data)

            # Reload config in-place so all existing references stay valid
            self.settings.reload_config(config_data)

            logger.success("Settings saved")
            self.accept()

        except (
            IPAddressValidationError,
            SSHKeyValidationError,
            PathValidationError,
        ) as e:
            QMessageBox.warning(self, "Validation Error", f"{e.message}")
        except (InvalidConfigurationError, ConfigurationSaveError) as e:
            QMessageBox.critical(self, "Save Failed", f"{e.message}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")
