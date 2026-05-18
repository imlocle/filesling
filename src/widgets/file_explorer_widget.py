from __future__ import annotations

import os
import shlex
import shutil
from stat import S_ISDIR
from typing import List, Optional

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
    QDropEvent,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
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


class DragDropTreeWidget(QTreeWidget):
    """Custom QTreeWidget that supports drag-drop, multi-select, and slow-click rename."""

    # Emitted when user slow-clicks to rename: (item, column)
    slow_click_rename = Signal(QTreeWidgetItem, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = None
        self._drag_start_items = []

        # Slow-click rename state
        self._last_clicked_item: Optional[QTreeWidgetItem] = None
        self._rename_timer = QTimer(self)
        self._rename_timer.setSingleShot(True)
        self._rename_timer.timeout.connect(self._trigger_rename)
        self._rename_pending_item: Optional[QTreeWidgetItem] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Track mouse press for potential drag or slow-click rename."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_items = [item.text(0) for item in self.selectedItems()]

            # Slow-click rename detection
            item = self.itemAt(event.pos())
            if (
                item
                and item == self._last_clicked_item
                and len(self.selectedItems()) == 1
                and not self._rename_timer.isActive()
            ):
                # Second click on same item — start rename timer
                self._rename_pending_item = item
                self._rename_timer.start(500)
            else:
                # Different item or first click — cancel any pending rename
                self._rename_timer.stop()
                self._rename_pending_item = None

            self._last_clicked_item = item

        super().mousePressEvent(event)

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

        # Start drag operation
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction)

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

    def __init__(self, parent=None):
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

    def start(self):
        """Show spinner and start animation."""
        self._angle = 0
        self.setVisible(True)
        self._timer.start(16)  # ~60fps
        self.raise_()

    def stop(self):
        """Hide spinner and stop animation."""
        self._timer.stop()
        self.setVisible(False)

    def _rotate(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event):
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
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.is_remote = is_remote
        self.sftp = sftp
        self.settings = settings

    def run(self):
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
                        for batch in self.sftp.listdir_attr_stream(
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
        - file_opened(str): when a file is double-clicked
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
    file_download_requested = Signal(str)  # remote_path
    files_dropped = Signal(
        list, str
    )  # [local_paths], remote_dest_dir (or local dest dir)
    file_opened = Signal(str)
    file_rename_requested = Signal(str)
    folder_create_requested = Signal(str)  # new_folder_path
    item_move_requested = Signal(str, str)  # src_path, dest_path
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

        # Inline rename state
        self._renaming_item: Optional[QTreeWidgetItem] = None
        self._renaming_old_name: str = ""
        self._rename_in_progress: bool = False
        self._rename_editor = None

        # Background loading state
        self._loader_thread: Optional[QThread] = None
        self._loader_worker: Optional[DirectoryLoader] = None

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
        self._search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                color: #cccccc;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
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
        self.breadcrumb_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.breadcrumb_label.setStyleSheet("color: #858585; font-size: 11px;")
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
        self._disk_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
        """)

        self._disk_label = QLabel("")
        self._disk_label.setStyleSheet("color: #858585; font-size: 11px;")
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
        """Update bottom breadcrumb text."""
        self.breadcrumb_label.setText(self.current_path)

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

        entry = item.text(0)  # Get name from first column
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
                bookmark_action = menu.addAction("⭐ Remove Bookmark")
            else:
                bookmark_action = menu.addAction("⭐ Bookmark")
            if full_path == self.settings.get_default_bookmark():
                default_bookmark_action = menu.addAction("🏠 Clear Default Bookmark")
            else:
                default_bookmark_action = menu.addAction("🏠 Set as Default Bookmark")

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
            if item.widget():
                item.widget().deleteLater()

        bookmarks = self.settings.get_bookmarks()
        if not bookmarks:
            return

        for path in bookmarks:
            name = os.path.basename(path.rstrip("/")) or path
            prefix = "🏠" if path == self.settings.get_default_bookmark() else "📁"
            btn = QPushButton(f"{prefix} {name}")
            btn.setMaximumHeight(24)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(14, 165, 233, 0.1);
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    color: #cbd5e1;
                }
                QPushButton:hover {
                    background-color: rgba(14, 165, 233, 0.2);
                    border-color: #0ea5e9;
                }
            """)
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
        label.setStyleSheet("color: #cccccc; padding: 4px;")
        dialog_layout.addWidget(label)

        # Folder tree
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
        """)
        dialog_layout.addWidget(tree)

        # Populate tree with remote folders
        def _load_folder(parent_item, path):
            """Load subfolders into tree item."""
            try:
                if self.is_remote and self.sftp:
                    entries = self.sftp.listdir(path)
                else:
                    entries = os.listdir(path)

                folders = sorted(
                    [
                        e
                        for e in entries
                        if not e.startswith(".")
                        and (
                            (
                                self.is_remote
                                and self._is_remote_directory(os.path.join(path, e))
                            )
                            or (
                                not self.is_remote
                                and os.path.isdir(os.path.join(path, e))
                            )
                        )
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

        def _on_item_expanded(item):
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

    # ------------------------------------------------------------------
    #  Core Refresh / Navigation
    # ------------------------------------------------------------------
    def refresh(self, path: str | None = None) -> None:
        if path is not None:
            self.current_path = path

        self.tree_widget.clear()

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
                    self._loader_worker.finished.disconnect()
                    self._loader_worker.error.disconnect()
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
            icon = (
                QIcon.fromTheme("folder")
                if is_dir
                else QIcon.fromTheme("text-x-generic")
            )
            item = SortableTreeWidgetItem([entry, size_str])
            item.setIcon(0, icon)
            item.setData(1, Qt.ItemDataRole.UserRole, size_bytes)
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
            icon = (
                QIcon.fromTheme("folder")
                if is_dir
                else QIcon.fromTheme("text-x-generic")
            )

            item = SortableTreeWidgetItem([entry, size_str])
            item.setIcon(0, icon)
            item.setData(1, Qt.ItemDataRole.UserRole, size_bytes)
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
                    self.refresh()
                    self.directory_changed.emit(self.current_path)
                else:
                    self.file_opened.emit(new_path)
            else:
                if os.path.isdir(new_path):
                    self.current_path = new_path
                    self.refresh()
                    self.directory_changed.emit(self.current_path)
                else:
                    self.file_opened.emit(new_path)
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
                self.tree_widget.topLevelItem(i).setHidden(False)
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

            def __init__(self, sftp, base_path, query, max_depth=3):
                super().__init__()
                self.sftp = sftp
                self.base_path = base_path
                self.query = query
                self.max_depth = max_depth

            def run(self):
                try:
                    results = []
                    self._search_dir(self.base_path, results, 0)
                    self.finished.emit(results)
                except Exception as e:
                    self.error.emit(str(e))

            def _search_dir(self, path, results, depth):
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

            def _fmt_size(self, size_bytes):
                if size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    return f"{size_bytes / 1024:.1f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    return f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

        self._loader_worker = SearchWorker(self.sftp, self.current_path, query)
        self._loader_worker.moveToThread(self._loader_thread)

        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.finished.connect(self._on_search_finished)
        self._loader_worker.error.connect(self._on_search_error)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_worker.error.connect(self._loader_thread.quit)

        self._loader_thread.start()

    def _on_search_finished(self, results: list) -> None:
        """Handle search results from background thread."""
        self._spinner.stop()
        self.tree_widget.clear()

        for rel_path, is_dir, size_str in results:
            icon = (
                QIcon.fromTheme("folder")
                if is_dir
                else QIcon.fromTheme("text-x-generic")
            )
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
            icon = (
                QIcon.fromTheme("folder")
                if is_dir
                else QIcon.fromTheme("text-x-generic")
            )
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
        self._rename_editor.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #0078d4;
                border-radius: 2px;
                padding: 2px 4px;
                font-size: 12px;
            }
        """)
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
            item.setText(0, new_name)
            self.tree_widget.blockSignals(False)
            logger.success(f"Renamed: {old_name} → {new_name}")
        except Exception as e:
            logger.error(f"Rename failed: {e}")

    def _on_item_renamed(self, item: QTreeWidgetItem, column: int) -> None:
        """No-op — rename is handled by _commit_rename."""

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
            if self.is_remote:
                return (
                    QIcon.fromTheme("folder")
                    if self._is_remote_directory(path)
                    else QIcon.fromTheme("text-x-generic")
                )
            return (
                QIcon.fromTheme("folder")
                if os.path.isdir(path)
                else QIcon.fromTheme("text-x-generic")
            )
        except Exception:
            return QIcon.fromTheme("unknown")

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
                    color = "#f48771"  # Red
                elif percent >= 75:
                    color = "#ce9178"  # Orange
                else:
                    color = "#0078d4"  # Blue
                self._disk_bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: #1e1e1e;
                        border: 1px solid #3e3e42;
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
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:
        """
        Handle drop events for both external files and internal file reorganization.

        For remote explorer:
        - External drops (from local filesystem) upload files
        - Internal drops reorganize files into folders

        For local explorer:
        - Move files to the target location
        """
        # First check if we're dropping on a tree item (internal drop)
        item_at_drop = self.tree_widget.itemAt(event.position().toPoint())

        # Check if this is an internal drag (internal MIME format)
        is_internal_drag = event.mimeData().hasFormat("application/x-explorer-items")

        if is_internal_drag or event.source() == self.tree_widget:
            # Internal drop: move selected items into target folder
            if item_at_drop:
                entry = item_at_drop.text(0)
                target_path = os.path.join(self.current_path, entry)

                # Check if target is a directory
                is_target_folder = False
                if self.is_remote:
                    is_target_folder = self._is_remote_directory(target_path)
                else:
                    is_target_folder = os.path.isdir(target_path)

                if is_target_folder:
                    self._handle_internal_drop(target_path)

            self.drag_over = False
            self.update()
            return

        # External drop (from Finder/desktop) — always drop into current directory
        if not event.mimeData().hasUrls():
            self.drag_over = False
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
            self.update()
            return

        # Remote explorer: upload to current directory
        if self.is_remote:
            self.files_dropped.emit(local_paths, self.current_path)
            self.drag_over = False
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
    def paintEvent(self, event) -> None:
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

    def resizeEvent(self, event) -> None:
        """Keep loading spinner sized to tree widget."""
        super().resizeEvent(event)
        self._spinner.resize(self.tree_widget.size())
