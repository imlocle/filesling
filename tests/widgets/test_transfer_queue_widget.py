"""
Unit tests for TransferQueueWidget.

Tests the TransferItem model and queue logic.
"""

import time

import pytest
from PySide6.QtWidgets import QApplication

from src.widgets.transfer_queue_widget import (
    TransferItem,
    TransferQueueWidget,
    TransferStatus,
    _format_speed,
    _format_time,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# TransferItem dataclass
# ---------------------------------------------------------------------------


class TestTransferItem:
    def test_defaults(self):
        item = TransferItem(display_name="test.mp4")
        assert item.display_name == "test.mp4"
        assert item.total_bytes == 0
        assert item.transferred_bytes == 0
        assert item.status == TransferStatus.PENDING
        assert item.error_message == ""
        assert item.start_time == 0.0
        assert item.end_time == 0.0

    def test_progress_percent_zero_total(self):
        item = TransferItem(display_name="x", total_bytes=0)
        assert item.progress_percent == 0

    def test_progress_percent_normal(self):
        item = TransferItem(display_name="x", total_bytes=1000, transferred_bytes=500)
        assert item.progress_percent == 50

    def test_progress_percent_capped_at_100(self):
        item = TransferItem(display_name="x", total_bytes=100, transferred_bytes=200)
        assert item.progress_percent == 100

    def test_speed_no_start_time(self):
        item = TransferItem(display_name="x", transferred_bytes=1000, start_time=0.0)
        assert item.speed_bytes_per_sec == 0.0

    def test_speed_calculation(self):
        now = time.time()
        item = TransferItem(
            display_name="x",
            transferred_bytes=10000,
            start_time=now - 10,  # 10 seconds ago
            end_time=now,
        )
        speed = item.speed_bytes_per_sec
        assert 900 < speed < 1100  # ~1000 B/s

    def test_eta_no_speed(self):
        item = TransferItem(display_name="x", total_bytes=1000, transferred_bytes=0)
        assert item.eta_seconds is None

    def test_eta_calculation(self):
        now = time.time()
        item = TransferItem(
            display_name="x",
            total_bytes=10000,
            transferred_bytes=5000,
            start_time=now - 10,
            end_time=now,
        )
        # Speed = 5000/10 = 500 B/s, remaining = 5000, ETA = 10s
        eta = item.eta_seconds
        assert eta is not None
        assert 9 < eta < 11

    def test_eta_no_total(self):
        item = TransferItem(display_name="x", total_bytes=0, transferred_bytes=100)
        assert item.eta_seconds is None


# ---------------------------------------------------------------------------
# TransferStatus enum
# ---------------------------------------------------------------------------


class TestTransferStatus:
    def test_values(self):
        assert TransferStatus.PENDING.value == "pending"
        assert TransferStatus.IN_PROGRESS.value == "in_progress"
        assert TransferStatus.COMPLETED.value == "completed"
        assert TransferStatus.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


class TestFormatSpeed:
    def test_bytes(self):
        assert _format_speed(500) == "500 B/s"

    def test_kilobytes(self):
        result = _format_speed(5000)
        assert "KB/s" in result
        assert "5.0" in result

    def test_megabytes(self):
        result = _format_speed(5_000_000)
        assert "MB/s" in result
        assert "5.0" in result

    def test_zero(self):
        assert _format_speed(0) == "0 B/s"


class TestFormatTime:
    def test_seconds(self):
        assert _format_time(45) == "45s"

    def test_minutes(self):
        assert _format_time(125) == "2m 5s"

    def test_hours(self):
        assert _format_time(3661) == "1h 1m"

    def test_zero(self):
        assert _format_time(0) == "0s"

    def test_just_under_minute(self):
        assert _format_time(59) == "59s"

    def test_exactly_one_hour(self):
        assert _format_time(3600) == "1h 0m"


# ---------------------------------------------------------------------------
# TransferQueueWidget
# ---------------------------------------------------------------------------


class TestTransferQueueWidget:
    def test_add_transfer(self, qapp):
        widget = TransferQueueWidget()
        idx = widget.add_transfer("⬆ video.mp4", 1024, "/remote/path", "sftp")
        assert idx == 0
        assert len(widget._items) == 1
        assert widget._items[0].display_name == "⬆ video.mp4"
        assert widget._items[0].total_bytes == 1024
        assert widget._items[0].destination == "/remote/path"
        assert widget._items[0].transfer_method == "sftp"

    def test_add_multiple_transfers(self, qapp):
        widget = TransferQueueWidget()
        idx1 = widget.add_transfer("a.mp4", 100)
        idx2 = widget.add_transfer("b.mp4", 200)
        idx3 = widget.add_transfer("c.mp4", 300)
        assert idx1 == 0
        assert idx2 == 1
        assert idx3 == 2
        assert len(widget._items) == 3

    def test_set_in_progress(self, qapp):
        widget = TransferQueueWidget()
        widget.add_transfer("test.mp4", 1024)
        widget.set_in_progress(0)
        assert widget._items[0].status == TransferStatus.IN_PROGRESS
        assert widget._items[0].start_time > 0

    def test_set_completed(self, qapp):
        widget = TransferQueueWidget()
        widget.add_transfer("test.mp4", 1024)
        widget.set_in_progress(0)
        widget.set_completed(0)
        assert widget._items[0].status == TransferStatus.COMPLETED
        assert widget._items[0].end_time > 0
        assert widget._items[0].transferred_bytes == widget._items[0].total_bytes

    def test_set_failed(self, qapp):
        widget = TransferQueueWidget()
        widget.add_transfer("test.mp4", 1024)
        widget.set_in_progress(0)
        widget.set_failed(0, "Connection lost")
        assert widget._items[0].status == TransferStatus.FAILED
        assert widget._items[0].error_message == "Connection lost"
        assert widget._items[0].end_time > 0

    def test_update_progress(self, qapp):
        widget = TransferQueueWidget()
        widget.add_transfer("test.mp4", 1024)
        widget.update_progress(0, 512, 1024)
        assert widget._items[0].transferred_bytes == 512

    def test_clear_completed(self, qapp):
        widget = TransferQueueWidget()
        widget.add_transfer("done.mp4", 100)
        widget.add_transfer("active.mp4", 200)
        widget.add_transfer("failed.mp4", 300)

        widget.set_completed(0)
        widget.set_in_progress(1)
        widget.set_failed(2, "error")

        widget.clear_completed()

        # Only the in-progress item should remain
        assert len(widget._items) == 1
        assert widget._items[0].display_name == "active.mp4"

    def test_invalid_index_ignored(self, qapp):
        widget = TransferQueueWidget()
        # These should not raise
        widget.set_in_progress(99)
        widget.set_completed(-1)
        widget.set_failed(5, "error")
        widget.update_progress(10, 100, 200)
