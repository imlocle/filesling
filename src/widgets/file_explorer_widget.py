from __future__ import annotations

import os
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
from src.utils.logging_signal import logger


def _get_file_icon(is_dir: bool, filename: str = "") -> QIcon:
    """Get a file/folder icon based on type. Uses colored pixmaps for theme compatibility."""
    from src.utils.icons import get_file_icon

    return get_file_icon(is_dir, filename)


class DragDropTreeWidget(QTreeWidget):
    """Custom QTreeWidget that supports drag-drop, multi-select, and slow-click rename."""

    # Emitted when user slow-clicks to rename: (item, column)
    slow_click_rename = Signal(QTreeWidgetItem, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
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
        # For remote files, download small files to temp dir.
        # Files over 10MB are skipped (user should use right-click → Download).
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, "is_remote"):
            if parent_widget.is_remote and parent_widget.sftp:
                import atexit
                import tempfile

                # Calculate total size to decide if we should download for drag
                MAX_DRAG_BYTES = 10 * 1024 * 1024  # 10MB per file limit
                downloadable = []
                for item_name in item_names:
                    remote_path = os.path.join(parent_widget.current_path, item_name)
                    try:
                        st = parent_widget.sftp.stat(remote_path)
                        size = st.st_size if st.st_size else 0
                        if size <= MAX_DRAG_BYTES:
                            downloadable.append((item_name, remote_path))
                    except Exception:
                        pass  # Can't stat — skip

                if downloadable:
                    temp_dir = tempfile.mkdtemp(prefix="filesling_drag_")
                    atexit.register(
                        lambda d=temp_dir: __import__("shutil").rmtree(
                            d, ignore_errors=True
                        )
                    )
                    urls = []
                    for item_name, remote_path in downloadable:
                        local_temp = os.path.join(temp_dir, item_name)
                        try:
                            parent_widget.sftp.get(remote_path, local_temp)
                            urls.append(QUrl.fromLocalFile(local_temp))
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

    def __init__(self, parent: Optional[QWidget] = None) -> None:
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
        parent: Optional[QObject] = None,
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
                                    or (
                                        self.settings.config.hide_nfo_files
                                        and attr.filename.endswith(".nfo")
                                    )
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
                            or (
                                self.settings.config.hide_nfo_files
                                and a.filename.endswith(".nfo")
                            )
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
                    or (self.settings.config.hide_nfo_files and e.endswith(".nfo"))
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


class _ConvertWorker(QObject):
    """Background worker for remote ffmpeg video conversion."""

    finished = Signal()
    error = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        host: str,
        username: str,
        key_path: str,
        port: int,
        remote_path: str,
        video_codec: str = "libx264",
        preset: str = "fast",
        crf: int = 18,
        audio_args: str = "-c:a aac -b:a 128k",
        container: str = "mp4",
    ) -> None:
        super().__init__()
        self.host = host
        self.username = username
        self.key_path = key_path
        self.port = port
        self.remote_path = remote_path
        self.video_codec = video_codec
        self.preset = preset
        self.crf = crf
        self.audio_args = audio_args
        self.container = container

    def run(self) -> None:
        try:
            from paramiko import AutoAddPolicy, SSHClient

            from src.services.ffmpeg_service import convert_video, replace_original

            # Open a dedicated SSH connection for this conversion
            # so it doesn't block the explorer's SFTP session
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            ssh.connect(
                hostname=self.host,
                username=self.username,
                key_filename=self.key_path,
                port=self.port,
                timeout=10,
            )

            def progress_cb(pct: int) -> None:
                self.progress.emit(pct)

            try:
                output_path = convert_video(
                    ssh_client=ssh,
                    remote_path=self.remote_path,
                    preset=self.preset,
                    crf=self.crf,
                    video_codec=self.video_codec,
                    audio_args=self.audio_args,
                    container=self.container,
                    progress_cb=progress_cb,
                )
                replace_original(ssh, self.remote_path, output_path)
                self.finished.emit()
            finally:
                ssh.close()
        except Exception as e:
            self.error.emit(str(e))


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
        self._sftp_background: Optional[SFTPClient] = None

        # Directory check cache (cleared on refresh) — reduces network calls
        # during drag operations
        self._dir_cache: dict[str, bool] = {}

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

        self._detail_panel = DetailPanel(self.settings)
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

        # Hidden by default — toggle with ⌘I
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

        # Video options (SSH only, video files only)
        convert_action = None
        convert_h265_action = None
        convert_settings_action = None
        media_info_action = None
        edit_metadata_action = None
        quick_fix_action = None
        if self.is_remote and self.sftp:
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
        """Handle moving an item — show a folder picker dialog."""
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
        """Handle moving multiple items — show a folder picker dialog."""
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
        """Handle batch rename — show find/replace dialog."""
        from src.views.dialogs.batch_rename_dialog import execute_batch_rename

        renamed = execute_batch_rename(
            parent=self,
            paths=paths,
            is_remote=self.is_remote,
            sftp=self.sftp,
            settings=self.settings,
        )
        if renamed > 0:
            self.refresh()

    def _handle_convert_video(self, remote_path: str, codec: str = "h264") -> None:
        """Handle video conversion request — delegate to VideoConvertManager."""
        if not hasattr(self, "_convert_manager"):
            from src.widgets.video_convert_manager import VideoConvertManager

            self._convert_manager = VideoConvertManager(self, self.settings)

        self._convert_manager.request_conversion(remote_path, self.sftp, codec=codec)

    def _show_convert_settings(self) -> None:
        """Show the video conversion settings dialog."""
        from src.views.dialogs.convert_settings_dialog import ConvertSettingsDialog

        dialog = ConvertSettingsDialog(self)
        dialog.exec()

    def _show_media_info(self, remote_path: str, open_tab: str = "info") -> None:
        """Show video metadata via ffprobe and allow editing tags."""
        import shlex

        from PySide6.QtWidgets import (
            QDialog,
            QGridLayout,
            QLabel,
            QLineEdit,
            QPlainTextEdit,
            QPushButton,
            QTabWidget,
            QVBoxLayout,
            QWidget,
        )

        if not self.sftp:
            return

        try:
            channel = self.sftp.get_channel()
            if not channel:
                return
            transport = channel.get_transport()
            if not transport:
                return

            # Run ffprobe to get full metadata
            cmd = (
                f"ffprobe -v quiet -print_format json -show_format -show_streams "
                f"{shlex.quote(remote_path)}"
            )
            session = transport.open_session()
            session.exec_command(cmd)

            output = b""
            while True:
                chunk = session.recv(4096)
                if not chunk:
                    break
                output += chunk
            session.close()

            raw_json = output.decode("utf-8", errors="ignore").strip()
            if not raw_json:
                logger.warn("Media Info: ffprobe returned no output")
                return

            import json

            data = json.loads(raw_json)
            fmt = data.get("format", {})
            tags = fmt.get("tags", {})
            filename = os.path.basename(remote_path)

            # --- Build dialog ---
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Media Info — {filename}")
            dialog.setMinimumSize(550, 500)

            dlg_layout = QVBoxLayout(dialog)

            tabs = QTabWidget()
            dlg_layout.addWidget(tabs)

            # === Tab 1: Info ===
            info_widget = QWidget()
            info_layout = QVBoxLayout(info_widget)
            info_text = QPlainTextEdit()
            info_text.setReadOnly(True)
            info_text.setStyleSheet("font-family: monospace; font-size: 12px;")

            lines = []
            lines.append(f"File: {filename}")
            lines.append(f"Format: {fmt.get('format_long_name', 'Unknown')}")

            duration_secs = float(fmt.get("duration", 0))
            if duration_secs > 0:
                hours = int(duration_secs // 3600)
                mins = int((duration_secs % 3600) // 60)
                secs = int(duration_secs % 60)
                lines.append(f"Duration: {hours:02d}:{mins:02d}:{secs:02d}")

            size_bytes = int(fmt.get("size", 0))
            if size_bytes > 0:
                size_mb = size_bytes / (1024 * 1024)
                lines.append(f"Size: {size_mb:.1f} MB")

            bitrate = int(fmt.get("bit_rate", 0))
            if bitrate > 0:
                lines.append(f"Overall Bitrate: {bitrate // 1000} kbps")

            lines.append("")

            streams = data.get("streams", [])
            for i, stream in enumerate(streams):
                codec_type = stream.get("codec_type", "unknown")
                codec_name = stream.get("codec_name", "unknown")
                codec_long = stream.get("codec_long_name", "")

                if codec_type == "video":
                    width = stream.get("width", "?")
                    height = stream.get("height", "?")
                    fps_str = stream.get("r_frame_rate", "")
                    fps = ""
                    if fps_str and "/" in fps_str:
                        num, den = fps_str.split("/")
                        try:
                            fps = f"{int(num) / int(den):.2f} fps"
                        except (ValueError, ZeroDivisionError):
                            fps = fps_str

                    pix_fmt = stream.get("pix_fmt", "")
                    profile = stream.get("profile", "")
                    vbitrate = int(stream.get("bit_rate", 0))

                    lines.append(f"━━━ Video Stream #{i} ━━━")
                    lines.append(f"  Codec: {codec_name} ({codec_long})")
                    if profile:
                        lines.append(f"  Profile: {profile}")
                    lines.append(f"  Resolution: {width}×{height}")
                    if fps:
                        lines.append(f"  Frame Rate: {fps}")
                    if pix_fmt:
                        lines.append(f"  Pixel Format: {pix_fmt}")
                    if vbitrate > 0:
                        lines.append(f"  Bitrate: {vbitrate // 1000} kbps")

                elif codec_type == "audio":
                    sample_rate = stream.get("sample_rate", "?")
                    channels = stream.get("channels", "?")
                    abitrate = int(stream.get("bit_rate", 0))
                    lang = stream.get("tags", {}).get("language", "")

                    lines.append(f"━━━ Audio Stream #{i} ━━━")
                    lines.append(f"  Codec: {codec_name} ({codec_long})")
                    lines.append(f"  Sample Rate: {sample_rate} Hz")
                    lines.append(f"  Channels: {channels}")
                    if abitrate > 0:
                        lines.append(f"  Bitrate: {abitrate // 1000} kbps")
                    if lang:
                        lines.append(f"  Language: {lang}")

                elif codec_type == "subtitle":
                    lang = stream.get("tags", {}).get("language", "")
                    lines.append(f"━━━ Subtitle Stream #{i} ━━━")
                    lines.append(f"  Codec: {codec_name}")
                    if lang:
                        lines.append(f"  Language: {lang}")

                lines.append("")

            info_text.setPlainText("\n".join(lines))
            info_layout.addWidget(info_text)
            tabs.addTab(info_widget, "Info")

            # === Tab 2: Tags (editable via NFO sidecar) ===
            from PySide6.QtWidgets import QScrollArea

            tags_scroll = QScrollArea()
            tags_scroll.setWidgetResizable(True)
            tags_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

            tags_widget = QWidget()
            tags_layout = QVBoxLayout(tags_widget)

            hint = QLabel(
                "Metadata is saved as an .nfo file next to the video.\n"
                "Jellyfin reads .nfo files automatically on library scan."
            )
            hint.setObjectName("secondary_label")
            hint.setWordWrap(True)
            tags_layout.addWidget(hint)

            # --- Read existing NFO if it exists (priority over embedded tags) ---
            nfo_path = os.path.splitext(remote_path)[0] + ".nfo"
            nfo_data = {}
            try:
                sess = transport.open_session()
                sess.exec_command(f"cat {shlex.quote(nfo_path)} 2>/dev/null")
                nfo_content = b""
                while True:
                    chunk = sess.recv(4096)
                    if not chunk:
                        break
                    nfo_content += chunk
                sess.close()
                if nfo_content.strip():
                    import xml.etree.ElementTree as ET

                    root = ET.fromstring(nfo_content.decode("utf-8", errors="ignore"))
                    for elem in root:
                        if elem.text:
                            key = elem.tag.lower()
                            # Accumulate multiple genre tags
                            if key in nfo_data and key == "genre":
                                nfo_data[key] += ";" + elem.text.strip()
                            else:
                                nfo_data[key] = elem.text.strip()
            except Exception:
                pass  # No NFO or can't read — use embedded tags

            # Merge: NFO takes priority, then embedded tags
            def _get_value(key: str) -> str:
                # Map our key names to NFO element names
                nfo_key_map = {
                    "sort_name": "sorttitle",
                    "show": "showtitle",
                    "season_number": "season",
                    "episode_sort": "episode",
                    "date": "year",
                    "album": "set",
                    "description": "plot",
                    "publisher": "studio",
                }
                nfo_key = nfo_key_map.get(key, key)
                # Check NFO first
                val = nfo_data.get(nfo_key, "") or nfo_data.get(key, "")
                if val:
                    return val
                # Fall back to embedded tags
                return tags.get(key, "") or tags.get(key.upper(), "") or ""

            # Auto-populate title with filename if no title exists anywhere
            auto_title = _get_value("title")
            if not auto_title:
                auto_title = os.path.splitext(filename)[0]

            # Editable tag fields
            tag_fields = {}
            grid = QGridLayout()
            grid.setSpacing(8)

            # Common tags (always visible)
            common_tags = [
                ("title", "Title"),
                ("sort_name", "Sort Title"),
                ("artist", "Artist"),
                ("director", "Director"),
                ("album", "Album / Series"),
                ("show", "Show Name"),
                ("season_number", "Season"),
                ("episode_sort", "Episode #"),
                ("date", "Date / Year"),
                ("genre", "Genre"),
                ("description", "Description"),
            ]

            # Advanced tags (hidden by default)
            advanced_tags = [
                ("track", "Track Number"),
                ("disc", "Disc Number"),
                ("composer", "Composer"),
                ("performer", "Performer"),
                ("publisher", "Publisher / Studio"),
                ("copyright", "Copyright"),
                ("language", "Language"),
                ("network", "Network"),
                ("synopsis", "Synopsis"),
                ("grouping", "Grouping"),
                ("lyrics", "Lyrics"),
                ("rating", "Rating"),
                ("comment", "Comment"),
                ("sort_artist", "Sort Artist"),
                ("sort_album", "Sort Album"),
                ("compilation", "Compilation"),
                ("encoded_by", "Encoded By"),
                ("url", "URL"),
            ]

            # Placeholder examples and tooltips
            field_hints = {
                "title": ("e.g., The Challenge", "Display name in Jellyfin."),
                "sort_name": (
                    "e.g., 01",
                    "Controls sort order. Set to '01' to sort first.",
                ),
                "artist": ("e.g., Tony Horton", "Creator, performer, or main actor."),
                "director": ("e.g., Christopher Nolan", "Director of the video."),
                "album": ("e.g., P90X3", "Collection or series group."),
                "show": ("e.g., P90X3", "TV show or series name."),
                "season_number": ("e.g., 1", "Season or disc number."),
                "episode_sort": ("e.g., 5", "Episode number for ordering."),
                "date": ("e.g., 2014", "Year or full date (YYYY-MM-DD)."),
                "genre": ("e.g., Fitness;Workout", "Use semicolons for multiple."),
                "description": (
                    "e.g., Full body strength workout",
                    "Short summary or plot.",
                ),
                "track": ("e.g., 3", "Track number within an album/disc."),
                "disc": ("e.g., 2", "Disc number in a multi-disc set."),
                "composer": ("e.g., Hans Zimmer", "Music composer."),
                "performer": ("e.g., Tony Horton", "Main performer or actor."),
                "publisher": ("e.g., Beachbody", "Publisher, studio, or distributor."),
                "copyright": ("e.g., © 2014 Beachbody", "Copyright notice."),
                "language": ("e.g., eng, jpn", "Primary language (ISO 639 code)."),
                "network": ("e.g., Netflix, HBO", "Network or streaming platform."),
                "synopsis": ("e.g., A detailed plot summary...", "Full plot synopsis."),
                "grouping": ("e.g., Phase 1", "Content grouping or phase."),
                "lyrics": ("e.g., Song lyrics...", "Lyrics or transcript."),
                "rating": ("e.g., TV-PG, PG-13", "Content rating."),
                "comment": ("e.g., Ripped from DVD", "Freeform notes."),
                "sort_artist": ("e.g., Horton, Tony", "Sort order for artist."),
                "sort_album": ("e.g., P90X3 Season 1", "Sort order for album."),
                "compilation": ("e.g., 1", "Set to 1 if part of a compilation."),
                "encoded_by": ("e.g., HandBrake 1.6", "Encoding software."),
                "url": ("e.g., https://...", "Related URL."),
            }

            row = 0
            for key, label in common_tags:
                value = auto_title if key == "title" else _get_value(key)
                grid.addWidget(QLabel(label + ":"), row, 0)
                field = QLineEdit(value)
                h = field_hints.get(key)
                if h:
                    field.setPlaceholderText(h[0])
                    field.setToolTip(h[1])
                grid.addWidget(field, row, 1)
                tag_fields[key] = field
                row += 1

            tags_layout.addLayout(grid)

            # "Show More" expandable section
            advanced_container = QWidget()
            advanced_layout_inner = QVBoxLayout(advanced_container)
            advanced_layout_inner.setContentsMargins(0, 0, 0, 0)
            advanced_layout_inner.setSpacing(4)
            advanced_container.setVisible(False)

            advanced_grid = QGridLayout()
            advanced_grid.setSpacing(8)
            adv_row = 0

            for key, label in advanced_tags:
                value = _get_value(key)
                advanced_grid.addWidget(QLabel(label + ":"), adv_row, 0)
                field = QLineEdit(value)
                h = field_hints.get(key)
                if h:
                    field.setPlaceholderText(h[0])
                    field.setToolTip(h[1])
                advanced_grid.addWidget(field, adv_row, 1)
                tag_fields[key] = field
                adv_row += 1

            advanced_layout_inner.addLayout(advanced_grid)
            tags_layout.addWidget(advanced_container)

            show_more_btn = QPushButton("▶ Show All Tags")
            show_more_btn.setObjectName("subtle_btn")
            show_more_btn.setMaximumWidth(140)

            def _toggle_advanced() -> None:
                visible = not advanced_container.isVisible()
                advanced_container.setVisible(visible)
                show_more_btn.setText("▼ Show Less" if visible else "▶ Show All Tags")

            show_more_btn.clicked.connect(_toggle_advanced)
            tags_layout.addWidget(show_more_btn)

            # Show any extra tags from NFO that aren't in our standard lists
            all_known_keys = {k for k, _ in common_tags + advanced_tags}
            # Also map NFO element names back to our keys
            reverse_nfo_map = {
                v: k
                for k, v in {
                    "sort_name": "sorttitle",
                    "show": "showtitle",
                    "season_number": "season",
                    "episode_sort": "episode",
                    "date": "year",
                    "album": "set",
                    "description": "plot",
                    "publisher": "studio",
                }.items()
            }
            all_nfo_known = set(reverse_nfo_map.keys()) | {
                k for k, _ in common_tags + advanced_tags
            }

            extra_nfo_tags = {}
            skip_nfo_keys = {"actor", "thumb", "fanart", "uniqueid", "fileinfo"}
            for nfo_key, value in nfo_data.items():
                if nfo_key in skip_nfo_keys:
                    continue
                # Check if this maps to a known field
                mapped_key = reverse_nfo_map.get(nfo_key, nfo_key)
                if mapped_key not in all_known_keys and nfo_key not in all_nfo_known:
                    extra_nfo_tags[nfo_key] = value

            if extra_nfo_tags:
                for key, value in extra_nfo_tags.items():
                    advanced_grid.addWidget(QLabel(f"{key}:"), adv_row, 0)
                    field = QLineEdit(value)
                    field.setPlaceholderText("(custom tag)")
                    advanced_grid.addWidget(field, adv_row, 1)
                    tag_fields[key] = field
                    adv_row += 1
                # Show advanced section if there are custom tags
                advanced_container.setVisible(True)
                show_more_btn.setText("▼ Show Less")

            # Add custom tag button
            def _add_custom_tag() -> None:
                from PySide6.QtWidgets import QInputDialog

                tag_name, ok = QInputDialog.getText(
                    dialog,
                    "Add Tag",
                    "Tag name (e.g., 'composer', 'copyright', 'network'):",
                )
                if ok and tag_name.strip():
                    tag_name = tag_name.strip().lower().replace(" ", "_")
                    if tag_name in tag_fields:
                        tag_fields[tag_name].setFocus()
                        return
                    nonlocal adv_row
                    advanced_grid.addWidget(QLabel(f"{tag_name}:"), adv_row, 0)
                    field = QLineEdit("")
                    field.setPlaceholderText("(empty)")
                    field.setFocus()
                    advanced_grid.addWidget(field, adv_row, 1)
                    tag_fields[tag_name] = field
                    adv_row += 1
                    advanced_container.setVisible(True)
                    show_more_btn.setText("▼ Show Less")

            add_tag_btn = QPushButton("+ Add Tag")
            add_tag_btn.setToolTip("Add a custom metadata tag.")
            add_tag_btn.setMaximumWidth(100)
            add_tag_btn.clicked.connect(_add_custom_tag)
            tags_layout.addWidget(add_tag_btn)

            tags_layout.addStretch()

            # Save button — writes .nfo file
            save_btn = QPushButton("💾 Save")
            save_btn.setToolTip(
                "Saves metadata as an .nfo file next to the video.\n"
                "Jellyfin reads this automatically. Instant, doesn't touch the video."
            )

            def _save_nfo() -> None:
                # Map our field keys to Jellyfin NFO XML element names
                key_to_nfo = {
                    "title": "title",
                    "sort_name": "sorttitle",
                    "artist": "artist",
                    "director": "director",
                    "album": "set",
                    "show": "showtitle",
                    "season_number": "season",
                    "episode_sort": "episode",
                    "date": "year",
                    "genre": "genre",
                    "description": "plot",
                    "track": "track",
                    "disc": "disc",
                    "composer": "composer",
                    "performer": "actor",
                    "publisher": "studio",
                    "copyright": "copyright",
                    "language": "language",
                    "network": "network",
                    "synopsis": "outline",
                    "rating": "mpaa",
                    "comment": "comment",
                    "sort_artist": "sortartist",
                    "sort_album": "sortset",
                    "url": "website",
                }

                # Auto-detect NFO type from filled fields
                has_season = bool(
                    tag_fields.get("season_number", None)
                    and tag_fields["season_number"].text().strip()
                )
                has_episode = bool(
                    tag_fields.get("episode_sort", None)
                    and tag_fields["episode_sort"].text().strip()
                )
                has_artist = bool(
                    tag_fields.get("artist", None)
                    and tag_fields["artist"].text().strip()
                )
                has_director = bool(
                    tag_fields.get("director", None)
                    and tag_fields["director"].text().strip()
                )

                if has_season or has_episode:
                    root_tag = "episodedetails"
                elif has_artist and not has_director:
                    root_tag = "musicvideo"
                else:
                    root_tag = "movie"

                # Build XML
                lines = ['<?xml version="1.0" encoding="utf-8"?>', f"<{root_tag}>"]
                for key, field in tag_fields.items():
                    value = field.text().strip()
                    if not value:
                        continue
                    nfo_tag = key_to_nfo.get(key, key)
                    # Genre: split on semicolons into separate elements
                    if key == "genre":
                        for g in value.split(";"):
                            g = g.strip()
                            if g:
                                lines.append(f"  <genre>{g}</genre>")
                    # Skip people fields here — handled below as <actor> entries
                    elif key in ("artist", "director", "performer", "composer"):
                        # Still write the dedicated tag (e.g., <director>)
                        value = (
                            value.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )
                        lines.append(f"  <{nfo_tag}>{value}</{nfo_tag}>")
                    else:
                        # Escape XML special chars
                        value = (
                            value.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )
                        lines.append(f"  <{nfo_tag}>{value}</{nfo_tag}>")

                # Auto-generate <actor> entries for Jellyfin's People section
                people_roles = {
                    "director": "Director",
                    "artist": "Artist",
                    "performer": "Actor",
                    "composer": "Composer",
                }
                for key, role in people_roles.items():
                    field = tag_fields.get(key)
                    if not field:
                        continue
                    value = field.text().strip()
                    if not value:
                        continue
                    # Support multiple names separated by semicolons
                    for name in value.split(";"):
                        name = name.strip()
                        if not name:
                            continue
                        safe_name = (
                            name.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )
                        lines.append("  <actor>")
                        lines.append(f"    <name>{safe_name}</name>")
                        lines.append(f"    <role>{role}</role>")
                        lines.append("  </actor>")

                lines.append(f"</{root_tag}>")
                nfo_content = "\n".join(lines) + "\n"

                # Write NFO file directly via SFTP (instant, no shell overhead)
                try:
                    with self.sftp.open(nfo_path, "w") as f:
                        f.write(nfo_content.encode("utf-8"))

                    logger.success(f"NFO saved: {os.path.basename(nfo_path)}")
                    dialog.accept()

                    # Add the NFO file to the tree directly (no full refresh needed)
                    nfo_filename = os.path.basename(nfo_path)
                    if not self.settings.config.hide_nfo_files:
                        # Check if it's already in the tree
                        exists = False
                        for i in range(self.tree_widget.topLevelItemCount()):
                            if self.tree_widget.topLevelItem(i).text(0) == nfo_filename:
                                exists = True
                                break
                        if not exists:
                            from src.widgets.file_explorer_widget import (
                                SortableTreeWidgetItem,
                                _get_file_icon,
                            )

                            size_str = f"{len(nfo_content)} B"
                            item = SortableTreeWidgetItem([nfo_filename, size_str])
                            item.setIcon(0, _get_file_icon(False, nfo_filename))
                            item.setData(1, Qt.ItemDataRole.UserRole, len(nfo_content))
                            self.tree_widget.addTopLevelItem(item)
                except Exception as e:
                    logger.error(f"NFO write error: {e}")
                    from PySide6.QtWidgets import QMessageBox

                    QMessageBox.warning(
                        dialog,
                        "Save Failed",
                        f"Failed to write .nfo file:\n{e}",
                    )

            save_btn.clicked.connect(_save_nfo)
            tags_layout.addWidget(save_btn)

            tags_scroll.setWidget(tags_widget)
            tabs.addTab(tags_scroll, "Tags")

            # Open on requested tab
            tabs.setCurrentIndex(1 if open_tab == "tags" else 0)

            dialog.exec()

        except Exception as e:
            logger.error(f"Media Info: Failed to get metadata: {e}")

    def _quick_fix_video(self, remote_path: str) -> None:
        """Show Quick Fix dialog and apply selected fixes (no re-encoding)."""
        import shlex

        from PySide6.QtWidgets import QMessageBox

        from src.views.dialogs.quick_fix_dialog import QuickFixDialog

        if not self.sftp:
            return

        filename = os.path.basename(remote_path)
        ext = os.path.splitext(remote_path)[1]

        dialog = QuickFixDialog(self, filename, ext)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        opts = dialog.options

        try:
            channel = self.sftp.get_channel()
            if not channel or not channel.get_transport():
                QMessageBox.warning(self, "Error", "No SSH connection available.")
                return
            transport = channel.get_transport()
        except Exception:
            return

        # Determine output extension
        base = os.path.splitext(remote_path)[0]
        out_ext = ".mp4" if opts.to_mp4 else ext

        # Build ffmpeg command
        tmp_path = f"{base}_fixed{out_ext}"
        cmd_parts = ["ffmpeg", "-y"]

        if opts.fix_timestamps:
            cmd_parts.extend(["-fflags", "+genpts"])

        cmd_parts.extend(["-i", shlex.quote(remote_path)])
        cmd_parts.extend(["-c", "copy"])

        if opts.strip_subtitles:
            cmd_parts.append("-sn")

        if opts.to_mp4:
            cmd_parts.extend(["-movflags", "+faststart"])

        cmd_parts.append(shlex.quote(tmp_path))
        cmd_parts.append("2>/dev/null")

        cmd = " ".join(cmd_parts)

        # Build replace command
        if out_ext.lower() != ext.lower():
            final_path = f"{base}{out_ext}"
            full_cmd = (
                f"{cmd} && rm -f {shlex.quote(remote_path)} "
                f"&& mv {shlex.quote(tmp_path)} {shlex.quote(final_path)}"
            )
        else:
            full_cmd = f"{cmd} && mv {shlex.quote(tmp_path)} {shlex.quote(remote_path)}"

        # Execute
        actions = []
        if opts.to_mp4:
            actions.append("container → MP4")
        if opts.fix_timestamps:
            actions.append("fix timestamps")
        if opts.strip_subtitles:
            actions.append("remove subtitles")
        logger.info(f"Quick Fix: {filename} ({', '.join(actions)})")

        try:
            session = transport.open_session()
            session.exec_command(full_cmd)
            exit_code = session.recv_exit_status()
            session.close()

            if exit_code == 0:
                logger.success(f"Quick Fix complete: {filename}")
                QMessageBox.information(
                    self,
                    "Fix Applied",
                    f"'{filename}' fixed successfully.\n\n"
                    f"Applied: {', '.join(actions)}.\n"
                    "No re-encoding — video quality unchanged.",
                )
                self.refresh()
            else:
                logger.error(f"Quick Fix failed: exit code {exit_code}")
                QMessageBox.warning(
                    self,
                    "Fix Failed",
                    f"ffmpeg exited with code {exit_code}.\n"
                    "The original file was not modified.",
                )
        except Exception as e:
            logger.error(f"Quick Fix error: {e}")
            QMessageBox.critical(self, "Error", f"Failed to fix video:\n{e}")

    # ------------------------------------------------------------------
    #  Core Refresh / Navigation
    # ------------------------------------------------------------------
    def refresh(self, path: Optional[str] = None) -> None:
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

        # Cancel any existing load — wait for it to finish to avoid
        # overlapping SFTP calls on the same channel (causes freezes)
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                try:
                    self._loader_worker.finished.disconnect()  # type: ignore
                    self._loader_worker.error.disconnect()  # type: ignore
                    if hasattr(self._loader_worker, "batch_ready"):
                        self._loader_worker.batch_ready.disconnect()  # type: ignore
                except (RuntimeError, TypeError):
                    pass
                self._loader_thread.quit()
                # Wait briefly — if SFTP call is in-flight, let it finish
                self._loader_thread.wait(500)
                if self._loader_thread.isRunning():
                    # Still running — detach and let it die on its own
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

    def _on_load_finished(self, results: list) -> None:
        """Handle background load completion."""
        self._spinner.stop()
        self.back_btn.setEnabled(True)

        # Re-enable sorting now that all items are loaded
        self.tree_widget.setSortingEnabled(True)

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
        self.back_btn.setEnabled(True)
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
                    or (self.settings.config.hide_nfo_files and e.endswith(".nfo"))
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
        if not self.back_btn.isEnabled():
            return  # Already loading
        self.current_path = os.path.dirname(self.current_path)
        self._detail_panel.clear()
        self.refresh()
        self.directory_changed.emit(self.current_path)

    def set_sftp(self, sftp: Optional[SFTPClient]) -> None:
        self.sftp = sftp
        # Detail panel gets the metadata channel if available (from connection manager)
        # Falls back to the main sftp if not (ADB/iOS connections)
        self._detail_panel.set_sftp(sftp)

    def set_sftp_background(self, sftp: Optional[SFTPClient]) -> None:
        """Set dedicated SFTP channel for background operations (dir loading, disk usage)."""
        self._sftp_background = sftp

    def _on_item_selected(self) -> None:
        items = self.tree_widget.selectedItems()
        if not items:
            self.item_selected.emit("")
            self._detail_panel.clear()
            return
        # For multi-select, emit the first selected item (or could emit all)
        item = items[0]
        entry = item.text(0)  # Get name from first column
        full_path = os.path.join(self.current_path, entry)
        self.item_selected.emit(full_path)

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
        """Called after 300ms debounce — show detail panel for selected file."""
        path = getattr(self, "_pending_detail_path", "")
        size_str = getattr(self, "_pending_detail_size", "")
        if not path:
            return

        entry = os.path.basename(path)

        # Skip folders entirely (no network calls)
        is_dir = False
        if self.is_remote:
            # Check from tree item data or cache
            size_data = None
            for i in range(self.tree_widget.topLevelItemCount()):
                it = self.tree_widget.topLevelItem(i)
                if it and it.text(0) == entry:
                    size_data = it.data(1, Qt.ItemDataRole.UserRole)
                    break
            is_dir = size_data is not None and size_data < 0
        else:
            is_dir = os.path.isdir(path)

        if is_dir:
            # Just show folder name, no network calls
            self._detail_panel.show_folder(entry)
        else:
            self._detail_panel.show_file(path, size_str)

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
        """Start inline editing using InlineRenameEditor."""
        if not hasattr(self, "_rename_editor_widget"):
            from src.widgets.inline_rename_editor import InlineRenameEditor

            self._rename_editor_widget = InlineRenameEditor(
                tree_widget=self.tree_widget,
                settings=self.settings,
                is_remote=self.is_remote,
                sftp=self.sftp,
                get_current_path=lambda: self.current_path,
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
        is_light = app is not None and app.property("filesling_theme") == "light"
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
