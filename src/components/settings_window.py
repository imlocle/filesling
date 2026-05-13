"""
Settings window with tabbed interface.
"""

import os
import uuid
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
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
        self.setMinimumSize(500, 500)

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

        self._setup_header(main_layout)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        self._setup_connection_tab()
        if not server_mode:
            self._setup_behavior_tab()
            self._setup_files_tab()

        main_layout.addWidget(self.tab_widget, stretch=1)
        self._setup_footer(main_layout)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    def _setup_header(self, layout: QVBoxLayout) -> None:
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-bottom: 1px solid #3e3e42;
                padding: 12px 16px;
            }
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(4)

        title = QLabel("Add Server" if self.server_mode else "Settings")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #ffffff;")
        header_layout.addWidget(title)

        layout.addWidget(header)

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
            self.server_name_input.setPlaceholderText("e.g., Living Room Pi")
            layout.addWidget(self.server_name_input)

        # Connection form widget (handles SSH/ADB fields + test)
        config = self.server_config if self.server_mode else {
            CONN_TYPE_KEY: CONN_TYPE_SSH,
            "username": self.settings.username,
            "host": self.settings.host,
            "ssh_port": self.settings.ssh_port,
            "ssh_key_path": self.settings.ssh_key_path,
            "remote_base_dir": self.settings.remote_base_dir,
        }
        self.connection_form = ConnectionFormWidget(config=config)
        layout.addWidget(self.connection_form)

        layout.addStretch()
        self.tab_widget.addTab(tab, "🔌 Connection")

    # ------------------------------------------------------------------
    # Behavior Tab
    # ------------------------------------------------------------------
    def _setup_behavior_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Transfer Behavior"))

        self.delete_after_transfer_checkbox = QCheckBox("Move to trash after transfer")
        self.delete_after_transfer_checkbox.setChecked(self.settings.delete_after_transfer)
        layout.addWidget(self.delete_after_transfer_checkbox)

        info = QLabel(
            "When enabled, local files are moved to the Trash after a successful upload."
        )
        info.setStyleSheet("color: #858585; font-size: 11px; padding: 4px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        self.tab_widget.addTab(tab, "⚙️ Behavior")

    # ------------------------------------------------------------------
    # Files Tab
    # ------------------------------------------------------------------
    def _setup_files_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("File Extensions to Transfer"))
        self.file_extensions_input = QTextEdit(
            ", ".join(sorted(self.settings.file_extensions))
        )
        self.file_extensions_input.setMaximumHeight(80)
        self.file_extensions_input.setAcceptRichText(False)
        self.file_extensions_input.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.file_extensions_input.setPlaceholderText(".mkv, .mp4, .avi, .srt")
        layout.addWidget(self.file_extensions_input)

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
        info.setStyleSheet("color: #858585; font-size: 11px; padding: 4px;")
        layout.addWidget(info)

        layout.addStretch()
        self.tab_widget.addTab(tab, "📄 Files")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    def _setup_footer(self, layout: QVBoxLayout) -> None:
        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-top: 1px solid #3e3e42;
                padding: 12px 16px;
            }
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setSpacing(8)
        footer_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("💾 Save")
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

            # Validate SSH config
            if config.get(CONN_TYPE_KEY) == CONN_TYPE_SSH:
                SettingsConfig.from_json({
                    **config,
                    "file_extensions": list(self.settings.file_extensions),
                    "skip_patterns": list(self.settings.skip_patterns),
                })
            elif config.get(CONN_TYPE_KEY) == CONN_TYPE_ADB and not config.get("device_id"):
                QMessageBox.warning(self, "No Device", "Please connect and select a device.")
                return

            self.settings.add_server(self.server_id, config)
            logger.success(f"Server '{server_name}' saved")
            self.accept()

        except (IPAddressValidationError, SSHKeyValidationError, PathValidationError) as e:
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
                "remote_base_dir": conn_config.get("remote_base_dir", DEFAULT_REMOTE_BASE_DIR),
                "delete_after_transfer": self.delete_after_transfer_checkbox.isChecked(),
                "file_extensions": [
                    ext.strip()
                    for ext in self.file_extensions_input.toPlainText().split(",")
                    if ext.strip()
                ],
                "skip_patterns": [
                    f.strip()
                    for f in self.skip_patterns_input.toPlainText().split(",")
                    if f.strip()
                ],
                "last_modified": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
            }

            SettingsConfig.from_json(config_data)
            self.settings.save_config(config_data)

            Settings._instance = None
            self.settings = Settings()

            logger.success("Settings saved")
            self.accept()

        except (IPAddressValidationError, SSHKeyValidationError, PathValidationError) as e:
            QMessageBox.warning(self, "Validation Error", f"{e.message}")
        except (InvalidConfigurationError, ConfigurationSaveError) as e:
            QMessageBox.critical(self, "Save Failed", f"{e.message}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")
