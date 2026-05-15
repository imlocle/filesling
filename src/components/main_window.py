from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.components.settings_window import SettingsWindow
from src.config.settings import Settings
from src.controllers.main_window_controller import MainWindowController
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import (
    DIALOG_FILES_ALREADY_EXIST,
    DIALOG_SETUP_FAILED,
    DIALOG_SETUP_REQUIRED,
    DUP_ACTION_CANCEL,
    DUP_ACTION_OVERWRITE,
    DUP_ACTION_SKIP,
    SOFTWARE_NAME,
)
from src.utils.logging_signal import logger
from src.widgets.file_explorer_widget import FileExplorerWidget


class MainWindow(QWidget):
    """
    Main window for Shuttle — a remote file manager.

    Features:
    - Clean toolbar with connection controls
    - Status bar with connection status
    - Remote file explorer with drag-and-drop upload
    - Activity log with timestamps
    - Progress indicator
    """

    fully_loaded = Signal()  # Emitted when window is fully initialized

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(SOFTWARE_NAME)
        self.setMinimumSize(700, 900)

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
        self._setup_shortcuts()

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
            "Welcome to Shuttle",
            "Welcome! Let's set up your first server connection.",
            QMessageBox.StandardButton.Ok,
        )

        settings_window = SettingsWindow(self.settings, server_mode=True)
        if settings_window.exec() != QDialog.DialogCode.Accepted:
            QMessageBox.critical(
                self,
                DIALOG_SETUP_REQUIRED,
                "At least one server must be configured to use Shuttle.",
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
                DIALOG_SETUP_REQUIRED,
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
                    DIALOG_SETUP_FAILED,
                    "Settings are required to run Shuttle.",
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
                    self.connection_manager_service = ConnectionManagerService(
                        self.settings
                    )
                    self.controller.connection_manager = self.connection_manager_service
                    self.controller.connect()
        else:
            logger.warn(
                f"Connection attempt {self.connection_attempts}/{self.max_connection_attempts} failed"
            )

    def change_server(self):
        """Allow user to change to a different server."""
        from src.components.server_selection_dialog import ServerSelectionDialog

        selection_dialog = ServerSelectionDialog(self)
        if selection_dialog.exec() != QDialog.DialogCode.Accepted:
            # User cancelled — reconnect to current server
            return

        server_id = selection_dialog.get_selected_server_id()
        if not server_id:
            return

        if not self.settings.load_server(server_id):
            return

        # Disconnect current connection
        self.connection_manager_service.disconnect()
        self.connection_attempts = 0

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

        # Explorer
        self.remote_explorer.file_delete_requested.connect(self.controller.delete_item)
        self.remote_explorer.file_rename_requested.connect(self.controller.rename_item)
        self.remote_explorer.file_download_requested.connect(
            self.controller.download_item
        )
        self.remote_explorer.folder_create_requested.connect(
            self.controller.create_folder
        )
        self.remote_explorer.item_move_requested.connect(self.controller.move_item)
        self.remote_explorer.item_selected.connect(
            self.controller.handle_selection_changed
        )
        self.remote_explorer.file_opened.connect(self.controller.handle_file_open)
        self.remote_explorer.files_dropped.connect(self._handle_remote_drop)
        self.remote_explorer.remote_error.connect(
            self.controller.handle_remote_explorer_failure
        )

    # ------------------------------------------------------------------
    # Keyboard Shortcuts (macOS)
    # ------------------------------------------------------------------
    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # ⌘+Backspace — Delete selected items
        QShortcut(QKeySequence("Ctrl+Backspace"), self).activated.connect(
            self.controller.delete_selected_item
        )

        # ⌘+R — Refresh explorer
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            self.controller.refresh_explorers
        )

        # Enter — Navigate into selected folder (only when search bar not focused)
        self._enter_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self._enter_shortcut.activated.connect(self._navigate_or_search)

        # ⌘+Up — Go back / up one directory
        QShortcut(QKeySequence("Ctrl+Up"), self).activated.connect(
            self.remote_explorer.go_back
        )

        # ⌘+N — New folder
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            self._create_folder_shortcut
        )

        # ⌘+F — Focus search/filter
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self.remote_explorer.show_search
        )

        # Escape — Deselect all / hide search
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            self._handle_escape
        )

    def _navigate_selected(self) -> None:
        """Navigate into the selected folder."""
        items = self.remote_explorer.tree_widget.selectedItems()
        if items and len(items) == 1:
            self.remote_explorer.navigate(items[0])

    def _navigate_or_search(self) -> None:
        """Enter key: if renaming, commit it. If search bar focused, search. Otherwise navigate."""
        if self.remote_explorer._rename_in_progress:
            self.remote_explorer._commit_rename()
            return
        if self.remote_explorer._search_bar.hasFocus():
            self.remote_explorer._execute_search()
        else:
            self._navigate_selected()

    def _create_folder_shortcut(self) -> None:
        """Trigger new folder creation in current directory."""
        self.remote_explorer._prompt_and_create_folder()

    def _deselect_all(self) -> None:
        """Clear selection in the explorer."""
        self.remote_explorer.tree_widget.clearSelection()

    def _handle_escape(self) -> None:
        """Escape: clear search if active, otherwise deselect."""
        if self.remote_explorer._search_bar.text():
            self.remote_explorer.hide_search()
        else:
            self._deselect_all()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------
    def _setup_toolbar(self, layout: QVBoxLayout) -> None:
        """Create modern toolbar with icon buttons."""
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setStyleSheet("""
            QFrame#toolbar {
                background-color: transparent;
                border: none;
                padding: 8px;
            }
        """)

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        # Left side buttons
        self.connect_btn = QPushButton("🔌")
        self.connect_btn.setObjectName("icon_btn")
        self.connect_btn.setToolTip("Connect")
        self.connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.change_server_btn = QPushButton("🔄")
        self.change_server_btn.setObjectName("icon_btn")
        self.change_server_btn.setToolTip("Change Server")
        self.change_server_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        toolbar_layout.addWidget(self.connect_btn)
        toolbar_layout.addWidget(self.change_server_btn)
        toolbar_layout.addStretch()

        # Right side buttons
        self.refresh_btn = QPushButton("🔃")
        self.refresh_btn.setObjectName("icon_btn")
        self.refresh_btn.setToolTip("Refresh")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setObjectName("icon_btn")
        self.delete_btn.setToolTip("Delete Selected Item")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setObjectName("icon_btn")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addWidget(self.settings_btn)

        layout.addWidget(toolbar)

    def _setup_status_bar(self, layout: QVBoxLayout) -> None:
        """Create status bar with connection and monitoring status."""
        status_bar = QFrame()
        status_bar.setObjectName("status_bar")
        status_bar.setStyleSheet("""
            QFrame#status_bar {
                background-color: rgba(30, 41, 59, 0.5);
                border: none;
                border-radius: 8px;
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
        """)

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
        """Create main content area with file explorer."""
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(12, 12, 12, 12)

        self.remote_explorer = FileExplorerWidget(
            settings=self.settings,
            root_path=self.settings.remote_base_dir,
            title="🖥 Remote Server",
            is_remote=True,
            sftp=None,
        )

        content_layout.addWidget(self.remote_explorer)
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
        self.log_box.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 8px;
                font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
                font-size: 12px;
            }
        """)
        log_layout.addWidget(self.log_box)

        layout.addWidget(log_container)

    def _setup_progress_bar(self, layout: QVBoxLayout) -> None:
        """Create transfer queue panel."""
        from src.widgets.transfer_queue_widget import TransferQueueWidget

        queue_container = QWidget()
        queue_layout = QVBoxLayout(queue_container)
        queue_layout.setContentsMargins(12, 0, 12, 12)

        self.transfer_queue = TransferQueueWidget()
        queue_layout.addWidget(self.transfer_queue)

        layout.addWidget(queue_container)

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
        """Update progress (legacy — now handled by queue widget)."""

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
        # Check if user opted to skip the confirmation
        skip_confirm = self.settings.config.__dict__.get("skip_exit_confirm", False)

        if skip_confirm:
            self.controller.shutdown()
            event.accept()
            return

        from PySide6.QtWidgets import QCheckBox

        msg = QMessageBox(self)
        msg.setWindowTitle(f"Exit {SOFTWARE_NAME}")
        msg.setText("Are you sure you want to quit?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        checkbox = QCheckBox("Don't ask me again")
        msg.setCheckBox(checkbox)

        reply = msg.exec()

        if reply == QMessageBox.StandardButton.Yes:
            # Save preference if checked
            if checkbox.isChecked():
                self.settings.config.skip_exit_confirm = True
                self.settings.save_config(self.settings._config_to_dict())

            self.controller.shutdown()
            event.accept()
        else:
            event.ignore()

    def _handle_remote_drop(self, local_paths: list[str], remote_dir: str) -> None:
        """
        Called when user drags files/folders from Finder onto the remote explorer.

        Checks for duplicates on the remote, prompts user, then adds to queue.
        """
        # --- Duplicate detection (files only, not folders) ---
        duplicates = []
        sftp = self.remote_explorer.sftp
        if sftp:
            for p in local_paths:
                if os.path.isdir(p):
                    continue  # Folders merge, not duplicate
                name = os.path.basename(p)
                remote_path = os.path.join(remote_dir, name).replace("\\", "/")
                try:
                    sftp.stat(remote_path)
                    duplicates.append(name)
                except (IOError, OSError):
                    pass  # File doesn't exist — no conflict

        if duplicates:
            action = self._show_duplicate_dialog(duplicates)
            if action == DUP_ACTION_SKIP:
                # Remove duplicates from the transfer list
                local_paths = [
                    p for p in local_paths if os.path.basename(p) not in duplicates
                ]
                if not local_paths:
                    logger.info("Transfer: All files skipped (already exist)")
                    return
            elif action == DUP_ACTION_CANCEL:
                logger.info("Transfer: Cancelled by user")
                return
            # action == DUP_ACTION_OVERWRITE → proceed with all files

        # Calculate total size for the queue widget
        total_bytes = 0
        for p in local_paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if not f.startswith("."):
                            try:
                                total_bytes += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass
            elif os.path.isfile(p):
                try:
                    total_bytes += os.path.getsize(p)
                except OSError:
                    pass

        # Build display name
        names = [os.path.basename(p.rstrip("/")) for p in local_paths]
        display_name = ", ".join(names[:2])
        if len(names) > 2:
            display_name += f" (+{len(names) - 2})"

        # Add to visual queue
        self.transfer_queue.add_transfer(display_name, total_bytes)

        # Start the transfer
        self.controller.manual_transfer.queue_transfer(
            local_paths=local_paths, remote_destination=remote_dir
        )

    def _show_duplicate_dialog(self, duplicates: list[str]) -> str:
        """
        Show a dialog when files already exist on the remote.

        Returns: DUP_ACTION_OVERWRITE, DUP_ACTION_SKIP, or DUP_ACTION_CANCEL
        """
        count = len(duplicates)
        msg = QMessageBox(self)
        msg.setWindowTitle(DIALOG_FILES_ALREADY_EXIST)

        if count == 1:
            msg.setText(f"'{duplicates[0]}' already exists on the remote.")
        else:
            file_list = "\n".join(f"  • {name}" for name in duplicates[:10])
            if count > 10:
                file_list += f"\n  ... and {count - 10} more"
            msg.setText(f"{count} files already exist on the remote:\n\n{file_list}")

        msg.setInformativeText("What would you like to do?")

        overwrite_btn = msg.addButton(
            "Overwrite", QMessageBox.ButtonRole.DestructiveRole
        )
        skip_btn = msg.addButton("Skip Duplicates", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        msg.setDefaultButton(skip_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == overwrite_btn:
            return DUP_ACTION_OVERWRITE
        elif clicked == skip_btn:
            return DUP_ACTION_SKIP
        else:
            return DUP_ACTION_CANCEL
