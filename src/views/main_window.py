from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QKeySequence,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

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
    GITHUB_REPO_URL,
    MAX_CONNECTION_RETRIES,
    QUIT_CHECK_INTERVAL_MS,
    SOFTWARE_NAME,
    VERSION,
)
from src.utils.logging_signal import logger
from src.views.settings_window import SettingsWindow
from src.widgets.file_explorer_widget import FileExplorerWidget


class MainWindow(QMainWindow):
    """
    Main window for FileSling — a remote file manager.

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

        # Restore window geometry from previous session
        self._restore_geometry()

        # Connection retry tracking
        self.connection_attempts = 0
        self.max_connection_attempts = MAX_CONNECTION_RETRIES

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
        self._setup_content_area(main_layout)
        self._setup_diagnostics_log()
        self._setup_progress_bar(main_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # === 3. Wire Signals ===
        self._setup_connections()
        self.controller.initialize_transfer_queue()
        self._setup_shortcuts()
        self._setup_menu_bar()

        # === 4. Connect logger ===
        logger.log_signal.connect(self.log)
        logger.progress_signal.connect(self.update_progress)

        # === 5. Signal that window is ready (after a short delay to allow UI to settle) ===
        QTimer.singleShot(100, self._emit_fully_loaded)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _emit_fully_loaded(self) -> None:
        """Emit signal that window is fully loaded and ready."""
        self.fully_loaded.emit()

        # Auto-connect after window is loaded
        QTimer.singleShot(200, self._auto_connect_and_start)

    def _auto_connect_and_start(self) -> None:
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
            f"Welcome to {SOFTWARE_NAME}",
            "Welcome! Let's set up your first server connection.",
            QMessageBox.StandardButton.Ok,
        )

        settings_window = SettingsWindow(self.settings, server_mode=True)
        if settings_window.exec() != QDialog.DialogCode.Accepted:
            QMessageBox.critical(
                self,
                DIALOG_SETUP_REQUIRED,
                f"At least one server must be configured to use {SOFTWARE_NAME}.",
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
        from src.views.dialogs.server_selection_dialog import ServerSelectionDialog

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
                    f"Settings are required to run {SOFTWARE_NAME}.",
                    QMessageBox.StandardButton.Ok,
                )
                self.close()
                return False

        return True

    def handle_connection_failure(self) -> None:
        """Handle connection failure — show server selection dialog.

        Only tracks retry attempts for SSH connections. ADB/iOS failures
        are typically hardware issues (unplugged cable) where "switch server"
        is not a useful suggestion.
        """
        # Skip retry counter for non-SSH connections
        from src.utils.constants import CONN_TYPE_KEY, CONN_TYPE_SSH

        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )
        if connection_type != CONN_TYPE_SSH:
            return

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

    def change_server(self) -> None:
        """Allow user to change to a different server."""
        from src.views.dialogs.server_selection_dialog import ServerSelectionDialog

        selection_dialog = ServerSelectionDialog(self)
        if selection_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        server_id = selection_dialog.get_selected_server_id()
        if not server_id:
            return

        self._switch_to_server(server_id)

    def _populate_server_combo(self) -> None:
        """Populate the server dropdown with all configured servers.

        NOTE (BUG-DA-23): This method depends on blockSignals(True) being called
        before clear()/addItem() and blockSignals(False) after. It also depends on
        _setup_connections having been called before this method. Reordering these
        calls will cause spurious _on_server_combo_changed signals.
        """
        self.server_combo.blockSignals(True)
        self.server_combo.clear()

        servers = self.settings.get_servers()
        current_id = self.settings.config.current_server_id

        for server_id, config in servers.items():
            name = config.get("name", server_id)
            self.server_combo.addItem(name, server_id)

        # Separator + "Manage Servers" option
        self.server_combo.insertSeparator(self.server_combo.count())
        self.server_combo.addItem("Manage Servers", "__manage__")

        # Select current server
        for i in range(self.server_combo.count()):
            if self.server_combo.itemData(i) == current_id:
                self.server_combo.setCurrentIndex(i)
                break

        self.server_combo.blockSignals(False)

    def _on_server_combo_changed(self, index: int) -> None:
        """Handle server selection from the dropdown."""
        if index < 0:
            return
        server_id = self.server_combo.itemData(index)
        if not server_id:
            return
        if server_id == "__manage__":
            # Reset combo to current server (don't stay on "Manage Servers…")
            self.server_combo.blockSignals(True)
            current_id = self.settings.config.current_server_id
            for i in range(self.server_combo.count()):
                if self.server_combo.itemData(i) == current_id:
                    self.server_combo.setCurrentIndex(i)
                    break
            self.server_combo.blockSignals(False)
            # Open the server selection dialog
            self.change_server()
            return
        if server_id == self.settings.config.current_server_id:
            return
        self._switch_to_server(server_id)

    def _switch_to_server(self, server_id: str) -> None:
        """Switch to a different server by ID."""
        if not self.settings.load_server(server_id):
            return

        # Disconnect current connection
        self.connection_manager_service.disconnect()
        self.connection_attempts = 0

        # Update connection manager with new settings
        self.connection_manager_service = ConnectionManagerService(self.settings)
        self.controller.connection_manager = self.connection_manager_service

        # Update combo selection (in case triggered from dialog)
        self.server_combo.blockSignals(True)
        for i in range(self.server_combo.count()):
            if self.server_combo.itemData(i) == server_id:
                self.server_combo.setCurrentIndex(i)
                break
        self.server_combo.blockSignals(False)

        # Connect to new server
        self.controller.connect()

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------
    def _setup_connections(self) -> None:
        """Wire UI signals to controller actions."""
        self.connect_btn.clicked.connect(self.controller.connect)
        self.server_combo.currentIndexChanged.connect(self._on_server_combo_changed)
        self.refresh_btn.clicked.connect(self.controller.refresh_explorers)
        self.settings_btn.clicked.connect(self.controller.open_settings)
        self.delete_btn.clicked.connect(self.controller.delete_selected_item)

        # Explorer
        self.remote_explorer.file_delete_requested.connect(self.controller.delete_item)
        self.remote_explorer.files_delete_requested.connect(
            self.controller.delete_items
        )
        self.remote_explorer.file_rename_requested.connect(self.controller.rename_item)
        self.remote_explorer.file_download_requested.connect(
            self.controller.download_item
        )
        self.remote_explorer.files_download_requested.connect(
            self.controller.download_items
        )
        self.remote_explorer.folder_create_requested.connect(
            self.controller.create_folder
        )
        self.remote_explorer.item_move_requested.connect(self.controller.move_item)
        self.remote_explorer.items_move_requested.connect(self.controller.move_items)
        self.remote_explorer.item_selected.connect(
            self.controller.handle_selection_changed
        )
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

        # ⌘+I — Toggle detail panel
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(
            self.remote_explorer.toggle_detail_panel
        )

        # Escape — Deselect all / hide search
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            self._handle_escape
        )

    # ------------------------------------------------------------------
    # Menu Bar
    # ------------------------------------------------------------------
    def _setup_menu_bar(self) -> None:
        """Create native macOS menu bar."""
        menu_bar = self.menuBar()

        # --- File Menu ---
        file_menu = menu_bar.addMenu("File")

        connect_action = QAction("Connect", self)
        connect_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        connect_action.triggered.connect(self.controller.connect)
        file_menu.addAction(connect_action)

        change_server_action = QAction("Change Server...", self)
        change_server_action.triggered.connect(self.change_server)
        file_menu.addAction(change_server_action)

        file_menu.addSeparator()

        settings_action = QAction("Settings...", self)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        settings_action.triggered.connect(self.controller.open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction(f"Quit {SOFTWARE_NAME}", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # --- Edit Menu ---
        edit_menu = menu_bar.addMenu("Edit")

        # Standard macOS Edit actions (required for Emojis & Symbols to appear)
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("Cut", self)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        edit_menu.addAction(cut_action)

        copy_action = QAction("Copy", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        edit_menu.addAction(copy_action)

        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        edit_menu.addAction(paste_action)

        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        edit_menu.addAction(select_all_action)

        edit_menu.addSeparator()

        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self.controller.refresh_explorers)
        edit_menu.addAction(refresh_action)

        new_folder_action = QAction("New Folder", self)
        new_folder_action.setShortcut(QKeySequence.StandardKey.New)
        new_folder_action.triggered.connect(
            self.remote_explorer._prompt_and_create_folder
        )
        edit_menu.addAction(new_folder_action)

        edit_menu.addSeparator()

        delete_action = QAction("Delete Selected", self)
        delete_action.setShortcut(QKeySequence("Ctrl+Backspace"))
        delete_action.triggered.connect(self.controller.delete_selected_item)
        edit_menu.addAction(delete_action)

        # --- View Menu ---
        view_menu = menu_bar.addMenu("View")

        search_action = QAction("Search", self)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        search_action.triggered.connect(self.remote_explorer.show_search)
        view_menu.addAction(search_action)

        back_action = QAction("Go Back", self)
        back_action.setShortcut(QKeySequence("Ctrl+Up"))
        back_action.triggered.connect(self.remote_explorer.go_back)
        view_menu.addAction(back_action)

        view_menu.addSeparator()

        detail_panel_action = QAction("Toggle Detail Panel", self)
        detail_panel_action.setShortcut(QKeySequence("Ctrl+I"))
        detail_panel_action.triggered.connect(self.remote_explorer.toggle_detail_panel)
        view_menu.addAction(detail_panel_action)

        view_menu.addSeparator()

        history_action = QAction("Activity History...", self)
        history_action.triggered.connect(self._show_activity_history)
        view_menu.addAction(history_action)

        diagnostics_action = QAction("Diagnostics Log...", self)
        diagnostics_action.triggered.connect(self._show_diagnostics_log)
        view_menu.addAction(diagnostics_action)

        # --- Help Menu ---
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction(f"About {SOFTWARE_NAME}", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        github_action = QAction("GitHub Repository", self)
        github_action.triggered.connect(
            lambda: __import__("webbrowser").open(GITHUB_REPO_URL)
        )
        help_menu.addAction(github_action)

        bug_action = QAction("Report a Bug", self)
        bug_action.triggered.connect(
            lambda: __import__("webbrowser").open(f"{GITHUB_REPO_URL}/issues/new")
        )
        help_menu.addAction(bug_action)

        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        transfer_legend_action = QAction("Transfer Indicators", self)
        transfer_legend_action.triggered.connect(self._show_transfer_legend)
        help_menu.addAction(transfer_legend_action)

    def _show_about(self) -> None:
        """Show About dialog."""
        QMessageBox.about(
            self,
            f"About {SOFTWARE_NAME}",
            (
                f"{SOFTWARE_NAME} v{VERSION}\n\n"
                "A native macOS transfer hub for devices and servers.\n\n"
                "Built with Python, PySide6, and Paramiko.\n"
                f"{GITHUB_REPO_URL}"
            ),
        )

    def _show_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog."""
        shortcuts = (
            "⌘R — Refresh\n"
            "⌘N — New Folder\n"
            "⌘F — Search\n"
            "⌘Delete — Delete Selected\n"
            "⌘↑ — Go Back\n"
            "Enter — Navigate / Search\n"
            "Escape — Clear Search / Deselect\n"
        )

        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts)

    def _show_transfer_legend(self) -> None:
        """Show transfer method indicator legend."""
        legend = (
            "Transfer queue indicators:\n\n"
            "● Green — rsync (fast delta transfer)\n"
            "● Blue — SFTP (standard transfer)\n"
            "● Orange — ADB (USB transfer)\n\n"
            "The dot appears next to the status while a transfer\n"
            "is active. Hover the dot for a tooltip description."
        )
        QMessageBox.information(self, "Transfer Indicators", legend)

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

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 6, 12, 6)
        toolbar_layout.setSpacing(8)

        # Left side: connect button + server dropdown
        self.connect_btn = QPushButton("⏻")
        self.connect_btn.setObjectName("icon_btn")
        self.connect_btn.setToolTip("Connect")
        self.connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Server quick-switch dropdown
        self.server_combo = QComboBox()
        self.server_combo.setMinimumWidth(150)
        self.server_combo.setMaximumWidth(280)
        self.server_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.server_combo.setToolTip("Switch server")
        self.server_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._populate_server_combo()

        # Connection status (minimal — just latency, shown inline)
        self.connection_status_label = QLabel("")
        self.connection_status_label.setObjectName("connection_disconnected")
        self.connection_status_label.setStyleSheet("font-size: 11px;")

        toolbar_layout.addWidget(self.connect_btn)
        toolbar_layout.addWidget(self.server_combo)
        toolbar_layout.addWidget(self.connection_status_label)
        toolbar_layout.addStretch()

        # Right side buttons
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("icon_btn")
        self.refresh_btn.setToolTip("Refresh")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.delete_btn = QPushButton("⌫")
        self.delete_btn.setObjectName("icon_btn")
        self.delete_btn.setToolTip("Delete Selected Item")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("icon_btn")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addWidget(self.settings_btn)

        layout.addWidget(toolbar)

    def _setup_content_area(self, layout: QVBoxLayout) -> None:
        """Create main content area with file explorer."""
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(8, 4, 8, 4)

        self.remote_explorer = FileExplorerWidget(
            settings=self.settings,
            root_path=self.settings.remote_base_dir,
            title="Remote Server",
            is_remote=True,
            sftp=None,
        )

        content_layout.addWidget(self.remote_explorer)
        layout.addWidget(content_container, stretch=3)

    def _setup_diagnostics_log(self) -> None:
        """Keep diagnostics logs available without showing them in the main UI."""
        self._log_messages: list[str] = []
        self._diagnostics_dialog: Optional[QDialog] = None
        self._diagnostics_log_box: Optional[QTextEdit] = None

    def _setup_progress_bar(self, layout: QVBoxLayout) -> None:
        """Create transfer queue panel."""
        from src.widgets.transfer_queue_widget import TransferQueueWidget

        queue_container = QWidget()
        queue_layout = QVBoxLayout(queue_container)
        queue_layout.setContentsMargins(8, 0, 8, 4)

        self.transfer_queue = TransferQueueWidget()
        queue_layout.addWidget(self.transfer_queue)

        layout.addWidget(queue_container, stretch=1)

    # ------------------------------------------------------------------
    # Logging & Progress
    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        """Record diagnostics logs and update the diagnostics dialog if open."""
        self._log_messages.append(message)
        if len(self._log_messages) > 1000:
            self._log_messages = self._log_messages[-1000:]

        if self._diagnostics_log_box:
            self._diagnostics_log_box.append(message)
            scrollbar = self._diagnostics_log_box.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _show_activity_history(self) -> None:
        """Show activity history in a dialog."""
        from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

        from src.services.activity_history_service import ActivityHistoryService

        # Fresh load from disk to include all recent activity
        history = ActivityHistoryService()
        records = history.records

        dialog = QDialog(self)
        dialog.setWindowTitle("Activity History")
        dialog.setMinimumSize(550, 400)

        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)

        if not records:
            text.setPlainText("No activity yet.")
        else:
            # Build a lookup from server_id → display name
            servers = self.settings.get_servers()
            server_names = {
                sid: config.get("name", sid) for sid, config in servers.items()
            }

            lines = []
            for r in reversed(records):
                icon = {
                    "upload": "⬆️",
                    "download": "⬇️",
                    "delete": "🗑️",
                    "rename": "✏️",
                    "move": "↔️",
                    "convert": "🔄",
                }.get(r.action, "•")

                display_server = server_names.get(r.server_name, r.server_name)
                line = f"{icon}  {r.action.capitalize()}  •  {r.filename}"
                line += f"\n    {r.timestamp}  •  {display_server}"

                if r.action == "rename":
                    old_name = os.path.basename(r.source)
                    new_name = os.path.basename(r.destination)
                    line += f"\n    {old_name} → {new_name}"
                elif r.action == "delete":
                    line += f"\n    {r.source}"
                elif r.action in ("upload", "download", "move"):
                    src = r.source or ""
                    dst = r.destination or ""
                    line += f"\n    {src} → {dst}"

                lines.append(line)
            text.setPlainText("\n\n".join(lines))

        layout.addWidget(text)
        dialog.exec()

    def _show_diagnostics_log(self) -> None:
        """Show the diagnostics log in a separate window."""
        if self._diagnostics_dialog:
            self._diagnostics_dialog.raise_()
            self._diagnostics_dialog.activateWindow()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Diagnostics Log")
        dialog.setMinimumSize(720, 420)
        dialog.finished.connect(self._clear_diagnostics_dialog)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)

        self._diagnostics_log_box = QTextEdit()
        self._diagnostics_log_box.setReadOnly(True)
        for message in self._log_messages:
            self._diagnostics_log_box.append(message)
        layout.addWidget(self._diagnostics_log_box)

        self._diagnostics_dialog = dialog
        dialog.show()

        scrollbar = self._diagnostics_log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_diagnostics_dialog(self, *args) -> None:
        """Forget diagnostics dialog widgets after the window closes."""
        self._diagnostics_dialog = None
        self._diagnostics_log_box = None

    def update_progress(self, value: int) -> None:
        """Update progress (legacy — now handled by queue widget)."""

    # ------------------------------------------------------------------
    # Lifecycle Events
    # ------------------------------------------------------------------
    def showEvent(self, event: QShowEvent) -> None:
        """Called when window is shown."""
        super().showEvent(event)
        # This handler itself does not force a connection; the user can connect
        # or start monitoring manually, and auto-connect/auto-start may still
        # occur elsewhere based on user settings.

    def closeEvent(self, event: QCloseEvent) -> None:
        """Called when user clicks the window's close button."""
        # Guard: controller may not exist if window closes during early init
        if not hasattr(self, "controller"):
            self._save_geometry()
            event.accept()
            return

        # Check if any transfers/conversions are active
        has_active_work = (
            self.controller.manual_transfer.is_busy()
            or self.controller.download_ctrl.is_active
        )

        if has_active_work:
            msg = QMessageBox(self)
            msg.setWindowTitle(f"Exit {SOFTWARE_NAME}")
            msg.setText("Transfers are still in progress.")
            msg.setInformativeText("What would you like to do?")

            quit_now_btn = msg.addButton(
                "Quit Now", QMessageBox.ButtonRole.DestructiveRole
            )
            quit_after_btn = msg.addButton(
                "Quit After Jobs Finish", QMessageBox.ButtonRole.AcceptRole
            )
            cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(cancel_btn)

            msg.exec()
            clicked = msg.clickedButton()

            if clicked == cancel_btn:
                event.ignore()
                return
            elif clicked == quit_after_btn:
                # Wait for transfers to finish, then quit
                self._quit_after_jobs()
                event.ignore()
                return
            # else: quit_now — fall through to shutdown

            self._save_geometry()
            self.controller.shutdown()
            event.accept()
            return

        # No active work — show normal exit confirmation
        skip_confirm = self.settings.config.__dict__.get("skip_exit_confirm", False)

        if skip_confirm:
            self._save_geometry()
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
            if checkbox.isChecked():
                self.settings.config.skip_exit_confirm = True
                self.settings.save_config(self.settings._config_to_dict())

            self._save_geometry()
            self.controller.shutdown()
            event.accept()
        else:
            event.ignore()

    def _quit_after_jobs(self) -> None:
        """Poll until all transfers finish, then quit."""
        from PySide6.QtCore import QTimer

        self._quit_timer = QTimer(self)
        self._quit_timer.setInterval(QUIT_CHECK_INTERVAL_MS)

        def _check_done() -> None:
            still_busy = (
                self.controller.manual_transfer.is_busy()
                or self.controller.download_ctrl.is_active
            )
            if not still_busy:
                self._quit_timer.stop()
                self._save_geometry()
                self.controller.shutdown()
                from PySide6.QtWidgets import QApplication

                QApplication.quit()

        self._quit_timer.timeout.connect(_check_done)
        self._quit_timer.start()
        logger.info("Will quit after all jobs complete...")

    # ------------------------------------------------------------------
    # Window Geometry Persistence
    # ------------------------------------------------------------------
    def _save_geometry(self) -> None:
        """Save window size and position for next session."""
        from PySide6.QtCore import QSettings

        settings = QSettings(SOFTWARE_NAME, SOFTWARE_NAME)
        settings.setValue("geometry", self.saveGeometry())

    def _restore_geometry(self) -> None:
        """Restore window size and position from previous session."""
        from PySide6.QtCore import QSettings

        settings = QSettings(SOFTWARE_NAME, SOFTWARE_NAME)
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _handle_remote_drop(self, local_paths: list[str], remote_dir: str) -> None:
        """
        Called when user drags files/folders from Finder onto the remote explorer.

        Checks for duplicates on the remote, prompts user, then adds to queue.
        """
        # --- Duplicate detection (files only, not folders) ---
        # Use a single listdir_attr() instead of N individual stat() calls
        # to detect duplicates. This reduces N round-trips to 1.
        duplicates = []
        sftp = self.remote_explorer.sftp
        if sftp:
            file_names_to_check = set()
            for p in local_paths:
                if not os.path.isdir(p):
                    file_names_to_check.add(os.path.basename(p))

            if file_names_to_check:
                try:
                    existing_entries = {
                        attr.filename for attr in sftp.listdir_attr(remote_dir)
                    }
                    duplicates = [
                        name for name in file_names_to_check if name in existing_entries
                    ]
                except (IOError, OSError):
                    # If listdir fails, fall back to per-file stat
                    for name in file_names_to_check:
                        remote_path = os.path.join(remote_dir, name).replace("\\", "/")
                        try:
                            sftp.stat(remote_path)
                            duplicates.append(name)
                        except (IOError, OSError):
                            pass

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

        # Determine transfer method for the indicator dot
        transfer_method = self.controller.manual_transfer.get_transfer_method()

        # Add each file/folder as its own queue row and queue individually
        for p in local_paths:
            name = os.path.basename(p.rstrip("/"))
            # Calculate size for this item
            item_bytes = 0
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if not f.startswith("."):
                            try:
                                item_bytes += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass
            elif os.path.isfile(p):
                try:
                    item_bytes = os.path.getsize(p)
                except OSError:
                    pass

            self.transfer_queue.add_transfer(
                name, item_bytes, remote_dir, transfer_method
            )
            self.controller.manual_transfer.queue_transfer(
                local_paths=[p], remote_destination=remote_dir
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
