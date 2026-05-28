"""
Transfer queue widget — shows pending, in-progress, and completed transfers.
"""

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.utils.constants import (
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_UPLOADING,
)


class TransferStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TransferItem:
    """Represents a single transfer in the queue."""

    display_name: str
    total_bytes: int = 0
    transferred_bytes: int = 0
    destination: str = ""
    status: TransferStatus = TransferStatus.PENDING
    error_message: str = ""
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def progress_percent(self) -> int:
        if self.total_bytes <= 0:
            return 0
        return min(100, int(self.transferred_bytes * 100 / self.total_bytes))

    @property
    def speed_bytes_per_sec(self) -> float:
        if self.start_time <= 0 or self.transferred_bytes <= 0:
            return 0.0
        elapsed = (self.end_time or time.time()) - self.start_time
        if elapsed <= 0:
            return 0.0
        return self.transferred_bytes / elapsed

    @property
    def eta_seconds(self) -> Optional[float]:
        speed = self.speed_bytes_per_sec
        if speed <= 0 or self.total_bytes <= 0:
            return None
        remaining = self.total_bytes - self.transferred_bytes
        return remaining / speed


class TransferItemWidget(QFrame):
    """Widget for a single transfer item in the queue."""

    retry_requested = Signal(int)  # index
    cancel_requested = Signal(int)  # index

    def __init__(
        self, index: int, item: TransferItem, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.item = item
        self.setObjectName("transfer_item")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Top row: name + status + cancel
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.name_label = QLabel(item.display_name)
        name_font = QFont()
        name_font.setWeight(QFont.Weight.Medium)
        self.name_label.setFont(name_font)
        self.name_label.setMaximumWidth(400)
        self.name_label.setWordWrap(False)

        # Show destination path if available
        if item.destination:
            # Use a compact relative-style path
            dest_display = item.destination
            if len(dest_display) > 50:
                dest_display = "…" + dest_display[-47:]
            self.name_label.setText(f"{item.display_name}")
            self.name_label.setToolTip(f"{item.display_name} → {item.destination}")
            self.dest_label = QLabel(f"→ {dest_display}")
            self.dest_label.setObjectName("secondary_label")
            self.dest_label.setStyleSheet("font-size: 10px;")
        else:
            self.dest_label = None

        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-size: 11px;")

        self.cancel_btn = QPushButton("x")
        self.cancel_btn.setObjectName("subtle_btn")
        self.cancel_btn.setMaximumWidth(20)
        self.cancel_btn.setMaximumHeight(20)
        self.cancel_btn.setToolTip("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.index))
        self.cancel_btn.setVisible(False)

        self.finder_btn = QPushButton("Show in Finder")
        self.finder_btn.setMaximumHeight(22)
        self.finder_btn.setVisible(False)
        self.finder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.finder_btn.clicked.connect(self._reveal_in_finder)

        top_row.addWidget(self.name_label, stretch=1)
        top_row.addWidget(self.status_label)
        top_row.addWidget(self.cancel_btn)
        top_row.addWidget(self.finder_btn)

        layout.addLayout(top_row)

        # Destination path (if available)
        if self.dest_label:
            layout.addWidget(self.dest_label)

        # Progress bar (only for in-progress)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximumHeight(14)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Bottom row: speed + ETA or error
        self.detail_label = QLabel()
        self.detail_label.setObjectName("secondary_label")
        layout.addWidget(self.detail_label)

        # Retry button (hidden by default)
        self.retry_btn = QPushButton("↻ Retry")
        self.retry_btn.setMaximumWidth(60)
        self.retry_btn.setMaximumHeight(22)
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.index))
        layout.addWidget(self.retry_btn)

        self.update_display()

    def update_display(self) -> None:
        """Update the widget to reflect current item state."""
        item = self.item

        if item.status == TransferStatus.PENDING:
            self.status_label.setText(STATUS_QUEUED)
            self.status_label.setObjectName("status_pending")
            self.status_label.style().polish(self.status_label)
            self.progress_bar.setVisible(False)
            self.detail_label.setVisible(False)
            self.retry_btn.setVisible(False)
            self.finder_btn.setVisible(False)
            self.cancel_btn.setVisible(True)

        elif item.status == TransferStatus.IN_PROGRESS:
            is_download = item.display_name.startswith("⬇")
            if is_download:
                self.status_label.setText(STATUS_DOWNLOADING)
            else:
                self.status_label.setText(STATUS_UPLOADING)
            self.status_label.setObjectName("status_active")
            self.status_label.style().polish(self.status_label)
            self.progress_bar.setVisible(True)

            # If no progress data yet, show indeterminate (pulsing) bar
            if item.progress_percent == 0 and item.transferred_bytes == 0:
                self.progress_bar.setRange(0, 0)  # indeterminate
            else:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(item.progress_percent)

            self.detail_label.setVisible(True)
            self.retry_btn.setVisible(False)
            self.finder_btn.setVisible(False)
            self.cancel_btn.setVisible(True)

            # Speed and ETA
            speed = item.speed_bytes_per_sec
            eta = item.eta_seconds
            parts = []
            if speed > 0:
                parts.append(f"{_format_speed(speed)}")
            if eta is not None and eta > 0:
                parts.append(f"ETA: {_format_time(eta)}")
            parts.append(f"{item.progress_percent}%")
            self.detail_label.setText(" · ".join(parts))

        elif item.status == TransferStatus.COMPLETED:
            self.status_label.setText("✅ Done")
            self.status_label.setObjectName("status_success")
            self.status_label.style().polish(self.status_label)
            self.progress_bar.setVisible(False)
            self.detail_label.setVisible(True)
            self.retry_btn.setVisible(False)
            self.cancel_btn.setVisible(False)

            # Show "Show in Finder" for completed downloads
            is_download = item.display_name.startswith("⬇")
            self.finder_btn.setVisible(is_download)

            # Show duration
            if item.start_time and item.end_time:
                duration = item.end_time - item.start_time
                speed = item.speed_bytes_per_sec
                parts = [f"{_format_time(duration)}"]
                if speed > 0:
                    parts.append(f"avg {_format_speed(speed)}")
                self.detail_label.setText(" · ".join(parts))
            else:
                self.detail_label.setText("")

        elif item.status == TransferStatus.FAILED:
            self.status_label.setText(STATUS_FAILED)
            self.status_label.setObjectName("status_error")
            self.status_label.style().polish(self.status_label)
            self.progress_bar.setVisible(False)
            self.detail_label.setVisible(True)
            self.detail_label.setText(item.error_message[:80])
            self.detail_label.setObjectName("status_error")
            self.detail_label.style().polish(self.detail_label)
            self.retry_btn.setVisible(True)
            self.cancel_btn.setVisible(False)

    def _reveal_in_finder(self) -> None:
        """Open the downloaded file's location in Finder."""
        import subprocess

        from src.config.settings import Settings

        settings = Settings()
        download_dir = settings.download_directory
        # Strip the "⬇ " prefix to get the filename
        filename = self.item.display_name.lstrip("⬇ ").strip()
        path = os.path.join(download_dir, filename)

        try:
            if os.path.exists(path):
                subprocess.run(["open", "-R", path], check=False)
            else:
                # File might have been moved — just open the directory
                subprocess.run(["open", download_dir], check=False)
        except Exception:
            pass


class TransferQueueWidget(QWidget):
    """
    Visual transfer queue panel.

    Shows all transfers: pending, in-progress, completed, and failed.
    Updates in real-time as transfers progress.
    """

    retry_transfer = Signal(int)  # index of failed transfer to retry
    cancel_transfer = Signal(int)  # index of pending transfer to cancel

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: List[TransferItem] = []
        self._item_widgets: List[TransferItemWidget] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Transfers")
        self.header_label.setObjectName("section_header")

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("subtle_btn")
        self.clear_btn.setMaximumHeight(22)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_completed)
        self.clear_btn.setVisible(False)

        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.clear_btn)
        layout.addLayout(header_layout)

        # Scroll area for items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(220)

        self.items_container = QWidget()
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(4)
        self.items_layout.addStretch()

        self.scroll_area.setWidget(self.items_container)
        layout.addWidget(self.scroll_area)

        # Empty state
        self.empty_label = QLabel("No transfers")
        self.empty_label.setObjectName("secondary_label")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.scroll_area.setVisible(False)

        # Update timer for speed/ETA
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh_active)
        self._update_timer.setInterval(500)

    def add_transfer(
        self, display_name: str, total_bytes: int = 0, destination: str = ""
    ) -> int:
        """Add a new transfer to the queue. Returns its index."""
        item = TransferItem(
            display_name=display_name,
            total_bytes=total_bytes,
            destination=destination,
        )
        self._items.append(item)
        index = len(self._items) - 1

        widget = TransferItemWidget(index, item)
        widget.retry_requested.connect(self.retry_transfer.emit)
        widget.cancel_requested.connect(self._cancel_item)
        self._item_widgets.append(widget)

        # Insert before the stretch
        self.items_layout.insertWidget(self.items_layout.count() - 1, widget)

        self._update_visibility()
        return index

    def set_in_progress(self, index: int) -> None:
        """Mark a transfer as in-progress and move it to the top of the list."""
        if 0 <= index < len(self._items):
            self._items[index].status = TransferStatus.IN_PROGRESS
            self._items[index].start_time = time.time()
            self._item_widgets[index].update_display()
            self._update_timer.start()

            # Move widget to top of layout
            widget = self._item_widgets[index]
            self.items_layout.removeWidget(widget)
            self.items_layout.insertWidget(0, widget)

    def update_progress(self, index: int, transferred: int, total: int) -> None:
        """Update transfer progress."""
        if 0 <= index < len(self._items):
            self._items[index].transferred_bytes = transferred
            if total > 0:
                self._items[index].total_bytes = total
            # Don't update widget here — timer handles it

    def set_completed(self, index: int) -> None:
        """Mark a transfer as completed."""
        if 0 <= index < len(self._items):
            self._items[index].status = TransferStatus.COMPLETED
            self._items[index].end_time = time.time()
            self._items[index].transferred_bytes = self._items[index].total_bytes
            self._item_widgets[index].update_display()
            self._check_stop_timer()
            self._update_visibility()

    def set_failed(self, index: int, error: str) -> None:
        """Mark a transfer as failed."""
        if 0 <= index < len(self._items):
            self._items[index].status = TransferStatus.FAILED
            self._items[index].end_time = time.time()
            self._items[index].error_message = error
            self._item_widgets[index].update_display()
            self._check_stop_timer()
            self._update_visibility()

    def clear_completed(self) -> None:
        """Remove completed and failed items from the list."""
        indices_to_remove = [
            i
            for i, item in enumerate(self._items)
            if item.status in (TransferStatus.COMPLETED, TransferStatus.FAILED)
        ]
        # Remove in reverse order to preserve indices
        for i in reversed(indices_to_remove):
            self._items.pop(i)
            widget = self._item_widgets.pop(i)
            self.items_layout.removeWidget(widget)
            widget.deleteLater()

        # Re-index remaining widgets
        for i, widget in enumerate(self._item_widgets):
            widget.index = i

        self._update_visibility()

    def _cancel_item(self, index: int) -> None:
        """Cancel a pending transfer and remove it from the queue."""
        if 0 <= index < len(self._items):
            item = self._items[index]
            if item.status != TransferStatus.PENDING:
                return  # Can only cancel pending items

            # Count how many pending items come before this one
            # (this maps to the internal queue index in the controller)
            pending_position = sum(
                1
                for i in range(index)
                if self._items[i].status == TransferStatus.PENDING
            )

            # Remove from visual queue
            self._items.pop(index)
            widget = self._item_widgets.pop(index)
            self.items_layout.removeWidget(widget)
            widget.deleteLater()

            # Re-index remaining widgets
            for i, w in enumerate(self._item_widgets):
                w.index = i

            self._update_visibility()

            # Emit signal with the pending position for the controller
            self.cancel_transfer.emit(pending_position)

    def _refresh_active(self) -> None:
        """Refresh display of active transfers (called by timer)."""
        for i, item in enumerate(self._items):
            if item.status == TransferStatus.IN_PROGRESS:
                self._item_widgets[i].update_display()

    def _check_stop_timer(self) -> None:
        """Stop the update timer if no transfers are in progress."""
        has_active = any(
            item.status == TransferStatus.IN_PROGRESS for item in self._items
        )
        if not has_active:
            self._update_timer.stop()

    def _update_visibility(self) -> None:
        """Show/hide elements based on queue state."""
        has_items = len(self._items) > 0
        self.scroll_area.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

        has_clearable = any(
            item.status in (TransferStatus.COMPLETED, TransferStatus.FAILED)
            for item in self._items
        )
        self.clear_btn.setVisible(has_clearable)

        # Update header count
        active = sum(
            1
            for item in self._items
            if item.status in (TransferStatus.PENDING, TransferStatus.IN_PROGRESS)
        )
        if active > 0:
            self.header_label.setText(f"Transfers ({active} active)")
        else:
            self.header_label.setText("Transfers")


def _format_speed(bytes_per_sec: float) -> str:
    """Format transfer speed."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"


def _format_time(seconds: float) -> str:
    """Format time duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"
