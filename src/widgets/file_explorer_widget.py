from __future__ import annotations

import os
import posixpath
import shutil
from stat import S_ISDIR
from typing import List, Optional

from paramiko import SFTPClient
from PySide6.QtCore import (
    QPoint,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QIcon,
    QPainter,
    QPaintEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings
from src.controllers.media_tools_controller import MediaToolsController
from src.services.activity_history_service import ActivityHistoryService
from src.services.nfo_metadata_cache_service import NfoMetadataCacheService
from src.utils.file_size import format_bytes, get_directory_size
from src.utils.logging_signal import logger
from src.workers.directory_loader import DirectoryLoader
from src.workers.nfo_cache_worker import NfoCacheWorker
from src.widgets.loading_spinner import LoadingSpinner
from src.widgets.tree_widgets import DragDropTreeWidget, SortableTreeWidgetItem


def _get_file_icon(is_dir: bool, filename: str = "") -> QIcon:
    """Get a file/folder icon based on type. Uses colored pixmaps for theme compatibility."""
    from src.utils.icons import get_file_icon

    return get_file_icon(is_dir, filename)


class FileExplorerWidget(QWidget):
    """
    A reusable file explorer widget for both local and remote (SFTP) directories.

    Features:
    - Tree view with icon, name, and size columns
    - Disk usage display in title (for remote explorer)
    - File/directory size formatting (MB/GB)

    Emits:
        - directory_changed(str): when current_path changes to a new directory
        - file_delete_requested(str): when user requests delete via context menu
        - file_rename_requested(str): when user requests rename via context menu
        - folder_create_requested(str): when user creates a new folder
        - item_move_requested(str, str): when user moves an item (src, dest)
        - item_selected(str): when selection changes
        - remote_error(str): when remote (SFTP) refresh fails (socket closed, etc)
        - files_dropped(list[str], str): local paths dropped, + destination path (current_path)
    """

    directory_changed = Signal(str)
    file_delete_requested = Signal(str)
    files_delete_requested = Signal(list)  # [paths] for multi-delete
    file_download_requested = Signal(str)  # remote_path
    files_download_requested = Signal(list)  # [remote_paths]
    batch_rename_requested = Signal(list)
    files_dropped = Signal(
        list, str
    )  # [local_paths], remote_dest_dir (or local dest dir)
    file_rename_requested = Signal(str)
    folder_create_requested = Signal(str)  # new_folder_path
    item_move_requested = Signal(str, str)  # src_path, dest_path
    items_move_requested = Signal(list)  # [(src_path, dest_path), ...]
    item_selected = Signal(str)
    remote_error = Signal(str)
    remote_load_finished = Signal(bool)

    def __init__(
        self,
        settings: Settings,
        root_path: str,
        is_remote: bool = False,
        sftp: Optional[SFTPClient] = None,
        title: str = "Explorer",
        history_service: Optional[ActivityHistoryService] = None,
    ) -> None:
        super().__init__()

        self.settings: Settings = settings
        self.root_path: str = root_path
        self.is_remote: bool = is_remote
        self.sftp: Optional[SFTPClient] = sftp
        self.title: str = title
        self.history: ActivityHistoryService = history_service or ActivityHistoryService(
            settings=settings
        )
        self._media_tools_controller: MediaToolsController = MediaToolsController(
            self, self.settings, self.history
        )

        self.current_path: str = root_path
        self.drag_over: bool = False
        self._drop_target_item: Optional[QTreeWidgetItem] = None

        # Inline rename state
        self._rename_in_progress: bool = False

        # Background loading state
        self._loader_thread: Optional[QThread] = None
        self._loader_worker: Optional[DirectoryLoader] = None
        self._sftp_background: Optional[SFTPClient] = None
        self._detail_sftp: Optional[SFTPClient] = None

        # Directory check cache (cleared on refresh): reduces network calls
        # during drag operations
        self._dir_cache: dict[str, bool] = {}
        self._nfo_cache = NfoMetadataCacheService()
        self._nfo_generation = 0
        self._pending_nfo_names: list[str] = []
        self._pending_nfo_request: Optional[tuple[str, list[str], int]] = None
        self._nfo_thread: Optional[QThread] = None
        self._nfo_worker: Optional[NfoCacheWorker] = None

        # ------------------------------------------------------------------
        # Layout
        # ------------------------------------------------------------------
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ------------------------------------------------------------------
        # Search / Filter bar
        # ------------------------------------------------------------------
        from PySide6.QtWidgets import QLineEdit

        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("🔍 Filter...")
        self._search_bar.setClearButtonEnabled(True)
        self._search_bar.setMaximumHeight(30)
        self._search_bar.returnPressed.connect(self._execute_search)
        self._search_bar.textChanged.connect(self._on_search_cleared)
        self._is_searching = False

        # Also trigger search on editingFinished (covers Enter on some Qt versions)
        layout.addWidget(self._search_bar)

        # ------------------------------------------------------------------
        # Navigation / Bookmarks bar
        # ------------------------------------------------------------------
        from src.widgets.bookmarks_bar import BookmarksBar

        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 2, 0, 6)
        nav_layout.setSpacing(4)

        self.back_btn: QPushButton = QPushButton("←")
        self.back_btn.setObjectName("icon_btn")
        self.back_btn.setToolTip("Go back")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._bookmarks_bar = BookmarksBar(self.settings)
        self._bookmarks_bar.bookmark_clicked.connect(self._navigate_to_bookmark)

        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self._bookmarks_bar, stretch=1)
        layout.addWidget(nav_container)
        self._refresh_bookmarks()

        # ------------------------------------------------------------------
        # Tree widget with columns
        # ------------------------------------------------------------------
        self.tree_widget: DragDropTreeWidget = DragDropTreeWidget()
        self.tree_widget.setAccessibleName("File Explorer")
        self.tree_widget.setHeaderLabels(["Name", "Size"])
        self.tree_widget.setColumnWidth(0, 300)  # Name column width
        self.tree_widget.setColumnWidth(1, 100)  # Size column width
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.setRootIsDecorated(False)  # No expand arrows
        self.tree_widget.setSortingEnabled(True)
        self.tree_widget.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Wrap tree + detail panel in a horizontal splitter
        from PySide6.QtWidgets import QSplitter

        from src.widgets.detail_panel import DetailPanel

        self._detail_panel = DetailPanel(self)
        self._detail_visible = self.settings.config.__dict__.get(
            "show_detail_panel", False
        )

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.tree_widget)
        self._splitter.addWidget(self._detail_panel)
        self._splitter.setStretchFactor(0, 4)  # tree gets most space
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([600, 220])
        self._splitter.setHandleWidth(1)

        # Hidden by default: toggle with ⌘I
        self._detail_panel.setVisible(self._detail_visible)

        layout.addWidget(self._splitter, stretch=1)  # stretch=1 fills available space

        self.breadcrumb_label: QLabel = QLabel()
        self.breadcrumb_label.setObjectName("secondary_label")
        self.breadcrumb_label.setTextFormat(Qt.TextFormat.RichText)
        self.breadcrumb_label.linkActivated.connect(self._on_breadcrumb_clicked)
        layout.addWidget(self.breadcrumb_label)

        # ------------------------------------------------------------------
        # Loading spinner (overlays the tree widget)
        # ------------------------------------------------------------------
        self._spinner = LoadingSpinner(self.tree_widget)

        # ------------------------------------------------------------------
        # Disk space bar (remote only)
        # ------------------------------------------------------------------
        self._disk_bar_container = QWidget()
        disk_bar_layout = QHBoxLayout(self._disk_bar_container)
        disk_bar_layout.setContentsMargins(0, 4, 0, 0)
        disk_bar_layout.setSpacing(8)

        self._disk_bar = QProgressBar()
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setValue(0)
        self._disk_bar.setFixedHeight(6)
        self._disk_bar.setTextVisible(False)

        self._disk_label = QLabel("")
        self._disk_label.setObjectName("secondary_label")
        self._disk_label.setMinimumWidth(140)

        disk_bar_layout.addWidget(self._disk_bar, stretch=1)
        disk_bar_layout.addWidget(self._disk_label)

        self._disk_bar_container.setVisible(False)
        layout.addWidget(self._disk_bar_container)

        self.back_btn.clicked.connect(self.go_back)
        self.tree_widget.itemSelectionChanged.connect(self._on_item_selected)
        self.tree_widget.itemDoubleClicked.connect(self.navigate)
        self.tree_widget.slow_click_rename.connect(self._start_inline_rename)

        # Context menu
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)

        # Drag & drop (both local + remote; remote emits files_dropped)
        self.setAcceptDrops(True)
        self.tree_widget.setAcceptDrops(True)

        # Ensure background threads are stopped on shutdown
        self.destroyed.connect(self._stop_all_threads)

        self.refresh()

    def _stop_all_threads(self) -> None:
        """Stop any running background threads (called on widget destruction)."""
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader_thread.quit()
            self._loader_thread.wait(1000)
        if hasattr(self, "_disk_thread") and self._disk_thread:
            if self._disk_thread.isRunning():
                self._disk_thread.quit()
                self._disk_thread.wait(1000)
        if self._nfo_thread and self._nfo_thread.isRunning():
            self._nfo_thread.quit()
            self._nfo_thread.wait(1000)

    def _update_breadcrumb(self) -> None:
        """Update bottom breadcrumb with clickable path segments."""
        import html

        parts = self.current_path.strip("/").split("/")
        crumbs = []
        for i, part in enumerate(parts):
            path = "/" + "/".join(parts[: i + 1])
            safe_path = html.escape(path, quote=True)
            safe_part = html.escape(part)
            crumbs.append(
                f'<a href="{safe_path}" style="text-decoration:none;">{safe_part}</a>'
            )
        self.breadcrumb_label.setText(" / ".join(crumbs) if crumbs else "/")

    def _on_breadcrumb_clicked(self, path: str) -> None:
        """Navigate to a clicked breadcrumb path."""
        self.current_path = path
        self.refresh()

    # ------------------------------------------------------------------
    #  Context menu (create / delete / rename / move)
    # ------------------------------------------------------------------
    def show_context_menu(self, position: QPoint) -> None:
        item = self.tree_widget.itemAt(position)

        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if not item:
            # No item selected: only show "New Folder"
            new_folder_action = menu.addAction("📁 New Folder")
            action = menu.exec(self.tree_widget.mapToGlobal(position))
            if action == new_folder_action:
                self._prompt_and_create_folder()
            return

        # Check for multi-select
        selected_items = self.tree_widget.selectedItems()
        is_multi = len(selected_items) > 1

        # Ensure the right-clicked item is part of the selection
        if item not in selected_items:
            # User right-clicked outside selection: treat as single item
            selected_items = [item]
            is_multi = False

        if is_multi:
            self._show_multi_select_context_menu(position, selected_items)
        else:
            self._show_single_item_context_menu(position, item)

    def _show_single_item_context_menu(
        self, position: QPoint, item: QTreeWidgetItem
    ) -> None:
        """Show context menu for a single selected item."""
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        entry = item.text(0)
        full_path = os.path.join(self.current_path, entry)

        new_folder_action = menu.addAction("📁 New Folder")
        menu.addSeparator()
        download_action = menu.addAction("⬇️ Download")
        rename_action = menu.addAction("✏️ Rename")
        move_action = menu.addAction("↔️ Move To")

        # Bookmark option for folders
        bookmark_action = None
        default_bookmark_action = None
        is_dir = (
            self._is_remote_directory(full_path)
            if self.is_remote
            else os.path.isdir(full_path)
        )
        if is_dir:
            menu.addSeparator()
            if full_path in self.settings.get_bookmarks():
                bookmark_action = menu.addAction("Remove Bookmark")
            else:
                bookmark_action = menu.addAction("Add Bookmark")
            if full_path == self.settings.get_default_bookmark():
                default_bookmark_action = menu.addAction("Clear Default Folder")
            else:
                default_bookmark_action = menu.addAction("Set as Default Folder")

        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Delete")

        # Video options (SSH only, video files only)
        convert_action = None
        convert_h265_action = None
        convert_settings_action = None
        media_info_action = None
        edit_metadata_action = None
        quick_fix_action = None
        if self._supports_ssh_media_tools():
            from src.services.ffmpeg_service import is_video_file

            if is_video_file(entry):
                menu.addSeparator()
                media_info_action = menu.addAction("ℹ️ Media Info")
                edit_metadata_action = menu.addAction("✏️ Edit Metadata")
                convert_menu = menu.addMenu("🎬 Convert Video")
                convert_action = convert_menu.addAction("H.264 (MP4)")
                convert_h265_action = convert_menu.addAction("H.265 / HEVC (MP4)")
                convert_menu.addSeparator()
                convert_settings_action = convert_menu.addAction("⚙ Settings...")
                quick_fix_action = menu.addAction("🔧 Quick Fix...")

        action = menu.exec(self.tree_widget.mapToGlobal(position))

        if action == download_action:
            self.file_download_requested.emit(full_path)
        elif action == rename_action:
            self.file_rename_requested.emit(full_path)
        elif action == move_action:
            self._handle_move_item(full_path)
        elif action == delete_action:
            self.file_delete_requested.emit(full_path)
        elif action == new_folder_action:
            self._prompt_and_create_folder()
        elif bookmark_action and action == bookmark_action:
            self._toggle_bookmark(full_path)
        elif default_bookmark_action and action == default_bookmark_action:
            self._toggle_default_bookmark(full_path)
        elif convert_action and action == convert_action:
            self._handle_convert_video(full_path, codec="h264")
        elif convert_h265_action and action == convert_h265_action:
            self._handle_convert_video(full_path, codec="h265")
        elif convert_settings_action and action == convert_settings_action:
            self._show_convert_settings()
        elif media_info_action and action == media_info_action:
            self._show_media_info(full_path)
        elif edit_metadata_action and action == edit_metadata_action:
            self._show_media_info(full_path, open_tab="tags")
        elif quick_fix_action and action == quick_fix_action:
            self._quick_fix_video(full_path)

    def _show_multi_select_context_menu(
        self, position: QPoint, selected_items: List[QTreeWidgetItem]
    ) -> None:
        """Show context menu for multiple selected items."""
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        count = len(selected_items)
        paths = [
            os.path.join(self.current_path, item.text(0)) for item in selected_items
        ]

        download_action = menu.addAction(f"⬇️ Download All ({count} items)")
        move_action = menu.addAction(f"↔️ Move All ({count} items)")
        rename_action = menu.addAction(f"✏️ Batch Rename ({count} items)")

        # Batch metadata option (only for video files on SSH connections)
        batch_metadata_action = None
        batch_quick_fix_action = None
        video_paths: list[str] = []
        if self._supports_ssh_media_tools():
            from src.services.ffmpeg_service import is_video_file

            video_paths = [
                path
                for item, path in zip(selected_items, paths)
                if is_video_file(os.path.basename(path))
                and not self._item_is_directory(item)
            ]
            if video_paths:
                menu.addSeparator()
                batch_metadata_action = menu.addAction(
                    f"✏️ Edit Metadata ({len(video_paths)} videos)"
                )
                batch_quick_fix_action = menu.addAction(
                    f"🔧 Quick Fix ({len(video_paths)} videos)"
                )

        menu.addSeparator()
        delete_action = menu.addAction(f"🗑️ Delete All ({count} items)")

        action = menu.exec(self.tree_widget.mapToGlobal(position))

        if action == download_action:
            self.files_download_requested.emit(paths)
        elif action == move_action:
            self._handle_move_items(paths)
        elif action == rename_action:
            self._handle_batch_rename(paths)
        elif action == delete_action:
            self.files_delete_requested.emit(paths)
        elif batch_metadata_action and action == batch_metadata_action:
            self._handle_batch_metadata(video_paths)
        elif batch_quick_fix_action and action == batch_quick_fix_action:
            self._quick_fix_videos(video_paths)

    def prompt_rename(self, old_path: str) -> Optional[str]:
        basename = os.path.basename(old_path)
        new_name, ok = QInputDialog.getText(
            self,
            "Rename File/Folder",
            f"Rename '{basename}' to:",
            text=basename,
        )
        if ok and new_name.strip():
            return new_name.strip()
        return None

    # ------------------------------------------------------------------
    #  Bookmarks
    # ------------------------------------------------------------------
    def _toggle_bookmark(self, path: str) -> None:
        """Add or remove a bookmark."""
        self._bookmarks_bar.toggle_bookmark(path)

    def _toggle_default_bookmark(self, path: str) -> None:
        """Set or clear the default bookmark for this server."""
        self._bookmarks_bar.toggle_default(path)

    def _refresh_bookmarks(self) -> None:
        """Rebuild the bookmarks bar from settings."""
        self._bookmarks_bar.refresh()

    def _navigate_to_bookmark(self, path: str) -> None:
        """Navigate to a bookmarked folder."""
        self.current_path = path
        self.refresh()

    def _prompt_and_create_folder(self) -> None:
        """Prompt user for new folder name and create it."""
        folder_name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Folder name:",
            text="New Folder",
        )
        if ok and folder_name.strip():
            folder_name = folder_name.strip()
            new_folder_path = os.path.join(self.current_path, folder_name)
            self.folder_create_requested.emit(new_folder_path)

    def _handle_move_item(self, src_path: str) -> None:
        """Handle moving an item: show a folder picker dialog."""
        from src.views.dialogs.folder_picker_dialog import show_move_dialog

        result = show_move_dialog(
            parent=self,
            src_paths=[src_path],
            root_path=self.root_path,
            is_remote=self.is_remote,
            sftp=self.sftp,
        )
        if result:
            src, dest = result[0]
            self.item_move_requested.emit(src, dest)

    def _handle_move_items(self, src_paths: List[str]) -> None:
        """Handle moving multiple items: show a folder picker dialog."""
        from src.views.dialogs.folder_picker_dialog import show_move_dialog

        result = show_move_dialog(
            parent=self,
            src_paths=src_paths,
            root_path=self.root_path,
            is_remote=self.is_remote,
            sftp=self.sftp,
        )
        if result:
            self.items_move_requested.emit(result)

    def _handle_batch_rename(self, paths: List[str]) -> None:
        """Forward selected paths to the file operations controller."""
        self.batch_rename_requested.emit(paths)

    def _handle_batch_metadata(self, video_paths: List[str]) -> None:
        """Handle batch metadata edit: show dialog and write NFOs."""
        from src.views.dialogs.batch_metadata_dialog import BatchMetadataDialog

        dialog = BatchMetadataDialog(
            parent=self,
            remote_paths=video_paths,
            sftp=self.sftp,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _handle_convert_video(self, remote_path: str, codec: str = "h264") -> None:
        """Queue a conversion through the media tools controller."""
        self._media_tools_controller.handle_convert_video(remote_path, codec)

    def _show_convert_settings(self) -> None:
        """Show conversion preferences through the media tools controller."""
        self._media_tools_controller.show_convert_settings()

    def _show_media_info(self, remote_path: str, open_tab: str = "info") -> None:
        """Show metadata for a remote video."""
        self._media_tools_controller.show_media_info(remote_path, open_tab)

    def _quick_fix_video(self, remote_path: str) -> None:
        """Show quick fix options and run the selected repair."""
        self._media_tools_controller.quick_fix_video(remote_path)

    def _quick_fix_videos(self, remote_paths: list[str]) -> None:
        """Apply shared container or timestamp fixes to selected videos."""
        self._media_tools_controller.quick_fix_videos(remote_paths)

    def _supports_ssh_media_tools(self) -> bool:
        """Return whether the current remote connection supports SSH commands."""
        if not self.is_remote or not self.sftp:
            return False
        from src.clients.adb_client import ADBClient
        from src.clients.ios_client import IOSClient

        return not isinstance(self.sftp, (ADBClient, IOSClient))

    @staticmethod
    def _item_is_directory(item: QTreeWidgetItem) -> bool:
        """Check the directory marker stored on a remote tree entry."""
        size_bytes = item.data(1, Qt.ItemDataRole.UserRole)
        return size_bytes is not None and size_bytes < 0

    # ------------------------------------------------------------------
    #  Core Refresh / Navigation
    # ------------------------------------------------------------------
    def refresh(self, path: Optional[str] = None) -> None:
        if path is not None:
            self.current_path = path

        if self.is_remote:
            self._nfo_generation += 1
            self._pending_nfo_names = []
            self._nfo_cache.begin_directory(self.current_path)

        self.tree_widget.clear()
        self._dir_cache.clear()
        self._is_searching = False

        self._update_breadcrumb()
        self._refresh_bookmarks()

        if self.is_remote:
            # Load asynchronously for remote (SFTP is slow)
            self._start_async_load()
        else:
            # Load synchronously for local (fast)
            self._load_local()

    def _start_async_load(self) -> None:
        """Start loading remote directory in background thread."""
        # Don't attempt async load without SFTP connection
        if not self.sftp:
            return

        # Cancel any existing load: wait for it to finish to avoid
        # overlapping SFTP calls on the same channel (causes freezes)
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                try:
                    self._loader_worker.finished.disconnect()  # type: ignore
                    self._loader_worker.error.disconnect()  # type: ignore
                    self._loader_worker.nfo_files_found.disconnect()  # type: ignore
                    if hasattr(self._loader_worker, "batch_ready"):
                        self._loader_worker.batch_ready.disconnect()  # type: ignore
                except (RuntimeError, TypeError):
                    pass
                self._loader_thread.quit()
                # Wait briefly: if SFTP call is in-flight, let it finish
                self._loader_thread.wait(500)
                if self._loader_thread.isRunning():
                    # Still running: detach and let it die on its own
                    self._loader_thread.finished.connect(
                        self._loader_thread.deleteLater
                    )
                else:
                    self._loader_thread.deleteLater()
            else:
                self._loader_thread.deleteLater()
            self._loader_thread = None
        if self._loader_worker is not None:
            self._loader_worker = None

        # Show spinner and clear tree for fresh load
        self.tree_widget.clear()
        # Disable sorting during async load to prevent items jumping around
        # as batches arrive (re-enabled in _on_load_finished)
        self.tree_widget.setSortingEnabled(False)
        self._spinner.resize(self.tree_widget.size())
        self._spinner.start()
        self.back_btn.setEnabled(False)

        # Create worker and thread
        self._loader_thread = QThread(self)  # Parent to prevent GC
        self._loader_worker = DirectoryLoader(
            path=self.current_path,
            is_remote=self.is_remote,
            sftp=self._sftp_background
            or self.sftp,  # Use dedicated channel if available
            settings=self.settings,
            generation=self._nfo_generation,
        )
        self._loader_worker.moveToThread(self._loader_thread)

        # Connect signals
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.batch_ready.connect(self._on_batch_ready)
        self._loader_worker.nfo_files_found.connect(self._on_nfo_files_found)
        self._loader_worker.finished.connect(self._on_load_finished)
        self._loader_worker.error.connect(self._on_load_error)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_worker.error.connect(self._loader_thread.quit)

        self._loader_thread.start()

    def _on_batch_ready(self, batch: list) -> None:
        """Handle a batch of items arriving progressively."""
        # Stop spinner on first batch and re-enable navigation
        self._spinner.stop()
        self.back_btn.setEnabled(True)

        for entry, is_dir, size_str, size_bytes in batch:
            icon = _get_file_icon(is_dir, entry)
            item = SortableTreeWidgetItem([entry, size_str])
            item.setIcon(0, icon)
            item.setData(1, Qt.ItemDataRole.UserRole, size_bytes)
            # Tooltip with full path and size
            full_path = os.path.join(self.current_path, entry)
            tooltip = f"{full_path}\nSize: {size_str}"
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
            self.tree_widget.addTopLevelItem(item)

    def _on_nfo_files_found(
        self, directory: str, generation: int, names: list[str]
    ) -> None:
        """Keep the sidecar names from the current directory listing."""
        if generation != self._nfo_generation or directory != self.current_path:
            return
        self._pending_nfo_names = [
            name for name in names if name.lower().endswith(".nfo")
        ]

    def _on_load_finished(self, results: list) -> None:
        """Handle background load completion."""
        self._spinner.stop()
        self.back_btn.setEnabled(True)

        # Re-enable sorting now that all items are loaded
        self.tree_widget.setSortingEnabled(True)

        # If batches were used, tree is already populated: just sort and update
        if self.tree_widget.topLevelItemCount() > 0 and results:
            # Re-sort after all items are in
            self.tree_widget.sortItems(
                self.tree_widget.sortColumn(),
                self.tree_widget.header().sortIndicatorOrder(),
            )
            self._update_breadcrumb()
            if self.is_remote and self.sftp:
                try:
                    self._get_disk_usage()
                except Exception:
                    pass
            if self.is_remote:
                self._start_nfo_cache_prefetch()
                self.remote_load_finished.emit(True)
            return

        # Non-streaming path (SSH/local): clear and rebuild
        self.tree_widget.clear()

        self._update_breadcrumb()

        # Update disk space bar
        if self.is_remote and self.sftp:
            try:
                self._get_disk_usage()
            except Exception:
                pass

        for entry, is_dir, size_str, size_bytes in results:
            icon = _get_file_icon(is_dir, entry)

            item = SortableTreeWidgetItem([entry, size_str])
            item.setIcon(0, icon)
            item.setData(1, Qt.ItemDataRole.UserRole, size_bytes)
            # Tooltip with full path and size
            full_path = os.path.join(self.current_path, entry)
            tooltip = f"{full_path}\nSize: {size_str}"
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
            self.tree_widget.addTopLevelItem(item)

        if self.is_remote:
            self._start_nfo_cache_prefetch()
            self.remote_load_finished.emit(True)

    def _start_nfo_cache_prefetch(self) -> None:
        """Load all listed sidecars in the background after a folder opens."""
        directory = self.current_path
        names = list(self._pending_nfo_names)
        generation = self._nfo_generation
        if (
            not names
            or not self._detail_sftp
            or not callable(getattr(self._detail_sftp, "open", None))
        ):
            self._pending_nfo_request = None
            self._nfo_cache.replace_directory(directory, {})
            self._refresh_selected_detail_from_cache(directory)
            return

        request = (directory, names, generation)
        if self._nfo_thread and self._nfo_thread.isRunning():
            self._pending_nfo_request = request
            return
        self._launch_nfo_cache_worker(*request)

    def _launch_nfo_cache_worker(
        self, directory: str, names: list[str], generation: int
    ) -> None:
        """Start the serialized NFO reader on the dedicated metadata channel."""
        if not self._detail_sftp:
            self._nfo_cache.replace_directory(directory, {})
            return

        self._nfo_thread = QThread(self)
        self._nfo_worker = NfoCacheWorker(
            self._detail_sftp, directory, names, generation
        )
        self._nfo_worker.moveToThread(self._nfo_thread)
        self._nfo_thread.started.connect(self._nfo_worker.run)
        self._nfo_worker.loaded.connect(self._on_nfo_cache_loaded)
        self._nfo_worker.loaded.connect(self._nfo_thread.quit)
        self._nfo_thread.finished.connect(self._nfo_worker.deleteLater)
        self._nfo_thread.finished.connect(self._on_nfo_cache_thread_finished)
        self._nfo_thread.start()

    def _on_nfo_cache_loaded(
        self, directory: str, generation: int, metadata_by_path: dict
    ) -> None:
        """Publish preloaded values and update the selected detail panel."""
        if generation != self._nfo_generation:
            return
        self._nfo_cache.replace_directory(directory, metadata_by_path)
        self._refresh_selected_detail_from_cache(directory)

    def _on_nfo_cache_thread_finished(self) -> None:
        """Clean up the reader thread and start the newest pending folder load."""
        if self._nfo_thread:
            self._nfo_thread.deleteLater()
        self._nfo_worker = None
        self._nfo_thread = None
        request = self._pending_nfo_request
        self._pending_nfo_request = None
        if request and request[2] == self._nfo_generation:
            self._launch_nfo_cache_worker(*request)

    def _refresh_selected_detail_from_cache(self, directory: str) -> None:
        """Render cached metadata for the selected file once the folder is ready."""
        path = getattr(self, "_pending_detail_path", "")
        if (
            not self._detail_visible
            or not path
            or getattr(self, "_pending_detail_is_dir", False)
            or posixpath.dirname(posixpath.normpath(path.replace("\\", "/")))
            != posixpath.normpath(directory.replace("\\", "/"))
        ):
            return
        metadata = self._nfo_cache.get_for_video(path)
        if metadata is None:
            return
        size_str = getattr(self, "_pending_detail_size", "")
        if self._detail_panel.show_file(path, size_str) and self._detail_sftp:
            self._media_tools_controller.load_detail_info(
                self._detail_panel, self._detail_sftp, path, metadata
            )
        else:
            self._detail_panel.show_metadata(metadata)

    def invalidate_nfo_cache(self, nfo_path: str) -> None:
        """Reload sidecars after an NFO is written by a metadata dialog."""
        if not self.is_remote or not self._nfo_cache.invalidate_file(nfo_path):
            return
        name = os.path.basename(nfo_path)
        if name not in self._pending_nfo_names:
            self._pending_nfo_names.append(name)
        self._nfo_generation += 1
        self._start_nfo_cache_prefetch()

    def _on_load_error(self, error_msg: str) -> None:
        """Handle background load error."""
        self._spinner.stop()
        self.back_btn.setEnabled(True)
        self.tree_widget.clear()

        error_item = QTreeWidgetItem([f"⚠️ Error loading directory: {error_msg}", ""])
        self.tree_widget.addTopLevelItem(error_item)

        if self.is_remote:
            self.remote_load_finished.emit(False)
            self._reset_remote_state_after_failure(error_msg)

    def _load_local(self) -> None:
        """Load local directory synchronously (fast)."""
        self.back_btn.setEnabled(True)
        try:
            entries = os.listdir(self.current_path)

            filtered_entries = [
                e
                for e in entries
                if not (
                    e.startswith(".")
                    or e.startswith("._")
                    or e in self.settings.skip_files
                    or (self.settings.config.hide_nfo_files and e.endswith(".nfo"))
                )
            ]
            filtered_entries.sort(key=lambda s: s.lower())

            for entry in filtered_entries:
                full_path = os.path.join(self.current_path, entry)
                icon = self._get_icon(full_path)
                size_bytes = self._get_size_bytes(full_path)
                size_str = format_bytes(size_bytes)

                item = SortableTreeWidgetItem([entry, size_str])
                item.setIcon(0, icon)
                item.setData(1, Qt.ItemDataRole.UserRole, size_bytes)
                # Tooltip with full path and size
                tooltip = f"{full_path}\nSize: {size_str}"
                item.setToolTip(0, tooltip)
                item.setToolTip(1, tooltip)
                self.tree_widget.addTopLevelItem(item)

        except Exception as e:
            error_item = QTreeWidgetItem([f"⚠️ Error loading directory: {e}", ""])
            self.tree_widget.addTopLevelItem(error_item)

    def _reset_remote_state_after_failure(self, error_msg: str) -> None:
        """
        If remote operations fail (socket closed, etc), reset to safe state:
        - reset current_path to root_path
        - clear sftp reference (forces controller to rebind)
        - emit remote_error so MainWindow/controller can reconnect
        """
        # Reset UI path to root (don't call listdir again here)
        self.current_path = self.root_path
        self._nfo_generation += 1
        self._nfo_cache.clear()
        self._pending_nfo_names = []
        self._pending_nfo_request = None
        self._update_breadcrumb()

        # Drop the dead client (important: prevents repeated "Socket is closed")
        self.sftp = None

        # Let the app/controller decide how to recover
        self.remote_error.emit(error_msg)

    def navigate(self, item: QTreeWidgetItem) -> None:
        entry: str = item.text(0)  # Get name from first column
        new_path: str = os.path.join(self.current_path, entry)

        try:
            if self.is_remote:
                if self._is_remote_directory(new_path):
                    self.current_path = new_path
                    self._is_searching = False
                    self.refresh()
                    self.directory_changed.emit(self.current_path)
            else:
                if os.path.isdir(new_path):
                    self.current_path = new_path
                    self._is_searching = False
                    self.refresh()
                    self.directory_changed.emit(self.current_path)
        except Exception as e:
            error_item = QTreeWidgetItem([f"⚠️ Cannot open {entry}: {e}", ""])
            self.tree_widget.addTopLevelItem(error_item)
            if self.is_remote:
                self._reset_remote_state_after_failure(str(e))

    def go_back(self) -> None:
        if self.current_path == self.root_path:
            return
        if not self.back_btn.isEnabled():
            return  # Already loading
        self.current_path = os.path.dirname(self.current_path)
        self._detail_panel.clear()
        self.refresh()
        self.directory_changed.emit(self.current_path)

    def set_sftp(self, sftp: Optional[SFTPClient]) -> None:
        self.sftp = sftp
        self._detail_sftp = sftp
        self._nfo_generation += 1
        self._nfo_cache.clear()
        self._pending_nfo_names = []
        self._pending_nfo_request = None

    def set_sftp_metadata(self, sftp: Optional[SFTPClient]) -> None:
        """Set the dedicated SFTP channel used for detail metadata."""
        self._detail_sftp = sftp

    def set_sftp_background(self, sftp: Optional[SFTPClient]) -> None:
        """Set dedicated SFTP channel for background operations (dir loading, disk usage)."""
        self._sftp_background = sftp

    def _on_item_selected(self) -> None:
        items = self.tree_widget.selectedItems()
        if not items:
            self._pending_detail_path = ""
            if hasattr(self, "_detail_timer"):
                self._detail_timer.stop()
            self.item_selected.emit("")
            self._detail_panel.clear()
            return
        # For multi-select, emit the first selected item (or could emit all)
        item = items[0]
        entry = item.text(0)  # Get name from first column
        full_path = os.path.join(self.current_path, entry)
        self.item_selected.emit(full_path)
        if self.is_remote:
            size_data = item.data(1, Qt.ItemDataRole.UserRole)
            self._pending_detail_is_dir = size_data is not None and size_data < 0
        else:
            self._pending_detail_is_dir = os.path.isdir(full_path)

        # Debounce detail panel: wait 300ms before fetching
        # (avoids wasting network calls when scrolling through files)
        if self._detail_visible:
            if not hasattr(self, "_detail_timer"):
                from PySide6.QtCore import QTimer

                self._detail_timer = QTimer(self)
                self._detail_timer.setSingleShot(True)
                self._detail_timer.timeout.connect(self._update_detail_panel)

            self._pending_detail_path = full_path
            self._pending_detail_size = item.text(1) if item.columnCount() > 1 else ""
            self._detail_timer.start(300)

    def _update_detail_panel(self) -> None:
        """Called after 300ms debounce: show detail panel for selected file."""
        path = getattr(self, "_pending_detail_path", "")
        size_str = getattr(self, "_pending_detail_size", "")
        if not path:
            return

        entry = os.path.basename(path)

        if getattr(self, "_pending_detail_is_dir", False):
            # Just show folder name, no network calls
            self._detail_panel.show_folder(entry)
        else:
            if self._detail_panel.show_file(path, size_str):
                metadata = self._nfo_cache.get_for_video(path)
                if metadata is None:
                    self._detail_panel.clear_metadata()
                elif self._detail_sftp:
                    self._media_tools_controller.load_detail_info(
                        self._detail_panel, self._detail_sftp, path, metadata
                    )
                else:
                    self._detail_panel.show_metadata(metadata)

    def show_search(self) -> None:
        """Focus the search bar."""
        self._search_bar.setFocus()
        self._search_bar.selectAll()

    def toggle_detail_panel(self) -> None:
        """Show or hide the detail panel."""
        self._detail_visible = not self._detail_visible
        self._detail_panel.setVisible(self._detail_visible)
        if not self._detail_visible:
            self._detail_panel.clear()

    def hide_search(self) -> None:
        """Clear the search filter."""
        self._search_bar.clear()

    def _on_search_cleared(self, text: str) -> None:
        """When search text is cleared, restore normal view."""
        if not text.strip() and self._is_searching:
            self._is_searching = False
            # Cancel any in-progress search worker to prevent its results
            # from overwriting the refresh we're about to trigger.
            if self._loader_thread is not None and self._loader_thread.isRunning():
                try:
                    if self._loader_worker:
                        self._loader_worker.finished.disconnect()  # type: ignore
                        self._loader_worker.error.disconnect()  # type: ignore
                except (RuntimeError, TypeError):
                    pass
            self.refresh()

    def _execute_search(self) -> None:
        """Execute search on Enter press."""
        text = self._search_bar.text().strip()
        if text:
            self._search_bar.clear()
            self._filter_items(text)

    def _filter_items(self, text: str) -> None:
        """Filter tree items. If query is empty, show normal directory listing.
        If query has text, do a recursive search across subdirectories."""
        query = text.lower().strip()

        if not query:
            # No filter: show normal directory listing
            for i in range(self.tree_widget.topLevelItemCount()):
                self.tree_widget.topLevelItem(i).setHidden(False)  # type: ignore
            # If we were showing search results, refresh to restore normal view
            if hasattr(self, "_is_searching") and self._is_searching:
                self._is_searching = False
                self.refresh()
            return

        # Recursive search: run in background for remote
        self._is_searching = True
        if self.is_remote and self.sftp:
            self._run_recursive_search(query)
        else:
            self._run_local_recursive_search(query)

    def _run_recursive_search(self, query: str) -> None:
        """Search recursively on remote server in a background thread."""
        self.tree_widget.clear()
        self._spinner.resize(self.tree_widget.size())
        self._spinner.start()

        # Wait for any existing loader
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                self._loader_thread.quit()
                self._loader_thread.wait(3000)
            self._loader_thread.deleteLater()
            self._loader_thread = None
        if self._loader_worker is not None:
            self._loader_worker.deleteLater()
            self._loader_worker = None

        # Run search in background
        self._loader_thread = QThread(self)
        self._search_query = query

        from src.workers.search_worker import SearchWorker

        self._loader_worker = SearchWorker(self.sftp, self.current_path, query)  # type: ignore
        self._loader_worker.moveToThread(self._loader_thread)  # type: ignore

        self._loader_thread.started.connect(self._loader_worker.run)  # type: ignore
        self._loader_worker.finished.connect(self._on_search_finished)  # type: ignore
        self._loader_worker.error.connect(self._on_search_error)  # type: ignore
        self._loader_worker.finished.connect(self._loader_thread.quit)  # type: ignore
        self._loader_worker.error.connect(self._loader_thread.quit)  # type: ignore

        self._loader_thread.start()

    def _on_search_finished(self, results: list) -> None:
        """Handle search results from background thread."""
        self._spinner.stop()
        self.tree_widget.clear()

        for rel_path, is_dir, size_str in results:
            icon = _get_file_icon(is_dir, rel_path)
            item = SortableTreeWidgetItem([rel_path, size_str])
            item.setIcon(0, icon)
            item.setData(1, Qt.ItemDataRole.UserRole, 0)
            self.tree_widget.addTopLevelItem(item)

        if not results:
            item = QTreeWidgetItem(["No results found", ""])
            self.tree_widget.addTopLevelItem(item)

        self._loader_worker = None
        self._loader_thread = None

    def _on_search_error(self, error_msg: str) -> None:
        """Handle search error."""
        self._spinner.stop()
        logger.error(f"Search failed: {error_msg}")
        self._loader_worker = None
        self._loader_thread = None

    def _run_local_recursive_search(self, query: str) -> None:
        """Search recursively on local filesystem."""
        self.tree_widget.clear()
        results = []

        for root, dirs, files in os.walk(self.current_path):
            # Limit depth
            rel_root = os.path.relpath(root, self.current_path)
            if rel_root.count(os.sep) > 3:
                continue
            # Skip hidden
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for name in dirs + files:
                if name.startswith("."):
                    continue
                if query in name.lower():
                    full_path = os.path.join(root, name)
                    rel = os.path.relpath(full_path, self.current_path)
                    is_dir = os.path.isdir(full_path)
                    size_str = (
                        format_bytes(-1 if is_dir else os.path.getsize(full_path))
                    )
                    results.append((rel, is_dir, size_str))

        for rel_path, is_dir, size_str in results:
            icon = _get_file_icon(is_dir, rel_path)
            item = SortableTreeWidgetItem([rel_path, size_str])
            item.setIcon(0, icon)
            item.setData(1, Qt.ItemDataRole.UserRole, 0)
            self.tree_widget.addTopLevelItem(item)

        if not results:
            item = QTreeWidgetItem(["No results found", ""])
            self.tree_widget.addTopLevelItem(item)

    def _start_inline_rename(self, item: QTreeWidgetItem, column: int) -> None:
        """Start inline editing using InlineRenameEditor."""
        if not hasattr(self, "_rename_editor_widget"):
            from src.widgets.inline_rename_editor import InlineRenameEditor

            self._rename_editor_widget = InlineRenameEditor(
                tree_widget=self.tree_widget,
                settings=self.settings,
                is_remote=self.is_remote,
                sftp=self.sftp,
                get_current_path=lambda: self.current_path,
                history_service=self.history,
            )

        self._rename_editor_widget._is_remote = self.is_remote
        self._rename_editor_widget._sftp = self.sftp
        self._rename_editor_widget.start(item, column)
        self._rename_in_progress = True

    def _commit_rename(self) -> None:
        """Commit the inline rename."""
        if hasattr(self, "_rename_editor_widget"):
            self._rename_editor_widget.commit()
        self._rename_in_progress = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_remote_directory(self, path: str) -> bool:
        if not self.sftp:
            return False
        try:
            st = self.sftp.stat(path)
            if st.st_mode is None:
                return False
            return S_ISDIR(st.st_mode)
        except Exception:
            return False

    def _get_icon(self, path: str) -> QIcon:
        try:
            filename = os.path.basename(path)
            if self.is_remote:
                return _get_file_icon(self._is_remote_directory(path), filename)
            return _get_file_icon(os.path.isdir(path), filename)
        except Exception:
            return _get_file_icon(False, os.path.basename(path))

    def _get_size_bytes(self, path: str) -> int:
        """
        Get raw size in bytes for sorting purposes.
        Returns -1 for directories on remote (unknown size) or on error.
        """
        try:
            if self.is_remote:
                if not self.sftp:
                    return -1
                stat_result = self.sftp.stat(path)
                if stat_result.st_mode is not None and S_ISDIR(stat_result.st_mode):
                    return -1
                return stat_result.st_size if stat_result.st_size is not None else -1
            if os.path.isdir(path):
                return get_directory_size(path)
            return os.path.getsize(path)
        except Exception:
            return -1

    def _get_disk_usage(self) -> Optional[str]:
        """
        Get disk usage information for remote filesystem asynchronously.

        Runs the df command on a background thread so the tree stays interactive.
        Returns None immediately; updates the disk bar via signal when done.
        """
        if not self.sftp:
            return None

        # Don't start another disk usage check if one is running
        if (
            hasattr(self, "_disk_thread")
            and self._disk_thread
            and self._disk_thread.isRunning()
        ):
            return None

        from src.workers.disk_usage_worker import DiskUsageWorker

        self._disk_thread = QThread(self)
        self._disk_worker = DiskUsageWorker(
            self._sftp_background or self.sftp, self.current_path
        )
        self._disk_worker.moveToThread(self._disk_thread)

        self._disk_thread.started.connect(self._disk_worker.run)
        self._disk_worker.finished.connect(
            self._on_disk_usage_ready, Qt.ConnectionType.QueuedConnection
        )
        self._disk_worker.error.connect(
            self._on_disk_usage_error, Qt.ConnectionType.QueuedConnection
        )
        self._disk_worker.finished.connect(self._disk_thread.quit)
        self._disk_worker.error.connect(self._disk_thread.quit)
        self._disk_thread.finished.connect(self._cleanup_disk_thread)

        self._disk_thread.start()
        return None

    def _on_disk_usage_ready(self, used_bytes: int, total_bytes: int) -> None:
        """Update the disk usage bar with results from background thread."""
        if total_bytes <= 0:
            return

        percent = int(used_bytes * 100 / total_bytes)
        self._disk_bar.setValue(percent)
        self._disk_label.setText(
            f"{format_bytes(used_bytes)} / {format_bytes(total_bytes)}"
        )
        self._disk_bar_container.setVisible(True)

        # Color the bar based on usage
        if percent >= 90:
            color = "#ff453a"  # Red
        elif percent >= 75:
            color = "#ff9f0a"  # Orange
        else:
            color = "#0a84ff"  # Blue

        app = QApplication.instance()
        is_light = app is not None and app.property("filesling_theme") == "light"
        background = "#e8e8ed" if is_light else "#2b2c30"
        self._disk_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {background};
                border: none;
                border-radius: 3px;
                height: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)

    def _on_disk_usage_error(self) -> None:
        """Hide disk bar if usage couldn't be determined."""
        self._disk_bar_container.setVisible(False)

    def _cleanup_disk_thread(self) -> None:
        """Clean up disk usage worker after completion."""
        if hasattr(self, "_disk_worker") and self._disk_worker:
            self._disk_worker.deleteLater()
            self._disk_worker = None
        if hasattr(self, "_disk_thread") and self._disk_thread:
            self._disk_thread.deleteLater()
            self._disk_thread = None

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # Accept both internal drags (from tree) and external file drops
        if event.source() == self.tree_widget:
            # Internal drag from tree items
            self.drag_over = True
            self.update()
            event.acceptProposedAction()
            return

        # Check for internal MIME data format
        if event.mimeData().hasFormat("application/x-explorer-items"):
            self.drag_over = True
            self.update()
            event.acceptProposedAction()
            return

        if not event.mimeData().hasUrls():
            event.ignore()
            return

        # Only accept local filesystem drops
        urls = event.mimeData().urls()
        if not any(u.isLocalFile() for u in urls):
            event.ignore()
            return

        self.drag_over = True
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.drag_over = False
        self._clear_drop_highlight()
        self.update()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Track drag position. Only highlight folders for internal moves."""
        # Only highlight drop targets for internal drags (rearranging files).
        # External drops (from Finder) always go into the current directory.
        is_internal = event.mimeData().hasFormat("application/x-explorer-items")
        if not is_internal:
            # Clear any lingering highlight
            if self._drop_target_item:
                self._clear_drop_highlight()
            event.acceptProposedAction()
            return

        item = self.tree_widget.itemAt(
            self.tree_widget.mapFrom(self, event.position().toPoint())
        )

        # Skip network check if still hovering the same highlighted folder
        if item is not None and item == self._drop_target_item:
            event.acceptProposedAction()
            return

        # Determine if the hovered item is a folder
        new_target = None
        if item:
            entry = item.text(0)
            full_path = os.path.join(self.current_path, entry)
            # Use cache to avoid repeated network calls during drag
            if full_path in self._dir_cache:
                is_folder = self._dir_cache[full_path]
            else:
                if self.is_remote:
                    is_folder = self._is_remote_directory(full_path)
                else:
                    is_folder = os.path.isdir(full_path)
                self._dir_cache[full_path] = is_folder
            if is_folder:
                new_target = item

        # Update highlight if target changed
        if new_target != self._drop_target_item:
            self._clear_drop_highlight()
            self._drop_target_item = new_target
            if self._drop_target_item:
                self._drop_target_item.setBackground(0, QColor(0, 120, 215, 60))
                self._drop_target_item.setBackground(1, QColor(0, 120, 215, 60))

        event.acceptProposedAction()

    def _clear_drop_highlight(self) -> None:
        """Remove the visual highlight from the current drop target."""
        if self._drop_target_item:
            self._drop_target_item.setBackground(0, QColor(0, 0, 0, 0))
            self._drop_target_item.setBackground(1, QColor(0, 0, 0, 0))
            self._drop_target_item = None

    def dropEvent(self, event: QDropEvent) -> None:
        """
        Handle drop events for both external files and internal file reorganization.

        For remote explorer:
        - External drops (from local filesystem) upload files
        - Internal drops reorganize files into folders

        For local explorer:
        - Move files to the target location
        """
        # Check if this is an internal drag (internal MIME format)
        is_internal_drag = event.mimeData().hasFormat("application/x-explorer-items")

        if is_internal_drag or event.source() == self.tree_widget:
            # Internal drop: move selected items into highlighted target folder
            if self._drop_target_item:
                entry = self._drop_target_item.text(0)
                target_path = os.path.join(self.current_path, entry)
                self._handle_internal_drop(target_path)

            self.drag_over = False
            self._clear_drop_highlight()
            self.update()
            return

        # External drop (from Finder/desktop): always drop into current directory
        if not event.mimeData().hasUrls():
            self.drag_over = False
            self._clear_drop_highlight()
            self.update()
            return

        urls: List[QUrl] = event.mimeData().urls()
        local_paths: List[str] = []
        for url in urls:
            if not url.isLocalFile():
                continue
            p = url.toLocalFile()
            if p:
                local_paths.append(p)

        if not local_paths:
            self.drag_over = False
            self._clear_drop_highlight()
            self.update()
            return

        # Remote explorer: upload to target folder or current directory
        if self.is_remote:
            dest_dir = self.current_path
            # Use the highlighted drop target (set during dragMoveEvent)
            # rather than recalculating: this matches what the user sees
            if self._drop_target_item:
                entry = self._drop_target_item.text(0)
                target_path = os.path.join(self.current_path, entry)
                dest_dir = target_path
            self.files_dropped.emit(local_paths, dest_dir)
            self.drag_over = False
            self._clear_drop_highlight()
            self.update()
            return

        # Local explorer: move into current directory
        for src in local_paths:
            if not os.path.exists(src):
                continue
            dst = os.path.join(self.current_path, os.path.basename(src))
            try:
                shutil.move(src, dst)
                logger.info(f"Moved: {os.path.basename(src)}: Into current directory")
            except Exception as e:
                logger.error(f"Error moving {src}: {e}")

        self.refresh()
        self.drag_over = False
        self._clear_drop_highlight()
        self.update()

    def _handle_internal_drop(self, target_folder_path: str) -> None:
        """
        Handle dropping selected items into a target folder.

        Moves all selected items into the target folder.
        """
        items = self.tree_widget.selectedItems()
        if not items:
            return

        moved_count = 0
        for item in items:
            entry = item.text(0)
            src_path = os.path.join(self.current_path, entry)
            dst_path = os.path.join(target_folder_path, entry)

            try:
                if self.is_remote:
                    if not self.sftp:
                        logger.error("No SFTP connection available")
                        continue
                    self.sftp.rename(src_path, dst_path)
                    logger.info(
                        f"Moved: {entry}: Into {os.path.basename(target_folder_path)}"
                    )
                else:
                    shutil.move(src_path, dst_path)
                    logger.info(
                        f"Moved: {entry}: Into {os.path.basename(target_folder_path)}"
                    )
                moved_count += 1
            except Exception:
                logger.error(f"Moved: {entry}: Failed")

        if moved_count > 0:
            self.refresh()

    # ------------------------------------------------------------------
    # Paint overlay
    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)

        if self.drag_over:
            painter: QPainter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            overlay_color: QColor = QColor(0, 120, 215, 40)
            border_color: QColor = QColor(0, 120, 215)

            painter.fillRect(self.rect(), overlay_color)
            painter.setPen(border_color)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 10, 10)

            painter.setPen(Qt.GlobalColor.black)
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "📂 Drop files/folders here",
            )

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep loading spinner sized to tree widget."""
        super().resizeEvent(event)
        self._spinner.resize(self.tree_widget.size())
