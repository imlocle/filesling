"""
Settings window with tabbed interface.
"""

import os
import uuid
from datetime import datetime

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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


class SettingsWindow(QDialog):
    """Settings dialog with tabbed interface."""

    def __init__(
        self,
        settings: Settings,
        server_mode: bool = False,
        server_id: str | None = None,
    ):
        super().__init__()
        self.setWindowTitle(f"{SOFTWARE_NAME} - Settings")
        self.setMinimumSize(500, 450)

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

        layout.addStretch()
        self.tab_widget.addTab(tab, "Connection")

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

        self.delete_after_transfer_checkbox = QCheckBox("Move to trash after transfer")
        self.delete_after_transfer_checkbox.setChecked(
            self.settings.delete_after_transfer
        )
        layout.addWidget(self.delete_after_transfer_checkbox)

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
        layout.addWidget(self.theme_combo)

        info = QLabel("Theme changes apply after saving settings.")
        info.setObjectName("secondary_label")
        layout.addWidget(info)

        layout.addStretch()
        self.tab_widget.addTab(tab, "Appearance")

    def _browse_download_dir(self) -> None:
        """Open folder picker for download directory."""
        from PySide6.QtWidgets import QFileDialog

        current = self.download_dir_input.text() or os.path.expanduser("~/Downloads")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", current
        )
        if folder:
            self.download_dir_input.setText(folder)

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    def _setup_footer(self, layout: QVBoxLayout) -> None:
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setSpacing(8)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self.save_settings)

        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)
        layout.addWidget(footer)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_settings(self):
        if self.server_mode:
            self._save_server_config()
        else:
            self._save_global_settings()

    def _save_server_config(self):
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

    def _save_global_settings(self):
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

            Settings._instance = None
            self.settings = Settings()

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
