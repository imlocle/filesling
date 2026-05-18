"""
Server selection dialog for choosing which server to connect to.

Shows a list of saved servers with their connection details.
Allows adding new servers or editing existing ones.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.config.settings import Settings
from src.utils.constants import SOFTWARE_NAME
from src.utils.logging_signal import logger


class ServerSelectionDialog(QDialog):
    """Dialog for selecting which server to connect to."""

    server_selected = Signal(str)  # Emits server_id when selected

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{SOFTWARE_NAME} - Select Server")
        self.setMinimumSize(450, 350)
        self.setModal(True)

        self.settings = Settings()
        self.selected_server_id = None

        self._setup_ui()
        self._load_servers()

        # Center on screen
        self._center_on_screen()

    def _center_on_screen(self):
        """Center the dialog on the screen."""
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen().geometry()
        dialog_geometry = self.frameGeometry()
        center_point = screen.center()
        dialog_geometry.moveCenter(center_point)
        self.move(dialog_geometry.topLeft())

    def _setup_ui(self):
        """Create the dialog UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self._setup_header(main_layout)

        # Server list
        self._setup_server_list(main_layout)

        # Footer with buttons
        self._setup_footer(main_layout)

    def _setup_header(self, layout: QVBoxLayout):
        """Create header section."""
        header = QFrame()

        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(16, 12, 16, 4)

        title = QLabel("Select Server")
        title.setObjectName("section_header")
        header_layout.addWidget(title)

        subtitle = QLabel("Choose a server to connect to, or add a new one")
        subtitle.setObjectName("secondary_label")
        header_layout.addWidget(subtitle)

        layout.addWidget(header)

    def _setup_server_list(self, layout: QVBoxLayout):
        """Create server list section."""
        list_container = QFrame()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(16, 8, 16, 8)
        list_layout.setSpacing(8)

        # List widget
        self.server_list = QListWidget()
        self.server_list.itemDoubleClicked.connect(self._on_server_double_clicked)
        self.server_list.itemSelectionChanged.connect(self._on_selection_changed)

        list_layout.addWidget(self.server_list)

        # Action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._add_new_server)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_server)

        self.default_btn = QPushButton("Default")
        self.default_btn.setEnabled(False)
        self.default_btn.setToolTip("Auto-connect to this server on launch")
        self.default_btn.clicked.connect(self._set_as_default)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_server)

        action_layout.addWidget(self.add_btn)
        action_layout.addWidget(self.edit_btn)
        action_layout.addWidget(self.default_btn)
        action_layout.addWidget(self.delete_btn)
        action_layout.addStretch()

        list_layout.addLayout(action_layout)
        layout.addWidget(list_container, stretch=1)

    def _setup_footer(self, layout: QVBoxLayout):
        """Create footer with action buttons."""
        footer = QFrame()

        footer_layout = QHBoxLayout(footer)
        footer_layout.setSpacing(8)
        footer_layout.setContentsMargins(16, 8, 16, 12)
        footer_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primary_btn")
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._connect_to_server)

        footer_layout.addWidget(self.cancel_btn)
        footer_layout.addWidget(self.connect_btn)

        layout.addWidget(footer)

    def _load_servers(self):
        """Load saved servers into the list."""
        self.server_list.clear()

        servers = self.settings.get_servers()

        if not servers:
            # Show empty state
            item = QListWidgetItem(
                "No servers configured. Click 'Add New Server' to get started."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(Qt.GlobalColor.gray)
            self.server_list.addItem(item)
            return

        for server_id, server_config in servers.items():
            display_text = self._format_server_display(server_id, server_config)
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, server_id)
            self.server_list.addItem(item)

    def _format_server_display(self, server_id: str, config: dict) -> str:
        """Format server information for display."""
        name = config.get("name", server_id)
        conn_type = config.get("connection_type", "ssh")
        is_default = self.settings.config.default_server_id == server_id
        prefix = "⭐ " if is_default else ""

        if conn_type == "adb":
            device_id = config.get("device_id", "")
            return f"{prefix}{name}\n📱 USB ({device_id})"
        else:
            user = config.get("username", "")
            ip = config.get("host", "")
            return f"{prefix}{name}\n🖥 {user}@{ip}"

    def _on_selection_changed(self):
        """Handle server selection change."""
        selected_items = self.server_list.selectedItems()
        has_selection = len(selected_items) > 0

        if has_selection:
            item = selected_items[0]
            server_id = item.data(Qt.ItemDataRole.UserRole)
            has_valid_server = server_id is not None
        else:
            has_valid_server = False

        self.connect_btn.setEnabled(has_valid_server)
        self.edit_btn.setEnabled(has_valid_server)
        self.default_btn.setEnabled(has_valid_server)
        self.delete_btn.setEnabled(has_valid_server)

    def _on_server_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on server item."""
        server_id = item.data(Qt.ItemDataRole.UserRole)
        if server_id:
            self._connect_to_server()

    def _connect_to_server(self):
        """Connect to the selected server."""
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        server_id = item.data(Qt.ItemDataRole.UserRole)

        if server_id:
            self.selected_server_id = server_id
            self.server_selected.emit(server_id)
            self.accept()

    def _set_as_default(self):
        """Set the selected server as the default for auto-connect."""
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        server_id = item.data(Qt.ItemDataRole.UserRole)

        if server_id:
            self.settings.set_default_server(server_id)
            server_name = self.settings.get_server(server_id).get("name", server_id)
            logger.success(f"Default server set: {server_name}")
            # Reload list to show the star indicator
            self._load_servers()

    def _add_new_server(self):
        """Open settings to add a new server."""
        from src.components.settings_window import SettingsWindow

        settings_dialog = SettingsWindow(self.settings, server_mode=True)
        if settings_dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_servers()

    def _edit_server(self):
        """Edit the selected server."""
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        server_id = item.data(Qt.ItemDataRole.UserRole)

        if server_id:
            from src.components.settings_window import SettingsWindow

            settings_dialog = SettingsWindow(
                self.settings, server_mode=True, server_id=server_id
            )
            if settings_dialog.exec() == QDialog.DialogCode.Accepted:
                self._load_servers()

    def _delete_server(self):
        """Delete the selected server."""
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        server_id = item.data(Qt.ItemDataRole.UserRole)

        if not server_id:
            return

        servers = self.settings.get_servers()
        server_config = servers.get(server_id, {})
        server_name = server_config.get("name", server_id)

        reply = QMessageBox.question(
            self,
            "Delete Server",
            f"Are you sure you want to delete '{server_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings.delete_server(server_id)
            self._load_servers()

    def get_selected_server_id(self) -> str | None:
        """Get the ID of the selected server."""
        return self.selected_server_id
