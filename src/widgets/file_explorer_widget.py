from __future__ import annotations

import os
import shutil
from stat import S_ISDIR
from typing import List, Optional

from paramiko import SFTPClient
from PySide6.QtCore import QPoint, QRectF, Qt, QUrl, Signal, QMimeData, QTimer, QThread, QObject
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QMouseEvent,
    QDrag,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings
from src.utils.logging_signal import logger


class DragDropTreeWidget(QTreeWidget):
    """Custom QTreeWidget that supports drag-drop while maintaining multi-select."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = None
        self._drag_start_items = []

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Track mouse press for potential drag operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_items = [item.text(0) for item in self.selectedItems()]
        super().mousePressEvent(event)

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
        pen = QPen(self._color, self._line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
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
    error = Signal(str)

    def __init__(self, path: str, is_remote: bool, sftp: Optional[SFTPClient],
                 settings: Settings, parent=None):
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
                entries = self.sftp.listdir(self.path)
            else:
                entries = os.listdir(self.path)

            filtered = [
                e for e in entries
                if not (e.startswith(".") or e.startswith("._") or e in self.settings.skip_files)
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

        # Background loading state
        self._loader_thread: Optional[QThread] = None
        self._loader_worker: Optional[DirectoryLoader] = None

        # ------------------------------------------------------------------
        # Layout / Header
        # ------------------------------------------------------------------
        layout: QVBoxLayout = QVBoxLayout(self)
        header_layout: QHBoxLayout = QHBoxLayout()

        self.back_btn: QPushButton = QPushButton("←")
        self.title_label: QLabel = QLabel(f"{self.title} ({self.current_path})")
        self.title_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        header_layout.addWidget(self.back_btn)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

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

        # ------------------------------------------------------------------
        # Loading spinner (overlays the tree widget)
        # ------------------------------------------------------------------
        self._spinner = LoadingSpinner(self.tree_widget)

        self.back_btn.clicked.connect(self.go_back)
        self.tree_widget.itemSelectionChanged.connect(self._on_item_selected)
        self.tree_widget.itemDoubleClicked.connect(self.navigate)

        # Context menu
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)

        # Drag & drop (both local + remote; remote emits files_dropped)
        self.setAcceptDrops(True)
        self.tree_widget.setAcceptDrops(True)

        self.refresh()

    # ------------------------------------------------------------------
    #  Context menu (create / delete / rename / move)
    # ------------------------------------------------------------------
    def show_context_menu(self, position: QPoint) -> None:
        item = self.tree_widget.itemAt(position)

        menu = QMenu(self)

        # "New Folder" is available when clicking on empty space or any item
        new_folder_action = menu.addAction("📁 New Folder")
        menu.addSeparator()

        if not item:
            # No item selected, only show "New Folder"
            action = menu.exec(self.tree_widget.mapToGlobal(position))
            if action == new_folder_action:
                self._prompt_and_create_folder()
            return

        entry = item.text(0)  # Get name from first column
        full_path = os.path.join(self.current_path, entry)

        delete_action = menu.addAction("🗑️ Delete")
        rename_action = menu.addAction("✏️ Rename")
        move_action = menu.addAction("↔️ Move To")

        action = menu.exec(self.tree_widget.mapToGlobal(position))

        if action == new_folder_action:
            self._prompt_and_create_folder()
        elif action == delete_action:
            self.file_delete_requested.emit(full_path)
        elif action == rename_action:
            self.file_rename_requested.emit(full_path)
        elif action == move_action:
            self._handle_move_item(full_path)

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
        """Handle moving an item to a new location."""
        basename = os.path.basename(src_path)
        dest_path, ok = QInputDialog.getText(
            self,
            "Move Item",
            f"Move '{basename}' to (full path):",
            text=self.current_path,
        )
        if ok and dest_path.strip():
            dest_path = dest_path.strip()
            # If user provided just a directory path, append the basename
            if os.path.basename(dest_path) == "" or dest_path == os.path.dirname(
                dest_path
            ):
                dest_path = os.path.join(dest_path, basename)
            self.item_move_requested.emit(src_path, dest_path)

    # ------------------------------------------------------------------
    #  Core Refresh / Navigation
    # ------------------------------------------------------------------
    def refresh(self, path: str | None = None) -> None:
        if path is not None:
            self.current_path = path

        self.tree_widget.clear()

        # Update title with disk usage for remote explorer
        title_text = f"{self.title} ({self.current_path})"
        self.title_label.setText(title_text)

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

        # Wait for any existing load to finish before starting a new one
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                self._loader_thread.quit()
                self._loader_thread.wait(3000)
            # Clean up the old thread safely (it's finished now)
            self._loader_thread.deleteLater()
            self._loader_thread = None
        if self._loader_worker is not None:
            self._loader_worker.deleteLater()
            self._loader_worker = None

        # Show spinner
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
        self._loader_worker.finished.connect(self._on_load_finished)
        self._loader_worker.error.connect(self._on_load_error)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_worker.error.connect(self._loader_thread.quit)

        self._loader_thread.start()

    def _on_load_finished(self, results: list) -> None:
        """Handle background load completion."""
        self._spinner.stop()
        self.tree_widget.clear()

        # Update title with disk usage
        title_text = f"{self.title} ({self.current_path})"
        if self.is_remote and self.sftp:
            try:
                disk_usage = self._get_disk_usage()
                if disk_usage:
                    title_text = f"{self.title} ({self.current_path}) - {disk_usage}"
            except Exception:
                pass
        self.title_label.setText(title_text)

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
        self.title_label.setText(f"{self.title} ({self.current_path})")

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

            # Execute df command to get disk usage
            # -B1 gives output in bytes for accurate calculation
            session = transport.open_session()
            session.exec_command(f"df -B1 {self.root_path} | tail -1")

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
            except Exception as e:
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
