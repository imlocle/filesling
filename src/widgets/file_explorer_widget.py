from __future__ import annotations

import os
import shlex
import shutil
from stat import S_ISDIR
from typing import Callable, List, Optional

from paramiko import SFTPClient
from PySide6.QtCore import (
    QMimeData,
    QObject,
    QPoint,
    QRectF,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
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
from src.utils.logging_signal import logger


def _get_file_icon(is_dir: bool, filename: str = "") -> QIcon:
    """Get a file/folder icon based on type. Uses colored pixmaps for theme compatibility."""
    from src.utils.icons import get_file_icon

    return get_file_icon(is_dir, filename)


class DragDropTreeWidget(QTreeWidget):
    """Custom QTreeWidget that supports drag-drop, multi-select, and slow-click rename."""

    # Emitted when user slow-clicks to rename: (item, column)
    slow_click_rename = Signal(QTreeWidgetItem, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_start_pos = None
        self._drag_start_items = []

        # Slow-click rename state
        self._last_clicked_item: Optional[QTreeWidgetItem] = None
        self._pressed_item: Optional[QTreeWidgetItem] = None
        self._rename_timer = QTimer(self)
        self._rename_timer.setSingleShot(True)
        self._rename_timer.timeout.connect(self._trigger_rename)
        self._rename_pending_item: Optional[QTreeWidgetItem] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Track mouse press for potential drag or slow-click rename."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_items = [item.text(0) for item in self.selectedItems()]

            # Cancel any pending rename immediately on new press
            # (rename only triggers after mouse release + delay)
            self._rename_timer.stop()
            self._rename_pending_item = None

            self._pressed_item = self.itemAt(event.pos())

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Start rename timer only on release (avoids conflict with drag)."""
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if (
                item
                and item == self._pressed_item
                and item == self._last_clicked_item
                and len(self.selectedItems()) == 1
                and self._drag_start_pos is not None
                and (event.pos() - self._drag_start_pos).manhattanLength() < 4
            ):
                # Click-release on same item without dragging — start rename timer
                self._rename_pending_item = item
                self._rename_timer.start(600)

            self._last_clicked_item = item
            self._pressed_item = None

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-click cancels rename timer and navigates."""
        self._rename_timer.stop()
        self._rename_pending_item = None
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Initiate drag when mouse moves far enough from press point."""
        if (
            not (event.buttons() & Qt.MouseButton.LeftButton)
            or self._drag_start_pos is None
        ):
            super().mouseMoveEvent(event)
            return

        # Only start drag if moved at least 4 pixels (Qt standard)
        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance < 4:
            super().mouseMoveEvent(event)
            return

        # Cancel rename if dragging
        self._rename_timer.stop()
        self._rename_pending_item = None

        # Get selected items
        selected_items = self.selectedItems()
        if not selected_items:
            super().mouseMoveEvent(event)
            return

        # Create MIME data with selected item names
        mime_data = QMimeData()
        item_names = [item.text(0) for item in selected_items]
        mime_data.setText(" | ".join(item_names))
        mime_data.setData("application/x-explorer-items", b"")

        # For external drag (to Finder): provide file URLs if available
        # For remote files, download to temp dir first
        # NOTE (BUG-DA-24): This downloads files synchronously on the main thread,
        # which freezes the UI for large files. Acceptable for small files (photos).
        # For large files, users should use right-click → Download instead.
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, "is_remote"):
            if parent_widget.is_remote and parent_widget.sftp:
                import atexit
                import tempfile

                temp_dir = tempfile.mkdtemp(prefix="filesling_drag_")
                # Schedule cleanup when the app exits
                atexit.register(
                    lambda d=temp_dir: __import__("shutil").rmtree(
                        d, ignore_errors=True
                    )
                )
                urls = []
                for item_name in item_names:
                    remote_path = os.path.join(parent_widget.current_path, item_name)
                    local_temp = os.path.join(temp_dir, item_name)
                    try:
                        parent_widget.sftp.get(remote_path, local_temp)
                        urls.append(QUrl.fromLocalFile(local_temp))
                        logger.info(f"Drag: Downloaded {item_name} for Finder")
                    except Exception:
                        pass  # Skip files that fail to download
                if urls:
                    mime_data.setUrls(urls)
            elif not parent_widget.is_remote:
                # Local files — provide URLs directly
                urls = []
                for item_name in item_names:
                    full_path = os.path.join(parent_widget.current_path, item_name)
                    if os.path.exists(full_path):
                        urls.append(QUrl.fromLocalFile(full_path))
                if urls:
                    mime_data.setUrls(urls)

        # Start drag operation
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)

        self._drag_start_pos = None
        self._drag_start_items = []

    def _trigger_rename(self) -> None:
        """Trigger inline rename after slow-click delay."""
        if self._rename_pending_item:
            self.slow_click_rename.emit(self._rename_pending_item, 0)
            self._rename_pending_item = None


class SortableTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem that sorts the Size column numerically using stored byte values."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if column == 1:
            # Sort by raw byte value stored in UserRole
            self_bytes = self.data(1, Qt.ItemDataRole.UserRole) or -1
            other_bytes = other.data(1, Qt.ItemDataRole.UserRole) or -1
            return self_bytes < other_bytes
        # Default: case-insensitive alphabetical sort for Name column
        return self.text(column).lower() < other.text(column).lower()


class LoadingSpinner(QWidget):
    """A modern spinning arc loading indicator, centered over the parent widget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setVisible(False)

        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

        # Spinner appearance
        self._arc_length = 270  # degrees
        self._line_width = 3
        self._spinner_size = 32
        self._color = QColor(0, 120, 215)  # Blue accent

    def start(self) -> None:
        """Show spinner and start animation."""
        self._angle = 0
        self.setVisible(True)
        self._timer.start(16)  # ~60fps
        self.raise_()

    def stop(self) -> None:
        """Hide spinner and stop animation."""
        self._timer.stop()
        self.setVisible(False)

    def _rotate(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Center the spinner
        cx = self.width() // 2
        cy = self.height() // 2
        half = self._spinner_size // 2

        rect = QRectF(cx - half, cy - half, self._spinner_size, self._spinner_size)

        # Draw spinning arc
        pen = QPen(
            self._color,
            self._line_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Qt uses 1/16th of a degree for arc angles
        start_angle = self._angle * 16
        span_angle = self._arc_length * 16
        painter.drawArc(rect, start_angle, span_angle)

        painter.end()


class DirectoryLoader(QObject):
    """Background worker that loads directory entries via SFTP or local filesystem."""

    finished = Signal(list)  # list of (entry, icon_hint, size_str, size_bytes)
    batch_ready = Signal(list)  # partial results for progressive loading
    error = Signal(str)

    def __init__(
        self,
        path: str,
        is_remote: bool,
        sftp: Optional[SFTPClient],
        settings: Settings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.is_remote = is_remote
        self.sftp = sftp
        self.settings = settings

    def run(self) -> None:
        """Load directory entries."""
        try:
            if self.is_remote:
                if not self.sftp:
                    self.error.emit("SFTP connection not available")
                    return

                # Use listdir_attr to get names + sizes in one call
                # (avoids per-file stat calls, critical for ADB performance)
                if hasattr(self.sftp, "listdir_attr"):
                    # Check if streaming is available (ADB)
                    if hasattr(self.sftp, "listdir_attr_stream"):
                        all_results = []
                        for batch in self.sftp.listdir_attr_stream(  # type: ignore
                            self.path, batch_size=50
                        ):
                            batch_results = []
                            for attr in batch:
                                if (
                                    attr.filename.startswith(".")
                                    or attr.filename.startswith("._")
                                    or attr.filename in self.settings.skip_files
                                ):
                                    continue
                                is_dir = (
                                    S_ISDIR(attr.st_mode) if attr.st_mode else False
                                )
                                size_bytes = -1 if is_dir else (attr.st_size or 0)
                                size_str = (
                                    self._format_size(size_bytes)
                                    if size_bytes >= 0
                                    else "—"
                                )
                                batch_results.append(
                                    (attr.filename, is_dir, size_str, size_bytes)
                                )
                            if batch_results:
                                self.batch_ready.emit(batch_results)
                                all_results.extend(batch_results)

                        # Sort final results and emit finished
                        all_results.sort(key=lambda r: r[0].lower())
                        self.finished.emit(all_results)
                        return

                    # Non-streaming fallback (Paramiko SFTP)
                    attrs = self.sftp.listdir_attr(self.path)
                    filtered = [
                        a
                        for a in attrs
                        if not (
                            a.filename.startswith(".")
                            or a.filename.startswith("._")
                            or a.filename in self.settings.skip_files
                        )
                    ]
                    filtered.sort(key=lambda a: a.filename.lower())

                    results = []
                    for attr in filtered:
                        is_dir = S_ISDIR(attr.st_mode) if attr.st_mode else False
                        size_bytes = -1 if is_dir else (attr.st_size or 0)
                        size_str = (
                            self._format_size(size_bytes) if size_bytes >= 0 else "—"
                        )
                        results.append((attr.filename, is_dir, size_str, size_bytes))

                    self.finished.emit(results)
                    return

                # Fallback: listdir + individual stat calls
                entries = self.sftp.listdir(self.path)
            else:
                entries = os.listdir(self.path)

            filtered = [
                e
                for e in entries
                if not (
                    e.startswith(".")
                    or e.startswith("._")
                    or e in self.settings.skip_files
                )
            ]
            filtered.sort(key=lambda s: s.lower())

            results = []
            for entry in filtered:
                full_path = os.path.join(self.path, entry)
                is_dir = self._check_is_dir(full_path)
                size_bytes = self._get_size_bytes(full_path, is_dir)
                size_str = self._format_size(size_bytes) if size_bytes >= 0 else "—"
                results.append((entry, is_dir, size_str, size_bytes))

            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))

    def _check_is_dir(self, path: str) -> bool:
        try:
            if self.is_remote:
                if not self.sftp:
                    return False
                st = self.sftp.stat(path)
                if st.st_mode is None:
                    return False
                return S_ISDIR(st.st_mode)
            return os.path.isdir(path)
        except Exception:
            return False

    def _get_size_bytes(self, path: str, is_dir: bool) -> int:
        try:
            if self.is_remote:
                if is_dir:
                    return -1
                if not self.sftp:
                    return -1
                st = self.sftp.stat(path)
                return st.st_size if st.st_size is not None else -1
            else:
                if is_dir:
                    return self._get_local_dir_size(path)
                return os.path.getsize(path)
        except Exception:
            return -1

    def _get_local_dir_size(self, path: str) -> int:
        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total += os.path.getsize(filepath)
        except Exception:
            pass
        return total

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 0:
            return "—"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


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
    files_dropped = Signal(
        list, str
    )  # [local_paths], remote_dest_dir (or local dest dir)
    file_rename_requested = Signal(str)
    folder_create_requested = Signal(str)  # new_folder_path
    item_move_requested = Signal(str, str)  # src_path, dest_path
    items_move_requested = Signal(list)  # [(src_path, dest_path), ...]
    item_selected = Signal(str)
    remote_error = Signal(str)

    def __init__(
        self,
        settings: Settings,
        root_path: str,
        is_remote: bool = False,
        sftp: Optional[SFTPClient] = None,
        title: str = "Explorer",
    ) -> None:
        super().__init__()

        self.settings: Settings = settings
        self.root_path: str = root_path
        self.is_remote: bool = is_remote
        self.sftp: Optional[SFTPClient] = sftp
        self.title: str = title

        self.current_path: str = root_path
        self.drag_over: bool = False
        self._drop_target_item: Optional[QTreeWidgetItem] = None

        # Inline rename state
        self._renaming_item: Optional[QTreeWidgetItem] = None
        self._renaming_old_name: str = ""
        self._rename_in_progress: bool = False
        self._rename_editor = None

        # Background loading state
        self._loader_thread: Optional[QThread] = None
        self._loader_worker: Optional[DirectoryLoader] = None

        # Directory check cache (cleared on refresh) — reduces network calls
        # during drag operations
        self._dir_cache: dict[str, bool] = {}

        # ------------------------------------------------------------------
        # Layout
        # ------------------------------------------------------------------
        layout: QVBoxLayout = QVBoxLayout(self)

        # ------------------------------------------------------------------
        # Search / Filter bar
        # ------------------------------------------------------------------
        from PySide6.QtWidgets import QLineEdit

        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("🔍 Filter...")
        self._search_bar.setClearButtonEnabled(True)
        self._search_bar.setMaximumHeight(28)
        self._search_bar.returnPressed.connect(self._execute_search)
        self._search_bar.textChanged.connect(self._on_search_cleared)
        self._is_searching = False

        # Also trigger search on editingFinished (covers Enter on some Qt versions)
        layout.addWidget(self._search_bar)

        # ------------------------------------------------------------------
        # Navigation / Bookmarks bar
        # ------------------------------------------------------------------
        self._bookmarks_container = QWidget()
        self._bookmarks_layout = QHBoxLayout(self._bookmarks_container)
        self._bookmarks_layout.setContentsMargins(0, 4, 0, 4)
        self._bookmarks_layout.setSpacing(4)

        self.back_btn: QPushButton = QPushButton("←")
        self.back_btn.setObjectName("icon_btn")
        self.back_btn.setToolTip("Go back")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._bookmarks_layout.addWidget(self.back_btn)
        self._bookmarks_layout.addStretch()
        layout.addWidget(self._bookmarks_container)
        self._refresh_bookmarks()

        # ------------------------------------------------------------------
        # Tree widget with columns
        # ------------------------------------------------------------------
        self.tree_widget: DragDropTreeWidget = DragDropTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Size"])
        self.tree_widget.setColumnWidth(0, 300)  # Name column width
        self.tree_widget.setColumnWidth(1, 100)  # Size column width
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.setRootIsDecorated(False)  # No expand arrows
        self.tree_widget.setSortingEnabled(True)
        self.tree_widget.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.tree_widget)

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
        self._disk_bar.setMaximumHeight(16)
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

        self.refresh()

    def _update_breadcrumb(self) -> None:
        """Update bottom breadcrumb with clickable path segments."""
        parts = self.current_path.strip("/").split("/")
        crumbs = []
        for i, part in enumerate(parts):
            path = "/" + "/".join(parts[: i + 1])
            crumbs.append(f'<a href="{path}" style="text-decoration:none;">{part}</a>')
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
            # No item selected — only show "New Folder"
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
            # User right-clicked outside selection — treat as single item
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
        bookmarks = self.settings.get_bookmarks()
        if path in bookmarks:
            bookmarks.remove(path)
            if path == self.settings.get_default_bookmark():
                self.settings.set_default_bookmark("")
        else:
            bookmarks.append(path)
        self.settings.set_bookmarks(bookmarks)
        self._refresh_bookmarks()

    def _toggle_default_bookmark(self, path: str) -> None:
        """Set or clear the default bookmark for this server."""
        if path == self.settings.get_default_bookmark():
            self.settings.set_default_bookmark("")
        else:
            bookmarks = self.settings.get_bookmarks()
            if path not in bookmarks:
                bookmarks.append(path)
                self.settings.set_bookmarks(bookmarks)
            self.settings.set_default_bookmark(path)
        self._refresh_bookmarks()

    def _refresh_bookmarks(self) -> None:
        """Rebuild the bookmarks bar from settings."""
        # Clear existing bookmark buttons (keep back button + stretch)
        while self._bookmarks_layout.count() > 2:
            item = self._bookmarks_layout.takeAt(1)
            if item.widget():  # type: ignore
                item.widget().deleteLater()  # type: ignore

        bookmarks = self.settings.get_bookmarks()
        if not bookmarks:
            return

        for path in bookmarks:
            name = os.path.basename(path.rstrip("/")) or path
            is_default = path == self.settings.get_default_bookmark()
            label = f"● {name}" if is_default else name
            btn = QPushButton(label)
            btn.setObjectName("bookmark_btn")
            if is_default:
                btn.setStyleSheet("QPushButton#bookmark_btn { color: #0a84ff; }")
            btn.setMaximumHeight(24)
            btn.clicked.connect(lambda checked, p=path: self._navigate_to_bookmark(p))
            self._bookmarks_layout.insertWidget(self._bookmarks_layout.count() - 1, btn)

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

    def _expand_tree_to_path(
        self,
        tree: QTreeWidget,
        root_item: QTreeWidgetItem,
        target_path: str,
        load_fn: Callable,
    ) -> None:
        """
        Expand the folder picker tree down to target_path and select it.

        Walks the path segments from root to target, expanding and loading
        each level so the user sees the tree pre-navigated to the current folder.
        """
        from PySide6.QtWidgets import QTreeWidgetItem

        if not target_path or not target_path.startswith(self.root_path):
            return

        # Get the relative path segments from root to target
        rel = os.path.relpath(target_path, self.root_path)
        if rel == ".":
            tree.setCurrentItem(root_item)
            return

        # Use "/" (POSIX separator) for splitting — remote paths are always POSIX
        segments = rel.replace("\\", "/").split("/")
        current_item = root_item

        for segment in segments:
            # Expand current item (triggers lazy load via placeholder removal)
            current_item.setExpanded(True)

            # If children are placeholders, load them manually
            if current_item.childCount() == 1 and current_item.child(0).text(0) == "":
                current_item.removeChild(current_item.child(0))
                folder_path = current_item.data(0, Qt.ItemDataRole.UserRole)
                load_fn(current_item, folder_path)
                # Add placeholders for next level
                for i in range(current_item.childCount()):
                    child = current_item.child(i)
                    placeholder = QTreeWidgetItem([""])
                    child.addChild(placeholder)

            # Find the child matching this segment
            found = False
            for i in range(current_item.childCount()):
                child = current_item.child(i)
                if child.text(0) == segment:
                    current_item = child
                    found = True
                    break

            if not found:
                break

        # Select and scroll to the final item
        tree.setCurrentItem(current_item)
        tree.scrollToItem(current_item)

    def _handle_move_item(self, src_path: str) -> None:
        """Handle moving an item — show a folder picker dialog."""
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QTreeWidget,
            QTreeWidgetItem,
        )

        basename = os.path.basename(src_path)

        # Build folder picker dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Move '{basename}' to...")
        dialog.setMinimumSize(400, 400)
        dialog_layout = QVBoxLayout(dialog)

        label = QLabel(f"Select destination folder for '{basename}':")
        dialog_layout.addWidget(label)

        # Folder tree
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        dialog_layout.addWidget(tree)

        # Populate tree with remote folders
        def _load_folder(parent_item: QTreeWidgetItem, path: str) -> None:
            """Load subfolders into tree item."""
            try:
                if self.is_remote and self.sftp:
                    attrs = self.sftp.listdir_attr(path)
                    folders = sorted(
                        [
                            a.filename
                            for a in attrs
                            if not a.filename.startswith(".")
                            and a.st_mode is not None
                            and S_ISDIR(a.st_mode)
                        ],
                        key=str.lower,
                    )
                else:
                    entries = os.listdir(path)
                    folders = sorted(
                        [
                            e
                            for e in entries
                            if not e.startswith(".")
                            and os.path.isdir(os.path.join(path, e))
                        ],
                        key=str.lower,
                    )
                for folder in folders:
                    child = QTreeWidgetItem([folder])
                    child.setData(
                        0, Qt.ItemDataRole.UserRole, os.path.join(path, folder)
                    )
                    parent_item.addChild(child)
            except Exception:
                pass

        def _on_item_expanded(item: QTreeWidgetItem) -> None:
            """Lazy-load subfolders when expanded."""
            # Only load if children haven't been loaded yet
            if item.childCount() == 1 and item.child(0).text(0) == "":
                item.removeChild(item.child(0))
                folder_path = item.data(0, Qt.ItemDataRole.UserRole)
                _load_folder(item, folder_path)
                # Add placeholder children for lazy loading
                for i in range(item.childCount()):
                    child = item.child(i)
                    placeholder = QTreeWidgetItem([""])
                    child.addChild(placeholder)

        tree.itemExpanded.connect(_on_item_expanded)

        # Add root
        root_item = QTreeWidgetItem([os.path.basename(self.root_path) or "/"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, self.root_path)
        tree.addTopLevelItem(root_item)
        _load_folder(root_item, self.root_path)

        # Add placeholders for lazy loading
        for i in range(root_item.childCount()):
            child = root_item.child(i)
            placeholder = QTreeWidgetItem([""])
            child.addChild(placeholder)

        root_item.setExpanded(True)

        # Auto-expand to the current directory of the file being moved
        current_dir = os.path.dirname(src_path)
        self._expand_tree_to_path(tree, root_item, current_dir, _load_folder)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)

        # Show dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Get selected folder
        selected = tree.currentItem()
        if not selected:
            return

        dest_dir = selected.data(0, Qt.ItemDataRole.UserRole)
        if not dest_dir:
            return

        dest_path = os.path.join(dest_dir, basename)
        self.item_move_requested.emit(src_path, dest_path)

    def _handle_move_items(self, src_paths: List[str]) -> None:
        """Handle moving multiple items — show a folder picker dialog."""
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QTreeWidget,
            QTreeWidgetItem,
        )

        count = len(src_paths)
        names = [os.path.basename(p) for p in src_paths]
        display = ", ".join(names[:3])
        if count > 3:
            display += f" (+{count - 3} more)"

        # Build folder picker dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Move {count} items to...")
        dialog.setMinimumSize(400, 400)
        dialog_layout = QVBoxLayout(dialog)

        label = QLabel(f"Select destination folder for {count} items:\n{display}")
        dialog_layout.addWidget(label)

        # Folder tree
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        dialog_layout.addWidget(tree)

        # Populate tree with remote folders
        def _load_folder(parent_item: QTreeWidgetItem, path: str) -> None:
            """Load subfolders into tree item."""
            try:
                if self.is_remote and self.sftp:
                    attrs = self.sftp.listdir_attr(path)
                    folders = sorted(
                        [
                            a.filename
                            for a in attrs
                            if not a.filename.startswith(".")
                            and a.st_mode is not None
                            and S_ISDIR(a.st_mode)
                        ],
                        key=str.lower,
                    )
                else:
                    entries = os.listdir(path)
                    folders = sorted(
                        [
                            e
                            for e in entries
                            if not e.startswith(".")
                            and os.path.isdir(os.path.join(path, e))
                        ],
                        key=str.lower,
                    )
                for folder in folders:
                    child = QTreeWidgetItem([folder])
                    child.setData(
                        0, Qt.ItemDataRole.UserRole, os.path.join(path, folder)
                    )
                    parent_item.addChild(child)
            except Exception:
                pass

        def _on_item_expanded(item: QTreeWidgetItem) -> None:
            """Lazy-load subfolders when expanded."""
            if item.childCount() == 1 and item.child(0).text(0) == "":
                item.removeChild(item.child(0))
                folder_path = item.data(0, Qt.ItemDataRole.UserRole)
                _load_folder(item, folder_path)
                for i in range(item.childCount()):
                    child = item.child(i)
                    placeholder = QTreeWidgetItem([""])
                    child.addChild(placeholder)

        tree.itemExpanded.connect(_on_item_expanded)

        # Add root
        root_item = QTreeWidgetItem([os.path.basename(self.root_path) or "/"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, self.root_path)
        tree.addTopLevelItem(root_item)
        _load_folder(root_item, self.root_path)

        # Add placeholders for lazy loading
        for i in range(root_item.childCount()):
            child = root_item.child(i)
            placeholder = QTreeWidgetItem([""])
            child.addChild(placeholder)

        root_item.setExpanded(True)

        # Auto-expand to the current directory of the items being moved
        current_dir = os.path.dirname(src_paths[0])
        self._expand_tree_to_path(tree, root_item, current_dir, _load_folder)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)

        # Show dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Get selected folder
        selected = tree.currentItem()
        if not selected:
            return

        dest_dir = selected.data(0, Qt.ItemDataRole.UserRole)
        if not dest_dir:
            return

        # Filter out self-moves (moving into itself or same location)
        moves = []
        skipped = []
        for src_path in src_paths:
            basename = os.path.basename(src_path)
            dest_path = os.path.join(dest_dir, basename)
            if dest_path.startswith(src_path + "/") or src_path == dest_dir:
                skipped.append(basename)
            else:
                moves.append((src_path, dest_path))

        if skipped:
            from PySide6.QtWidgets import QMessageBox

            skipped_display = ", ".join(skipped[:5])
            if len(skipped) > 5:
                skipped_display += f" (+{len(skipped) - 5} more)"
            QMessageBox.warning(
                self,
                "Move Skipped",
                f"Cannot move items into themselves:\n{skipped_display}",
                QMessageBox.StandardButton.Ok,
            )

        if moves:
            self.items_move_requested.emit(moves)

    def _handle_batch_rename(self, paths: List[str]) -> None:
        """Handle batch rename — show find/replace dialog."""
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QGridLayout,
            QLineEdit,
            QListWidget,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Batch Rename ({len(paths)} items)")
        dialog.setMinimumSize(450, 350)
        dialog_layout = QVBoxLayout(dialog)

        # Find & Replace inputs
        grid = QGridLayout()
        grid.addWidget(QLabel("Find:"), 0, 0)
        find_input = QLineEdit()
        find_input.setPlaceholderText("Text to find in filenames")
        grid.addWidget(find_input, 0, 1)

        grid.addWidget(QLabel("Replace:"), 1, 0)
        replace_input = QLineEdit()
        replace_input.setPlaceholderText("Replacement text (leave empty to remove)")
        grid.addWidget(replace_input, 1, 1)
        dialog_layout.addLayout(grid)

        # Preview list
        dialog_layout.addWidget(QLabel("Preview:"))
        preview_list = QListWidget()
        preview_list.setMinimumHeight(150)
        dialog_layout.addWidget(preview_list)

        # Populate initial preview
        basenames = [os.path.basename(p) for p in paths]
        for name in basenames:
            preview_list.addItem(f"{name} → {name}")

        # Update preview on input change
        def update_preview() -> None:
            find_text = find_input.text()
            preview_list.clear()
            for name in basenames:
                if find_text:
                    new_name = name.replace(find_text, replace_input.text())
                else:
                    new_name = name
                if new_name != name:
                    preview_list.addItem(f"{name} → {new_name}")
                else:
                    preview_list.addItem(f"{name} (unchanged)")

        find_input.textChanged.connect(update_preview)
        replace_input.textChanged.connect(update_preview)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        find_text = find_input.text()
        if not find_text:
            return

        replace_text = replace_input.text()

        # Perform renames — check for collisions first
        renamed = 0
        collisions = []
        for path in paths:
            old_name = os.path.basename(path)
            new_name = old_name.replace(find_text, replace_text)
            if new_name == old_name:
                continue

            new_path = os.path.join(os.path.dirname(path), new_name)

            # Check if destination already exists
            exists = False
            try:
                if self.is_remote and self.sftp:
                    self.sftp.stat(new_path)
                    exists = True
                elif not self.is_remote:
                    exists = os.path.exists(new_path)
            except (IOError, OSError):
                pass  # Doesn't exist — safe to rename

            if exists:
                # Try with suffix _2, _3, etc.
                base, ext = os.path.splitext(new_name)
                suffix_num = 2
                while exists:
                    candidate = f"{base}_{suffix_num}{ext}"
                    candidate_path = os.path.join(os.path.dirname(path), candidate)
                    exists = False
                    try:
                        if self.is_remote and self.sftp:
                            self.sftp.stat(candidate_path)
                            exists = True
                        elif not self.is_remote:
                            exists = os.path.exists(candidate_path)
                    except (IOError, OSError):
                        pass
                    if exists:
                        suffix_num += 1
                    else:
                        new_path = candidate_path
                        collisions.append(f"{new_name} → {candidate}")
                        break

            try:
                if self.is_remote and self.sftp:
                    self.sftp.rename(path, new_path)
                elif not self.is_remote:
                    os.rename(path, new_path)
                renamed += 1
            except Exception as e:
                logger.error(f"Rename failed: {old_name}: {e}")

        if renamed == 0 and self.sftp is None and self.is_remote:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "Rename Failed",
                "Connection lost — no files were renamed.",
                QMessageBox.StandardButton.Ok,
            )
            return

        if collisions:
            logger.warn(f"Batch rename: {len(collisions)} name collisions resolved")

        if renamed > 0:
            logger.success(f"Batch rename: {renamed} files renamed")
            self.refresh()

    # ------------------------------------------------------------------
    #  Core Refresh / Navigation
    # ------------------------------------------------------------------
    def refresh(self, path: str | None = None) -> None:
        if path is not None:
            self.current_path = path

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

        # Cancel any existing load — disconnect signals and let it finish silently
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                # Disconnect all signals so the old worker doesn't update UI
                try:
                    self._loader_worker.finished.disconnect()  # type: ignore
                    self._loader_worker.error.disconnect()  # type: ignore
                except (RuntimeError, TypeError):
                    pass
                # Let the thread finish on its own and clean up
                self._loader_thread.quit()
                self._loader_thread.finished.connect(self._loader_thread.deleteLater)
            else:
                self._loader_thread.deleteLater()
            self._loader_thread = None
        if self._loader_worker is not None:
            self._loader_worker = None

        # Show spinner and clear tree for fresh load
        self.tree_widget.clear()
        self._spinner.resize(self.tree_widget.size())
        self._spinner.start()

        # Create worker and thread
        self._loader_thread = QThread(self)  # Parent to prevent GC
        self._loader_worker = DirectoryLoader(
            path=self.current_path,
            is_remote=self.is_remote,
            sftp=self.sftp,
            settings=self.settings,
        )
        self._loader_worker.moveToThread(self._loader_thread)

        # Connect signals
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.batch_ready.connect(self._on_batch_ready)
        self._loader_worker.finished.connect(self._on_load_finished)
        self._loader_worker.error.connect(self._on_load_error)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_worker.error.connect(self._loader_thread.quit)

        self._loader_thread.start()

    def _on_batch_ready(self, batch: list) -> None:
        """Handle a batch of items arriving progressively."""
        # Stop spinner on first batch
        self._spinner.stop()

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

    def _on_load_finished(self, results: list) -> None:
        """Handle background load completion."""
        self._spinner.stop()

        # If batches were used, tree is already populated — just sort and update
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
            return

        # Non-streaming path (SSH/local) — clear and rebuild
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

    def _on_load_error(self, error_msg: str) -> None:
        """Handle background load error."""
        self._spinner.stop()
        self.tree_widget.clear()

        error_item = QTreeWidgetItem([f"⚠️ Error loading directory: {error_msg}", ""])
        self.tree_widget.addTopLevelItem(error_item)

        if self.is_remote:
            self._reset_remote_state_after_failure(error_msg)

    def _load_local(self) -> None:
        """Load local directory synchronously (fast)."""
        try:
            entries = os.listdir(self.current_path)

            filtered_entries = [
                e
                for e in entries
                if not (
                    e.startswith(".")
                    or e.startswith("._")
                    or e in self.settings.skip_files
                )
            ]
            filtered_entries.sort(key=lambda s: s.lower())

            for entry in filtered_entries:
                full_path = os.path.join(self.current_path, entry)
                icon = self._get_icon(full_path)
                size_str = self._get_size_string(full_path)
                size_bytes = self._get_size_bytes(full_path)

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
        self.current_path = os.path.dirname(self.current_path)
        self.refresh()
        self.directory_changed.emit(self.current_path)

    def set_sftp(self, sftp: Optional[SFTPClient]) -> None:
        self.sftp = sftp

    def _on_item_selected(self) -> None:
        items = self.tree_widget.selectedItems()
        if not items:
            self.item_selected.emit("")
            return
        # For multi-select, emit the first selected item (or could emit all)
        entry = items[0].text(0)  # Get name from first column
        full_path = os.path.join(self.current_path, entry)
        self.item_selected.emit(full_path)

    def show_search(self) -> None:
        """Focus the search bar."""
        self._search_bar.setFocus()
        self._search_bar.selectAll()

    def hide_search(self) -> None:
        """Clear the search filter."""
        self._search_bar.clear()

    def _on_search_cleared(self, text: str) -> None:
        """When search text is cleared, restore normal view."""
        if not text.strip() and self._is_searching:
            self._is_searching = False
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
            # No filter — show normal directory listing
            for i in range(self.tree_widget.topLevelItemCount()):
                self.tree_widget.topLevelItem(i).setHidden(False)  # type: ignore
            # If we were showing search results, refresh to restore normal view
            if hasattr(self, "_is_searching") and self._is_searching:
                self._is_searching = False
                self.refresh()
            return

        # Recursive search — run in background for remote
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

        class SearchWorker(QObject):
            finished = Signal(list)
            error = Signal(str)

            def __init__(
                self, sftp: object, base_path: str, query: str, max_depth: int = 3
            ) -> None:
                super().__init__()
                self.sftp = sftp
                self.base_path = base_path
                self.query = query
                self.max_depth = max_depth

            def run(self) -> None:
                try:
                    results = []
                    self._search_dir(self.base_path, results, 0)
                    self.finished.emit(results)
                except Exception as e:
                    self.error.emit(str(e))

            def _search_dir(self, path: str, results: list, depth: int) -> None:
                if depth > self.max_depth:
                    return
                try:
                    entries = self.sftp.listdir_attr(path)
                    for attr in entries:
                        name = attr.filename
                        if name.startswith(".") or name.startswith("._"):
                            continue
                        full_path = f"{path}/{name}"
                        is_dir = attr.st_mode is not None and S_ISDIR(attr.st_mode)

                        if self.query in name.lower():
                            rel = os.path.relpath(full_path, self.base_path)
                            size_str = (
                                "—" if is_dir else self._fmt_size(attr.st_size or 0)
                            )
                            results.append((rel, is_dir, size_str))

                        if is_dir:
                            self._search_dir(full_path, results, depth + 1)
                except Exception:
                    pass

            def _fmt_size(self, size_bytes: int) -> str:
                if size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    return f"{size_bytes / 1024:.1f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    return f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

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
                        "—" if is_dir else self._format_size(os.path.getsize(full_path))
                    )
                    results.append((rel, is_dir, size_str))

        from src.widgets.file_explorer_widget import SortableTreeWidgetItem

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
        """Start inline editing using a QLineEdit overlay."""
        self._renaming_item = item
        self._renaming_old_name = item.text(0)
        self._rename_in_progress = True

        # Get the item's visual rect for column 0
        rect = self.tree_widget.visualItemRect(item)
        # Adjust for header height
        header_height = self.tree_widget.header().height()

        # Create a QLineEdit overlay
        from PySide6.QtWidgets import QLineEdit

        self._rename_editor = QLineEdit(self.tree_widget)
        self._rename_editor.setText(item.text(0))
        self._rename_editor.selectAll()
        self._rename_editor.setGeometry(
            rect.x() + 24,  # offset for icon
            rect.y() + header_height,
            rect.width() - 24,
            rect.height(),
        )
        self._rename_editor.show()
        self._rename_editor.setFocus()

        # Connect signals
        self._rename_editor.returnPressed.connect(self._commit_rename)
        self._rename_editor.editingFinished.connect(self._commit_rename)

    def _commit_rename(self) -> None:
        """Commit the inline rename."""
        if not self._rename_in_progress:
            return
        self._rename_in_progress = False

        editor = self._rename_editor
        item = self._renaming_item
        old_name = self._renaming_old_name

        new_name = editor.text().strip() if editor else ""

        # Clean up editor
        if editor:
            editor.hide()
            editor.deleteLater()
            self._rename_editor = None
        self._renaming_item = None

        # If name didn't change or is empty, do nothing
        if not new_name or new_name == old_name:
            return

        # Do the rename
        old_path = os.path.join(self.current_path, old_name)
        new_path = os.path.join(self.current_path, new_name)

        try:
            if self.is_remote:
                if self.sftp:
                    self.sftp.rename(old_path, new_path)
            else:
                os.rename(old_path, new_path)

            # Update the item text directly
            self.tree_widget.blockSignals(True)
            item.setText(0, new_name)  # type: ignore
            self.tree_widget.blockSignals(False)
            logger.success(f"Renamed: {old_name} → {new_name}")

            # Record in history
            from src.services.activity_history_service import ActivityHistoryService

            history = ActivityHistoryService()
            history.add(
                filename=old_name,
                action="rename",
                source=old_path,
                destination=new_path,
                server_name=(
                    self.settings.config.current_server_id
                    if hasattr(self.settings, "config")
                    else ""
                ),
            )
        except Exception as e:
            logger.error(f"Rename failed: {e}")

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

    def _get_size_string(self, path: str) -> str:
        """
        Get human-readable size string for a file or directory.
        For remote: only show file sizes (directories show "—" for speed)
        For local: calculate directory sizes
        """
        try:
            if self.is_remote:
                if not self.sftp:
                    return "—"

                # For remote, only show file sizes (not directory sizes for performance)
                if self._is_remote_directory(path):
                    return "—"  # Skip directory size calculation for speed
                else:
                    st = self.sftp.stat(path)
                    if st.st_size is None:
                        return "—"
                    return self._format_size(st.st_size)
            else:
                # Local: show both file and directory sizes
                if os.path.isdir(path):
                    size_bytes = self._get_local_dir_size(path)
                else:
                    size_bytes = os.path.getsize(path)
                return self._format_size(size_bytes)
        except Exception:
            return "—"

    def _get_size_bytes(self, path: str) -> int:
        """
        Get raw size in bytes for sorting purposes.
        Returns -1 for directories on remote (unknown size) or on error.
        """
        try:
            if self.is_remote:
                if not self.sftp:
                    return -1
                if self._is_remote_directory(path):
                    return -1
                st = self.sftp.stat(path)
                return st.st_size if st.st_size is not None else -1
            else:
                if os.path.isdir(path):
                    return self._get_local_dir_size(path)
                return os.path.getsize(path)
        except Exception:
            return -1

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes into human-readable string."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _get_local_dir_size(self, path: str) -> int:
        """Calculate total size of a local directory."""
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total += os.path.getsize(filepath)
        except Exception:
            pass
        return total

    def _get_disk_usage(self) -> Optional[str]:
        """
        Get disk usage information for remote filesystem.

        Returns:
            String like "45.2 GB / 128 GB" or None if unavailable
        """
        if not self.sftp:
            return None

        try:
            # Get SSH client from SFTP connection
            channel = self.sftp.get_channel()
            if not channel:
                return None

            transport = channel.get_transport()
            if not transport:
                return None

            # Execute df command against the current path so mounted drives show
            # their own filesystem capacity instead of the server base path.
            # -B1 gives output in bytes for accurate calculation
            session = transport.open_session()
            session.exec_command(f"df -B1 {shlex.quote(self.current_path)} | tail -1")

            # Read output
            output = session.recv(1024).decode("utf-8").strip()
            session.close()

            if not output:
                return None

            # Parse df output: Filesystem Size Used Avail Use% Mounted
            parts = output.split()
            if len(parts) < 4:
                return None

            # parts[1] = total size, parts[2] = used size
            total_bytes = int(parts[1])
            used_bytes = int(parts[2])

            # Update disk bar
            if total_bytes > 0:
                percent = int(used_bytes * 100 / total_bytes)
                self._disk_bar.setValue(percent)
                self._disk_label.setText(
                    f"{self._format_size(used_bytes)} / {self._format_size(total_bytes)}"
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
                is_light = (
                    app is not None and app.property("filesling_theme") == "light"
                )
                background = "#e8e8ed" if is_light else "#2b2c30"
                border = "#d2d2d7" if is_light else "#3d3e44"
                self._disk_bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: {background};
                        border: 1px solid {border};
                        border-radius: 4px;
                    }}
                    QProgressBar::chunk {{
                        background-color: {color};
                        border-radius: 3px;
                    }}
                """)

            used_str = self._format_size(used_bytes)
            total_str = self._format_size(total_bytes)

            return f"{used_str} / {total_str}"
        except Exception:
            return None

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

        # External drop (from Finder/desktop) — always drop into current directory
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
            # rather than recalculating — this matches what the user sees
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
