"""
Connection form widget — reusable SSH/ADB connection configuration form.

Used by both the "Add Server" dialog and the main Settings window.
"""

import os
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import (
    CONN_TYPE_ADB,
    CONN_TYPE_KEY,
    CONN_TYPE_SSH,
    DEFAULT_ADB_BASE_DIR,
    DEFAULT_REMOTE_BASE_DIR,
    DEFAULT_SSH_KEY_PATH,
    PLACEHOLDER_BASE_DIR,
    PLACEHOLDER_HOST,
    PLACEHOLDER_NO_DEVICES,
    PLACEHOLDER_SSH_KEY,
    PLACEHOLDER_USERNAME,
)


class ConnectionFormWidget(QWidget):
    """
    Reusable connection form with SSH and ADB support.

    Provides:
    - Connection type selector (SSH / USB)
    - SSH fields (host, username, port, key)
    - ADB device picker
    - Base directory input
    - Test connection button + status label
    """

    connection_tested = Signal(bool)  # True if test succeeded

    def __init__(self, config: Optional[dict] = None, parent=None):
        """
        Args:
            config: Existing server config dict to populate fields (or None for defaults)
        """
        super().__init__(parent)
        self._config = config or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Connection type
        layout.addWidget(QLabel("Connection Type"))
        self.connection_type_combo = QComboBox()
        self.connection_type_combo.setView(QListView())
        self.connection_type_combo.addItem("SSH (Remote Server)", CONN_TYPE_SSH)
        self.connection_type_combo.addItem("USB (Android Device)", CONN_TYPE_ADB)
        current_type = self._config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
        self.connection_type_combo.setCurrentIndex(0 if current_type == "ssh" else 1)
        self.connection_type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self.connection_type_combo)

        # --- SSH fields ---
        self.ssh_group = QWidget()
        ssh_layout = QVBoxLayout(self.ssh_group)
        ssh_layout.setContentsMargins(0, 6, 0, 0)
        ssh_layout.setSpacing(6)

        ssh_layout.addWidget(QLabel("Host"))
        self.host_input = QLineEdit(self._config.get("host", ""))
        self.host_input.setPlaceholderText(PLACEHOLDER_HOST)
        ssh_layout.addWidget(self.host_input)
        host_hint = QLabel("IP address or hostname of the server on your network")
        host_hint.setObjectName("secondary_label")
        ssh_layout.addWidget(host_hint)

        ssh_layout.addWidget(QLabel("Username"))
        self.username_input = QLineEdit(self._config.get("username", ""))
        self.username_input.setPlaceholderText(PLACEHOLDER_USERNAME)
        ssh_layout.addWidget(self.username_input)
        username_hint = QLabel("The SSH login user (e.g., pi, admin, root)")
        username_hint.setObjectName("secondary_label")
        ssh_layout.addWidget(username_hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        port_col = QVBoxLayout()
        port_col.addWidget(QLabel("Port"))
        self.ssh_port_input = QLineEdit(str(self._config.get("ssh_port", 22)))
        self.ssh_port_input.setPlaceholderText("22")
        self.ssh_port_input.setMaximumWidth(80)
        port_col.addWidget(self.ssh_port_input)
        row.addLayout(port_col)
        key_col = QVBoxLayout()
        key_col.addWidget(QLabel("SSH Key"))
        self.ssh_key_path = QLineEdit(
            self._config.get("ssh_key_path", os.path.expanduser(DEFAULT_SSH_KEY_PATH))
        )
        self.ssh_key_path.setPlaceholderText(PLACEHOLDER_SSH_KEY)
        key_col.addWidget(self.ssh_key_path)
        row.addLayout(key_col, stretch=1)
        ssh_layout.addLayout(row)
        key_hint = QLabel(
            "Path to your private key. Default is ~/.ssh/id_rsa. Port 22 is standard for SSH."
        )
        key_hint.setObjectName("secondary_label")
        key_hint.setWordWrap(True)
        ssh_layout.addWidget(key_hint)

        # Passphrase for SSH key
        ssh_layout.addWidget(QLabel("Key Passphrase (optional)"))
        self.passphrase_input = QLineEdit(self._config.get("key_passphrase", ""))
        self.passphrase_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase_input.setPlaceholderText("Leave empty if key has no passphrase")
        ssh_layout.addWidget(self.passphrase_input)

        # Password auth (alternative to key)
        ssh_layout.addWidget(QLabel("Password (alternative to SSH key)"))
        self.password_input = QLineEdit(self._config.get("password", ""))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText(
            "Leave empty to use SSH key authentication"
        )
        ssh_layout.addWidget(self.password_input)
        pw_hint = QLabel("If set, password auth is used instead of SSH key.")
        pw_hint.setObjectName("secondary_label")
        ssh_layout.addWidget(pw_hint)

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
        self.adb_device_combo.setPlaceholderText(PLACEHOLDER_NO_DEVICES)
        self._refresh_adb_devices()
        self.adb_refresh_btn = QPushButton("↻")
        self.adb_refresh_btn.setObjectName("icon_btn")
        self.adb_refresh_btn.setToolTip("Refresh devices")
        self.adb_refresh_btn.clicked.connect(self._refresh_adb_devices)
        adb_row.addWidget(self.adb_device_combo, stretch=1)
        adb_row.addWidget(self.adb_refresh_btn)
        adb_layout.addLayout(adb_row)

        adb_hint = QLabel(
            "Enable USB Debugging on your device: Settings → Developer Options → USB Debugging"
        )
        adb_hint.setObjectName("secondary_label")
        adb_hint.setWordWrap(True)
        adb_layout.addWidget(adb_hint)

        layout.addWidget(self.adb_group)

        # --- Base directory ---
        layout.addWidget(QLabel("Base Directory"))
        default_base = (
            DEFAULT_ADB_BASE_DIR
            if current_type == CONN_TYPE_ADB
            else DEFAULT_REMOTE_BASE_DIR
        )
        self.remote_base_dir_input = QLineEdit(
            self._config.get("remote_base_dir", default_base)
        )
        self.remote_base_dir_input.setPlaceholderText(PLACEHOLDER_BASE_DIR)
        layout.addWidget(self.remote_base_dir_input)

        self._base_dir_hint = QLabel()
        self._base_dir_hint.setObjectName("secondary_label")
        self._base_dir_hint.setWordWrap(True)
        self._update_base_dir_hint()
        layout.addWidget(self._base_dir_hint)

        # Show/hide
        self.adb_group.setVisible(current_type == CONN_TYPE_ADB)
        self.ssh_group.setVisible(current_type == CONN_TYPE_SSH)

        # Test connection
        test_btn = QPushButton("Test Connection")
        test_btn.setObjectName("primary_btn")
        test_btn.clicked.connect(self.test_connection)
        layout.addWidget(test_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        layout.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_connection_type(self) -> str:
        """Returns 'ssh' or 'adb'."""
        return self.connection_type_combo.currentData()

    def get_config(self) -> dict:
        """Get the current form values as a server config dict."""
        conn_type = self.get_connection_type()

        if conn_type == CONN_TYPE_ADB:
            return {
                CONN_TYPE_KEY: CONN_TYPE_ADB,
                "device_id": self.adb_device_combo.currentData() or "",
                "remote_base_dir": self.remote_base_dir_input.text().rstrip("/").strip()
                or DEFAULT_ADB_BASE_DIR,
            }
        else:
            config = {
                CONN_TYPE_KEY: CONN_TYPE_SSH,
                "username": self.username_input.text().strip(),
                "host": self.host_input.text().strip(),
                "ssh_key_path": self.ssh_key_path.text().strip(),
                "ssh_port": int(self.ssh_port_input.text().strip() or "22"),
                "remote_base_dir": self.remote_base_dir_input.text().rstrip("/").strip()
                or DEFAULT_REMOTE_BASE_DIR,
            }
            # Optional auth fields
            passphrase = self.passphrase_input.text()
            if passphrase:
                config["key_passphrase"] = passphrase
            password = self.password_input.text()
            if password:
                config["password"] = password
            return config

    def test_connection(self) -> None:
        """Test the current connection configuration."""
        self.status_label.setText("● Testing...")
        self.status_label.setObjectName("status_pending")
        self.status_label.style().polish(self.status_label)

        conn_type = self.get_connection_type()

        if conn_type == CONN_TYPE_ADB:
            self._test_adb()
        else:
            self._test_ssh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_type_changed(self, index: int) -> None:
        is_adb = self.connection_type_combo.currentData() == CONN_TYPE_ADB
        self.adb_group.setVisible(is_adb)
        self.ssh_group.setVisible(not is_adb)
        current_text = self.remote_base_dir_input.text().strip()
        if is_adb and current_text in ("", DEFAULT_REMOTE_BASE_DIR):
            self.remote_base_dir_input.setText(DEFAULT_ADB_BASE_DIR)
        elif not is_adb and current_text in ("", DEFAULT_ADB_BASE_DIR):
            self.remote_base_dir_input.setText(DEFAULT_REMOTE_BASE_DIR)
        self._update_base_dir_hint()

    def _update_base_dir_hint(self) -> None:
        """Update the hint text below Base Directory based on connection type."""
        is_adb = self.connection_type_combo.currentData() == CONN_TYPE_ADB
        if is_adb:
            self._base_dir_hint.setText(
                "Android internal storage is typically /storage/emulated/0. "
                "Common folders: Download, DCIM, Movies, Music."
            )
        else:
            self._base_dir_hint.setText(
                "The starting directory when browsing this server. "
                "Use / to browse from root."
            )

    def _refresh_adb_devices(self) -> None:
        from src.services.adb_client import get_connected_devices

        self.adb_device_combo.clear()
        saved_device_id = self._config.get("device_id", "")
        saved_name = self._config.get("name", "")

        try:
            devices = get_connected_devices()
        except Exception:
            devices = []

        if devices:
            for device in devices:
                label = f"{device['model']} ({device['id']})"
                self.adb_device_combo.addItem(label, device["id"])

            # Select the saved device if it's in the list
            if saved_device_id:
                for i in range(self.adb_device_combo.count()):
                    if self.adb_device_combo.itemData(i) == saved_device_id:
                        self.adb_device_combo.setCurrentIndex(i)
                        return
                # Saved device not in connected list — add it as disconnected
                disconnected_label = (
                    f"{saved_name} — {saved_device_id} (disconnected)"
                    if saved_name
                    else f"{saved_device_id} (disconnected)"
                )
                self.adb_device_combo.addItem(disconnected_label, saved_device_id)
                self.adb_device_combo.setCurrentIndex(self.adb_device_combo.count() - 1)
        elif saved_device_id:
            # No devices connected — show the saved device as disconnected
            disconnected_label = (
                f"{saved_name} — {saved_device_id} (disconnected)"
                if saved_name
                else f"{saved_device_id} (disconnected)"
            )
            self.adb_device_combo.addItem(disconnected_label, saved_device_id)
            self.adb_device_combo.setCurrentIndex(0)
        else:
            self.adb_device_combo.setPlaceholderText(PLACEHOLDER_NO_DEVICES)

    def _test_ssh(self) -> None:
        from src.config.settings import SettingsConfig

        class TempSettings:
            def __init__(self, config):
                self.username = config.username
                self.host = config.host
                self.ssh_key_path = config.ssh_key_path
                self.ssh_port = config.ssh_port

        config = self.get_config()
        try:
            temp_config = SettingsConfig.from_json(config)
            temp_settings = TempSettings(temp_config)
            cms = ConnectionManagerService(temp_settings)  # type: ignore
        except Exception:
            self.status_label.setText("● Invalid configuration")
            self.status_label.setObjectName("status_error")
            self.status_label.style().polish(self.status_label)
            self.connection_tested.emit(False)
            return

        if cms.test_connection():
            self.status_label.setText("● Connected successfully")
            self.status_label.setObjectName("status_success")
            self.status_label.style().polish(self.status_label)
            self.connection_tested.emit(True)
        else:
            self.status_label.setText("● Connection failed")
            self.status_label.setObjectName("status_error")
            self.status_label.style().polish(self.status_label)
            self.connection_tested.emit(False)

    def _test_adb(self) -> None:
        from src.services.adb_client import ADBClient, get_connected_devices

        devices = get_connected_devices()
        if not devices:
            self.status_label.setText("● No device connected")
            self.status_label.setObjectName("status_error")
            self.status_label.style().polish(self.status_label)
            self.connection_tested.emit(False)
            return

        device_id = self.adb_device_combo.currentData()
        if not device_id:
            device_id = devices[0]["id"]

        try:
            client = ADBClient(device_id)
            base_dir = self.remote_base_dir_input.text().strip() or DEFAULT_ADB_BASE_DIR
            client.listdir(base_dir)
            self.status_label.setText("● Device connected successfully")
            self.status_label.setObjectName("status_success")
            self.status_label.style().polish(self.status_label)
            self.connection_tested.emit(True)
        except Exception as e:
            self.status_label.setText(f"● ADB error: {str(e)[:50]}")
            self.status_label.setObjectName("status_error")
            self.status_label.style().polish(self.status_label)
            self.connection_tested.emit(False)
