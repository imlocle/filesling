"""
Modern settings window with tabbed interface.

Organized into logical sections:
- Connection: SSH/SFTP settings
- Paths: Local and remote directories
- Behavior: Auto-start, delete after transfer, stability
- Files: Extensions and skip patterns
"""

import os
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
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import SOFTWARE_NAME
from src.utils.logging_signal import logger
from src.models.errors import (
    ConfigurationSaveError,
    InvalidConfigurationError,
    IPAddressValidationError,
    PathValidationError,
    SSHKeyValidationError,
)


class SettingsWindow(QDialog):
    """Modern settings dialog with tabbed interface."""

    def __init__(
        self,
        settings: Settings,
        server_mode: bool = False,
        server_id: str | None = None,
    ):
        super().__init__()
        self.setWindowTitle(f"{SOFTWARE_NAME} - Settings")
        self.setMinimumSize(500, 550)

        self.settings = settings
        self.server_mode = server_mode  # If True, we're adding/editing a server
        self.server_id = server_id  # If editing, this is the server ID
        self.server_config = {}  # Current server config being edited

        # If editing a server, load its config
        if server_mode and server_id:
            self.server_config = settings.get_server(server_id) or {}

        # If in server mode, show server name field
        self.server_name_input = None

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self._setup_header(main_layout)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        self._setup_connection_tab()

        # Only show behavior and files tabs if not in server mode
        if not server_mode:
            self._setup_behavior_tab()
            self._setup_files_tab()

        main_layout.addWidget(self.tab_widget, stretch=1)

        # Footer with buttons
        self._setup_footer(main_layout)

        # Test connection on load (only if not in server mode or editing existing)
        if not server_mode or server_id:
            self.test_connection()

    def _setup_header(self, layout: QVBoxLayout) -> None:
        """Create header with title and connection status."""
        header = QFrame()
        header.setStyleSheet(
            """
            QFrame {
                background-color: #252526;
                border-bottom: 1px solid #3e3e42;
                padding: 16px;
            }
        """
        )

        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(8)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #ffffff;")
        header_layout.addWidget(title)

        # Connection status
        self.connection_status_label = QLabel("● Testing connection...")
        self.connection_status_label.setStyleSheet("color: #858585; font-weight: 500;")
        header_layout.addWidget(self.connection_status_label)

        # Last modified
        self.last_mod_label = QLabel()
        self.last_mod_label.setStyleSheet("color: #858585; font-size: 11px;")
        if self.settings.last_modified:
            self.last_mod_label.setText(f"Last modified: {self.settings.last_modified}")
        else:
            self.last_mod_label.setText("Configuration not yet saved")
        header_layout.addWidget(self.last_mod_label)

        layout.addWidget(header)

    def _setup_connection_tab(self) -> None:
        """Create connection settings tab."""
        from PySide6.QtWidgets import QComboBox

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Server name (only in server mode)
        if self.server_mode:
            layout.addWidget(QLabel("Name"))
            self.server_name_input = QLineEdit(self.server_config.get("name", ""))
            self.server_name_input.setPlaceholderText("e.g., Living Room Pi")
            layout.addWidget(self.server_name_input)

        # Connection type
        from PySide6.QtWidgets import QListView
        layout.addWidget(QLabel("Connection Type"))
        self.connection_type_combo = QComboBox()
        self.connection_type_combo.setView(QListView())
        self.connection_type_combo.addItem("SSH (Remote Server)", "ssh")
        self.connection_type_combo.addItem("USB (Android Device)", "adb")
        current_type = self.server_config.get("connection_type", "ssh") if self.server_mode else "ssh"
        self.connection_type_combo.setCurrentIndex(0 if current_type == "ssh" else 1)
        self.connection_type_combo.currentIndexChanged.connect(self._on_connection_type_changed)
        layout.addWidget(self.connection_type_combo)

        # --- SSH fields ---
        self.ssh_group = QWidget()
        ssh_layout = QVBoxLayout(self.ssh_group)
        ssh_layout.setContentsMargins(0, 6, 0, 0)
        ssh_layout.setSpacing(6)

        if self.server_mode:
            username = self.server_config.get("username", "")
            host_val = self.server_config.get("host", "")
            ssh_port = self.server_config.get("ssh_port", 22)
            ssh_key = self.server_config.get("ssh_key_path", os.path.expanduser("~/.ssh/id_rsa"))
        else:
            username = self.settings.username
            host_val = self.settings.host
            ssh_port = self.settings.ssh_port
            ssh_key = self.settings.ssh_key_path

        ssh_layout.addWidget(QLabel("Host"))
        self.host_input = QLineEdit(host_val)
        self.host_input.setPlaceholderText("192.168.1.100")
        ssh_layout.addWidget(self.host_input)

        ssh_layout.addWidget(QLabel("Username"))
        self.username_input = QLineEdit(username)
        self.username_input.setPlaceholderText("pi")
        ssh_layout.addWidget(self.username_input)

        row = QHBoxLayout()
        row.setSpacing(8)
        port_col = QVBoxLayout()
        port_col.addWidget(QLabel("Port"))
        self.ssh_port_input = QLineEdit(str(ssh_port))
        self.ssh_port_input.setPlaceholderText("22")
        self.ssh_port_input.setMaximumWidth(80)
        port_col.addWidget(self.ssh_port_input)
        row.addLayout(port_col)
        key_col = QVBoxLayout()
        key_col.addWidget(QLabel("SSH Key"))
        self.ssh_key_path = QLineEdit(ssh_key)
        self.ssh_key_path.setPlaceholderText("~/.ssh/id_rsa")
        key_col.addWidget(self.ssh_key_path)
        row.addLayout(key_col, stretch=1)
        ssh_layout.addLayout(row)

        layout.addWidget(self.ssh_group)

        # --- ADB fields ---
        self.adb_group = QWidget()
        adb_layout = QVBoxLayout(self.adb_group)
        adb_layout.setContentsMargins(0, 6, 0, 0)
        adb_layout.setSpacing(6)

        adb_layout.addWidget(QLabel("Device"))
        adb_row = QHBoxLayout()
        adb_row.setSpacing(8)
        self.adb_device_combo = QComboBox()
        self.adb_device_combo.setView(QListView())
        self.adb_device_combo.setPlaceholderText("No devices detected")
        self._refresh_adb_devices()
        self.adb_refresh_btn = QPushButton("🔃")
        self.adb_refresh_btn.setObjectName("icon_btn")
        self.adb_refresh_btn.setToolTip("Refresh devices")
        self.adb_refresh_btn.clicked.connect(self._refresh_adb_devices)
        adb_row.addWidget(self.adb_device_combo, stretch=1)
        adb_row.addWidget(self.adb_refresh_btn)
        adb_layout.addLayout(adb_row)

        layout.addWidget(self.adb_group)

        # --- Base directory (shared) ---
        layout.addWidget(QLabel("Base Directory"))
        remote_base = self.server_config.get("remote_base_dir", "/mnt/external") if self.server_mode else self.settings.remote_base_dir
        self.remote_base_dir_input = QLineEdit(remote_base)
        self.remote_base_dir_input.setPlaceholderText("/mnt/external or /sdcard")
        layout.addWidget(self.remote_base_dir_input)

        # Show/hide based on type
        self.adb_group.setVisible(current_type == "adb")
        self.ssh_group.setVisible(current_type == "ssh")

        # Test connection
        test_btn = QPushButton("🔌 Test Connection")
        test_btn.setObjectName("primary_btn")
        test_btn.clicked.connect(self.test_connection)
        layout.addWidget(test_btn)

        layout.addStretch()
        self.tab_widget.addTab(tab, "🔌 Connection")

    def _on_connection_type_changed(self, index: int) -> None:
        """Show/hide connection fields based on type."""
        is_adb = self.connection_type_combo.currentData() == "adb"
        self.adb_group.setVisible(is_adb)
        self.ssh_group.setVisible(not is_adb)
        # Update base directory to sensible default for the connection type
        current_text = self.remote_base_dir_input.text().strip()
        if is_adb and current_text in ("", "/mnt/external"):
            self.remote_base_dir_input.setText("/sdcard")
        elif not is_adb and current_text in ("", "/sdcard"):
            self.remote_base_dir_input.setText("/mnt/external")

    def _refresh_adb_devices(self) -> None:
        """Refresh the list of connected ADB devices."""
        from src.services.adb_client import get_connected_devices

        self.adb_device_combo.clear()
        devices = get_connected_devices()
        if devices:
            for device in devices:
                label = f"{device['model']} ({device['id']})"
                self.adb_device_combo.addItem(label, device["id"])
        else:
            self.adb_device_combo.setPlaceholderText("No devices — plug in via USB")

    def _setup_behavior_tab(self) -> None:
        """Create behavior settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Transfer group
        transfer_group = QGroupBox("Transfer Behavior")
        transfer_layout = QFormLayout()
        transfer_layout.setSpacing(12)
        transfer_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.delete_after_transfer_checkbox = QCheckBox()
        self.delete_after_transfer_checkbox.setChecked(
            self.settings.delete_after_transfer
        )

        transfer_layout.addRow(
            "Move to trash after transfer:", self.delete_after_transfer_checkbox
        )

        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)

        # Info label
        delete_info = QLabel(
            "💡 When enabled, local files are moved to the Trash after a successful upload. "
            "They can be recovered from Trash if needed."
        )
        delete_info.setStyleSheet(
            "color: #858585; padding: 8px; background-color: #252526; border-radius: 4px;"
        )
        delete_info.setWordWrap(True)
        layout.addWidget(delete_info)

        layout.addStretch()
        self.tab_widget.addTab(tab, "⚙️ Behavior")

    def _setup_files_tab(self) -> None:
        """Create file filtering settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # File extensions group
        extensions_group = QGroupBox("File Extensions to Transfer")
        extensions_layout = QVBoxLayout()
        extensions_layout.setSpacing(8)

        extensions_label = QLabel("Only upload files with these extensions (comma-separated):")
        extensions_label.setStyleSheet("color: #858585;")
        extensions_layout.addWidget(extensions_label)

        self.file_extensions_input = QTextEdit(
            ", ".join(sorted(self.settings.file_extensions))
        )
        self.file_extensions_input.setMaximumHeight(100)
        self.file_extensions_input.setAcceptRichText(False)
        self.file_extensions_input.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.file_extensions_input.setPlaceholderText(".mkv, .mp4, .avi, .srt")
        extensions_layout.addWidget(self.file_extensions_input)

        extensions_group.setLayout(extensions_layout)
        layout.addWidget(extensions_group)

        # Skip patterns group
        skip_group = QGroupBox("Skip Patterns")
        skip_layout = QVBoxLayout()
        skip_layout.setSpacing(8)

        skip_label = QLabel("Skip files matching these patterns (comma-separated):")
        skip_label.setStyleSheet("color: #858585;")
        skip_layout.addWidget(skip_label)

        self.skip_patterns_input = QTextEdit(
            ", ".join(sorted(self.settings.skip_patterns))
        )
        self.skip_patterns_input.setMaximumHeight(100)
        self.skip_patterns_input.setAcceptRichText(False)
        self.skip_patterns_input.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.skip_patterns_input.setPlaceholderText(".DS_Store, Thumbs.db, ._*")
        skip_layout.addWidget(self.skip_patterns_input)

        skip_group.setLayout(skip_layout)
        layout.addWidget(skip_group)

        # Info label
        info_label = QLabel(
            "💡 Tip: Hidden files (starting with .) are automatically skipped"
        )
        info_label.setStyleSheet(
            "color: #858585; padding: 8px; background-color: #252526; border-radius: 4px;"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()
        self.tab_widget.addTab(tab, "📄 Files")

    def _setup_footer(self, layout: QVBoxLayout) -> None:
        """Create footer with action buttons."""
        footer = QFrame()
        footer.setStyleSheet(
            """
            QFrame {
                background-color: #252526;
                border-top: 1px solid #3e3e42;
                padding: 16px;
            }
        """
        )

        footer_layout = QHBoxLayout(footer)
        footer_layout.setSpacing(8)

        footer_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.setObjectName("primary_btn")
        self.save_btn.setMinimumHeight(36)
        self.save_btn.setMinimumWidth(140)
        self.save_btn.clicked.connect(self.save_settings)

        footer_layout.addWidget(self.cancel_btn)
        footer_layout.addWidget(self.save_btn)

        layout.addWidget(footer)

    def save_settings(self):
        """Collect UI values, validate, and save configuration."""
        if self.server_mode:
            # Save as a server configuration
            self._save_server_config()
        else:
            # Save as global settings
            self._save_global_settings()

    def _save_server_config(self):
        """Save server configuration."""
        import uuid

        # Generate server ID if new
        if not self.server_id:
            self.server_id = str(uuid.uuid4())[:8]

        server_name = (
            self.server_name_input.text().strip()
            if self.server_name_input
            else f"Server {self.server_id}"
        )

        if not server_name:
            QMessageBox.warning(
                self,
                "Missing Server Name",
                "Please enter a name for this server.",
                QMessageBox.StandardButton.Ok,
            )
            return

        try:
            connection_type = self.connection_type_combo.currentData()

            if connection_type == "adb":
                # ADB server config
                device_id = self.adb_device_combo.currentData()
                if not device_id:
                    QMessageBox.warning(
                        self,
                        "No Device Selected",
                        "Please connect an Android device and select it.",
                        QMessageBox.StandardButton.Ok,
                    )
                    return

                server_config = {
                    "name": server_name,
                    "connection_type": "adb",
                    "device_id": device_id,
                    "remote_base_dir": self.remote_base_dir_input.text()
                    .rstrip("/")
                    .strip()
                    or "/sdcard",
                }
            else:
                # SSH server config
                # Convert and validate port before building config
                ssh_port_str = self.ssh_port_input.text().strip()
                try:
                    ssh_port = int(ssh_port_str or "22")
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid SSH Port",
                        f"SSH port must be a valid integer. Got: '{ssh_port_str}'",
                        QMessageBox.StandardButton.Ok,
                    )
                    self.ssh_port_input.setFocus()
                    return

                server_config = {
                    "name": server_name,
                    "connection_type": "ssh",
                    "username": self.username_input.text().strip(),
                    "host": self.host_input.text().strip(),
                    "ssh_key_path": self.ssh_key_path.text().strip(),
                    "ssh_port": ssh_port,
                    "remote_base_dir": self.remote_base_dir_input.text()
                    .rstrip("/")
                    .strip(),
                }
                # Validate SSH config
                temp_config = {
                    **server_config,
                    "file_extensions": list(self.settings.file_extensions),
                    "skip_patterns": list(self.settings.skip_patterns),
                }
                SettingsConfig.from_json(temp_config)

            # Save the server
            self.settings.add_server(self.server_id, server_config)

            logger.success(f"Server '{server_name}' saved successfully")
            QMessageBox.information(
                self,
                "Server Saved",
                f"Server '{server_name}' has been saved successfully.",
                QMessageBox.StandardButton.Ok,
            )
            self.accept()

        except IPAddressValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid IP Address",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.tab_widget.setCurrentIndex(0)
            self.host_input.setFocus()

        except SSHKeyValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid SSH Key",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.tab_widget.setCurrentIndex(0)
            self.ssh_key_path.setFocus()

        except PathValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid Path",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.tab_widget.setCurrentIndex(1)

        except Exception as e:
            logger.error(f"Settings: Unexpected error: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred while saving server:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _save_global_settings(self):
        """Save global application settings."""
        try:
            # Build new config data from UI inputs, preserving all existing fields
            config_data = {
                "servers": self.settings.config.servers,  # Keep existing servers
                "current_server_id": self.settings.config.current_server_id,
                "default_server_id": self.settings.config.default_server_id,
                "username": self.username_input.text().strip(),
                "host": self.host_input.text().strip(),
                "ssh_key_path": self.ssh_key_path.text().strip(),
                "ssh_port": int(self.ssh_port_input.text().strip() or "22"),
                "remote_base_dir": self.remote_base_dir_input.text()
                .rstrip("/")
                .strip(),
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

            # Validate configuration
            validated_config = SettingsConfig.from_json(config_data)

            # Save to file with complete config (preserves servers)
            self.settings.save_config(config_data)

            # Reload settings to update in-memory config
            # The Settings singleton will reload from the saved file
            Settings._instance = None  # Reset singleton
            self.settings = Settings()  # Reload from saved config

            logger.success("Settings saved successfully")
            QMessageBox.information(
                self,
                "Settings Saved",
                "Your settings have been saved successfully.",
                QMessageBox.StandardButton.Ok,
            )
            self.accept()

        except IPAddressValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid IP Address",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.tab_widget.setCurrentIndex(0)  # Switch to Connection tab
            self.host_input.setFocus()

        except SSHKeyValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid SSH Key",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.tab_widget.setCurrentIndex(0)  # Switch to Connection tab
            self.ssh_key_path.setFocus()

        except PathValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid Path",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.tab_widget.setCurrentIndex(1)  # Switch to Paths tab

        except InvalidConfigurationError as e:
            QMessageBox.critical(
                self,
                "Configuration Error",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )

        except ConfigurationSaveError as e:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )

        except Exception as e:
            logger.error(f"Settings: Unexpected error: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred while saving settings:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def test_connection(self):
        """Test connection to remote server or USB device."""
        self.connection_status_label.setText("● Testing connection...")
        self.connection_status_label.setStyleSheet("color: #ce9178; font-weight: 500;")

        # Check if ADB connection type
        if hasattr(self, 'connection_type_combo') and self.connection_type_combo.currentData() == "adb":
            self._test_adb_connection()
            return

        # SSH connection test
        if self.server_mode:
            from src.config.settings import SettingsConfig

            class TempSettings:
                def __init__(self, config: SettingsConfig):
                    self.config = config
                    self.username = config.username
                    self.host = config.host
                    self.ssh_key_path = config.ssh_key_path
                    self.ssh_port = config.ssh_port

            temp_config_data = {
                "username": self.username_input.text().strip(),
                "host": self.host_input.text().strip(),
                "ssh_key_path": self.ssh_key_path.text().strip(),
                "ssh_port": int(self.ssh_port_input.text().strip() or "22"),
                "remote_base_dir": self.remote_base_dir_input.text().strip()
                or "/mnt/external",
            }
            try:
                temp_config = SettingsConfig.from_json(temp_config_data)
                temp_settings = TempSettings(temp_config)
                connection_manager_service = ConnectionManagerService(temp_settings)
            except Exception as e:
                self.connection_status_label.setText("● Invalid configuration")
                self.connection_status_label.setStyleSheet("color: #f48771; font-weight: 500;")
                return
        else:
            connection_manager_service = ConnectionManagerService(self.settings)

        if connection_manager_service.test_connection():
            self.connection_status_label.setText("● Connected successfully")
            self.connection_status_label.setStyleSheet("color: #4ec9b0; font-weight: 500;")
        else:
            self.connection_status_label.setText("● Connection failed")
            self.connection_status_label.setStyleSheet("color: #f48771; font-weight: 500;")

    def _test_adb_connection(self):
        """Test ADB connection to Android device."""
        from src.services.adb_client import ADBClient, get_connected_devices

        devices = get_connected_devices()
        if not devices:
            self.connection_status_label.setText("● No device connected")
            self.connection_status_label.setStyleSheet("color: #f48771; font-weight: 500;")
            return

        device_id = self.adb_device_combo.currentData()
        if not device_id:
            device_id = devices[0]["id"]

        try:
            client = ADBClient(device_id)
            base_dir = self.remote_base_dir_input.text().strip() or "/sdcard"
            client.listdir(base_dir)
            self.connection_status_label.setText("● Device connected successfully")
            self.connection_status_label.setStyleSheet("color: #4ec9b0; font-weight: 500;")
        except Exception as e:
            self.connection_status_label.setText(f"● ADB error: {str(e)[:50]}")
            self.connection_status_label.setStyleSheet("color: #f48771; font-weight: 500;")
