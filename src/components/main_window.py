from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.components.settings_window import SettingsWindow
from src.config.settings import Settings
from src.controllers.main_window_controller import MainWindowController
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import SOFTWARE_NAME
from src.utils.logging_signal import logger
from src.widgets.file_explorer_widget import FileExplorerWidget


class MainWindow(QWidget):
    """
    Modern, clean main window for PiSync.

    Features:
    - Clean toolbar with icon + text buttons
    - Status bar with connection and monitoring status
    - Dual-pane file explorer
    - Activity log with timestamps
    - Progress indicator
    """

    fully_loaded = Signal()  # Emitted when window is fully initialized

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(SOFTWARE_NAME)
        self.setMinimumSize(700, 700)

        # Connection retry tracking
        self.connection_attempts = 0
        self.max_connection_attempts = 3

        # === 1. Load Settings ===
        self.settings = Settings()

        # Check if we need to show server selection / perform initial server setup
        self._should_show_server_selection()

        # Validate settings for backward compatibility and required fields
        if not self._validate_settings():
            return

        # Create controller
        self.connection_manager_service = ConnectionManagerService(self.settings)
        self.controller = MainWindowController(self, self.connection_manager_service)

        # === 2. Build Layout ===
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._setup_toolbar(main_layout)
        self._setup_status_bar(main_layout)
        self._setup_content_area(main_layout)
        self._setup_activity_log(main_layout)
        self._setup_progress_bar(main_layout)

        self.setLayout(main_layout)

        # === 3. Wire Signals ===
        self._setup_connections()

        # === 4. Connect logger ===
        logger.log_signal.connect(self.log)
        logger.progress_signal.connect(self.update_progress)

        # === 5. Signal that window is ready (after a short delay to allow UI to settle) ===
        QTimer.singleShot(100, self._emit_fully_loaded)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _emit_fully_loaded(self):
        """Emit signal that window is fully loaded and ready."""
        self.fully_loaded.emit()

        # Auto-connect after window is loaded
        QTimer.singleShot(200, self._auto_connect_and_start)

    def _auto_connect_and_start(self):
        """Automatically connect after window loads."""
        self.controller.connect()

    def _should_show_server_selection(self) -> bool:
        """
        Check if we should show server selection dialog.
        If a default server is set, skip the dialog and load it directly.

        Returns:
            True if server was selected/loaded successfully
        """
        servers = self.settings.get_servers()

        # If no servers configured, show settings to add first server
        if not servers:
            return self._show_initial_setup()

        # If a default server is set, try to load it directly (skip dialog)
        default_id = self.settings.config.default_server_id
        if default_id and default_id in servers:
            if self.settings.load_server(default_id):
                return True

        # Otherwise show selection dialog
        return self._show_server_selection()

    def _show_initial_setup(self) -> bool:
        """
        Show initial setup for new users.

        Returns:
            True if setup completed, False if cancelled
        """
        QMessageBox.information(
            self,
            "Welcome to PiSync",
            "Welcome! Let's set up your first Raspberry Pi server.",
            QMessageBox.StandardButton.Ok,
        )

        settings_window = SettingsWindow(self.settings, server_mode=True)
        if settings_window.exec() != QDialog.DialogCode.Accepted:
            QMessageBox.critical(
                self,
                "Setup Required",
                "At least one server must be configured to use PiSync.",
                QMessageBox.StandardButton.Ok,
            )
            self.close()
            return False

        # After adding first server, show selection
        return self._show_server_selection()

    def _show_server_selection(self) -> bool:
        """
        Show server selection dialog.

        Returns:
            True if server selected, False if cancelled
        """
        from src.components.server_selection_dialog import ServerSelectionDialog

        selection_dialog = ServerSelectionDialog(self)
        if selection_dialog.exec() != QDialog.DialogCode.Accepted:
            self.close()
            return False

        server_id = selection_dialog.get_selected_server_id()
        if not server_id:
            self.close()
            return False

        # Load the selected server
        if not self.settings.load_server(server_id):
            QMessageBox.critical(
                self,
                "Server Load Failed",
                "Failed to load the selected server configuration.",
                QMessageBox.StandardButton.Ok,
            )
            self.close()
            return False

        return True

    def _validate_settings(self) -> bool:
        """Validate settings for backward compatibility with old configs."""
        if not self.settings.is_valid():
            QMessageBox.warning(
                self,
                "Setup Required",
                "Please configure your settings first.",
                QMessageBox.StandardButton.Ok,
            )

            settings_window = SettingsWindow(self.settings)
            if (
                settings_window.exec() != QDialog.DialogCode.Accepted
                or not self.settings.is_valid()
            ):
                QMessageBox.critical(
                    self,
                    "Setup Failed",
                    "Settings are required to run PiSync.",
                    QMessageBox.StandardButton.Ok,
                )
                self.close()
                return False

        return True

    def handle_connection_failure(self):
        """Handle connection failure — show server selection dialog."""
        self.connection_attempts += 1

        if self.connection_attempts >= self.max_connection_attempts:
            logger.error(
                f"Connection failed after {self.max_connection_attempts} attempts"
            )

            reply = QMessageBox.question(
                self,
                "Connection Failed",
                f"Failed to connect after {self.max_connection_attempts} attempts.\n\n"
                "Would you like to select a different server?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.connection_attempts = 0
                if self._show_server_selection():
                    self.connection_manager_service = ConnectionManagerService(self.settings)
                    self.controller.connection_manager = self.connection_manager_service
                    self.controller.connect()
        else:
            logger.warn(
                f"Connection attempt {self.connection_attempts}/{self.max_connection_attempts} failed"
            )

    def change_server(self):
        """Allow user to change to a different server."""
        # Disconnect current connection
        self.connection_manager_service.disconnect()

        # Reset connection attempts
        self.connection_attempts = 0

        # Show server selection
        if self._show_server_selection():
            # Update connection manager with new settings
            self.connection_manager_service = ConnectionManagerService(self.settings)
            self.controller.connection_manager = self.connection_manager_service

            # Connect to new server
            self.controller.connect()

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------
    def _setup_connections(self) -> None:
        """Wire UI signals to controller actions."""
        self.connect_btn.clicked.connect(self.controller.connect)
        self.change_server_btn.clicked.connect(self.change_server)
        self.refresh_btn.clicked.connect(self.controller.refresh_explorers)
        self.settings_btn.clicked.connect(self.controller.open_settings)
        self.delete_btn.clicked.connect(self.controller.delete_selected_item)

        # Pi explorer
        self.pi_explorer.file_delete_requested.connect(self.controller.delete_item)
        self.pi_explorer.file_rename_requested.connect(self.controller.rename_item)
        self.pi_explorer.folder_create_requested.connect(self.controller.create_folder)
        self.pi_explorer.item_move_requested.connect(self.controller.move_item)
        self.pi_explorer.item_selected.connect(self.controller.handle_selection_changed)
        self.pi_explorer.file_opened.connect(self.controller.handle_file_open)
        self.pi_explorer.files_dropped.connect(self._handle_pi_drop)
        self.pi_explorer.remote_error.connect(
            self.controller.handle_remote_explorer_failure
        )

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------
    def _setup_toolbar(self, layout: QVBoxLayout) -> None:
        """Create modern toolbar with icon + text buttons."""
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setStyleSheet(
            """
            QFrame#toolbar {
                background-color: #252526;
                border-bottom: 1px solid #3e3e42;
                padding: 8px;
            }
        """
        )

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        # Connect button
        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.setObjectName("primary_btn")
        self.connect_btn.setMinimumHeight(36)
        self.connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Spacer
        toolbar_layout.addWidget(self.connect_btn)
        toolbar_layout.addStretch()

        # Right side buttons
        self.change_server_btn = QPushButton("🔄 Change Server")
        self.change_server_btn.setMinimumHeight(36)
        self.change_server_btn.setToolTip("Select a different server")
        self.change_server_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("icon_btn")
        self.refresh_btn.setToolTip("Refresh Explorers")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setObjectName("icon_btn")
        self.delete_btn.setToolTip("Delete Selected Item")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("icon_btn")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        toolbar_layout.addWidget(self.change_server_btn)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addWidget(self.settings_btn)

        layout.addWidget(toolbar)

    def _setup_status_bar(self, layout: QVBoxLayout) -> None:
        """Create status bar with connection and monitoring status."""
        status_bar = QFrame()
        status_bar.setObjectName("status_bar")
        status_bar.setStyleSheet(
            """
            QFrame#status_bar {
                background-color: #252526;
                border-bottom: 1px solid #3e3e42;
                padding: 6px 12px;
            }
            QLabel#connection_disconnected {
                color: #858585;
                font-weight: 500;
            }
            QLabel#connection_connected {
                color: #4ec9b0;
                font-weight: 500;
            }
        """
        )

        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 6, 12, 6)
        status_layout.setSpacing(16)

        # Connection status
        self.connection_status_label = QLabel("● Disconnected")
        self.connection_status_label.setObjectName("connection_disconnected")

        status_layout.addWidget(self.connection_status_label)
        status_layout.addStretch()

        layout.addWidget(status_bar)

    def _setup_content_area(self, layout: QVBoxLayout) -> None:
        """Create main content area with Pi file explorer."""
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(12, 12, 12, 12)

        self.pi_explorer = FileExplorerWidget(
            settings=self.settings,
            root_path=self.settings.remote_base_dir,
            title="🥧 Raspberry Pi",
            is_remote=True,
            sftp=None,
        )

        content_layout.addWidget(self.pi_explorer)
        layout.addWidget(content_container, stretch=1)

    def _setup_activity_log(self, layout: QVBoxLayout) -> None:
        """Create activity log section."""
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(12, 0, 12, 12)
        log_layout.setSpacing(6)

        # Log header
        log_header = QLabel("Activity Log")
        log_header.setObjectName("section_header")
        log_layout.addWidget(log_header)

        # Log text box
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(180)
        self.log_box.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 8px;
                font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
                font-size: 12px;
            }
        """
        )
        log_layout.addWidget(self.log_box)

        layout.addWidget(log_container)

    def _setup_progress_bar(self, layout: QVBoxLayout) -> None:
        """Create progress bar."""
        progress_container = QWidget()
        progress_layout = QVBoxLayout(progress_container)
        progress_layout.setContentsMargins(12, 0, 12, 12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimumHeight(28)

        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_container)

    # ------------------------------------------------------------------
    # Logging & Progress
    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        """Append message to activity log."""
        self.log_box.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_progress(self, value: int) -> None:
        """Update progress bar."""
        self.progress_bar.setValue(value)
        if value < 100:
            self.progress_bar.setFormat(f"Transferring... {value}%")
        else:
            self.progress_bar.setFormat("✓ Transfer Complete")
            # Reset after 2 seconds
            QTimer.singleShot(2000, lambda: self.progress_bar.setFormat(""))

    # ------------------------------------------------------------------
    # Lifecycle Events
    # ------------------------------------------------------------------
    def showEvent(self, event: QShowEvent):
        """Called when window is shown."""
        super().showEvent(event)
        # This handler itself does not force a connection; the user can connect
        # or start monitoring manually, and auto-connect/auto-start may still
        # occur elsewhere based on user settings.

    def closeEvent(self, event: QCloseEvent):
        """Called when user clicks the window's close button."""
        reply = QMessageBox.question(
            self,
            f"Exit {SOFTWARE_NAME}",
            "Are you sure you want to quit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"Closing {SOFTWARE_NAME}...")
            self.controller.shutdown()
            event.accept()
        else:
            event.ignore()

    def _handle_pi_drop(self, local_paths: list[str], remote_dir: str) -> None:
        """
        Called when user drags files/folders from Finder onto the Pi explorer.

        Delegates to ManualTransferController for handling.
        """
        self.controller.manual_transfer.transfer_to_pi(
            local_paths=local_paths, remote_destination=remote_dir
        )
