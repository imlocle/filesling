"""
Unit tests for DownloadController.

Tests download slot management, cleanup, and interface logic.
Since DownloadController inherits QObject, we test with a real QApplication.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from src.controllers.download_controller import (
    DownloadController,
    _DownloadSlot,
)
from src.utils.constants import MAX_PARALLEL_DOWNLOADS as MAX_PARALLEL

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for QObject-based tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_view(qapp):
    """Create a mock MainWindow (must be a real QWidget for QObject parenting)."""
    widget = QWidget()
    widget.remote_explorer = MagicMock()
    widget.remote_explorer.sftp = MagicMock()
    widget.transfer_queue = MagicMock()
    widget.transfer_queue.add_transfer.return_value = 0
    widget.transfer_queue._items = []
    return widget


@pytest.fixture
def mock_settings():
    """Create a mock Settings."""
    settings = MagicMock()
    settings.download_directory = "/tmp/downloads"
    settings.config.current_server_id = "test-server"
    settings.config.notify_on_transfer_complete = False
    settings.config.notify_sound = False
    settings.config.reveal_in_finder_after_download = False
    settings.get_server.return_value = {
        "download_directory": "/tmp/downloads",
        "connection_type": "ssh",
    }
    return settings


@pytest.fixture
def mock_connection_manager():
    """Create a mock ConnectionManagerService."""
    cm = MagicMock()
    cm.open_sftp_session.return_value = MagicMock()
    return cm


@pytest.fixture
def mock_transfer_controller():
    """Create a mock ManualTransferController."""
    tc = MagicMock()
    tc.get_transfer_method.return_value = "sftp"
    tc.is_busy.return_value = False
    tc.queue_size.return_value = 0
    tc.history = MagicMock()
    return tc


@pytest.fixture
def controller(
    mock_view, mock_settings, mock_connection_manager, mock_transfer_controller
):
    """Create a DownloadController with mocked dependencies."""
    return DownloadController(
        view=mock_view,
        settings=mock_settings,
        connection_manager=mock_connection_manager,
        transfer_controller=mock_transfer_controller,
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestDownloadControllerProperties:
    def test_is_active_empty(self, controller):
        assert controller.is_active is False

    def test_is_active_with_slot(self, controller):
        controller._active.append(_DownloadSlot())
        assert controller.is_active is True

    def test_active_count(self, controller):
        assert controller.active_count == 0
        controller._active.append(_DownloadSlot())
        controller._active.append(_DownloadSlot())
        assert controller.active_count == 2


# ---------------------------------------------------------------------------
# Download slot management
# ---------------------------------------------------------------------------


class TestDownloadSlotManagement:
    def test_max_parallel_constant(self):
        """MAX_PARALLEL should be 3."""
        assert MAX_PARALLEL == 3

    def test_process_pending_starts_next(self, controller):
        """When a slot frees up, pending downloads should start."""
        controller._pending.append((["/remote/queued.mp4"], "/local", 1024, 1))

        with patch.object(controller, "_start_download") as mock_start:
            controller._process_pending()
            mock_start.assert_called_once_with(
                ["/remote/queued.mp4"], "/local", 1024, 1
            )

    def test_process_pending_respects_max_parallel(self, controller):
        """Should not start more than MAX_PARALLEL concurrent downloads."""
        for _ in range(MAX_PARALLEL):
            controller._active.append(_DownloadSlot())

        controller._pending.append((["/remote/a.mp4"], "/local", 100, 0))

        with patch.object(controller, "_start_download") as mock_start:
            controller._process_pending()
            mock_start.assert_not_called()

    def test_process_pending_starts_multiple(self, controller):
        """Should start multiple pending downloads up to MAX_PARALLEL."""
        controller._pending.append((["/remote/a.mp4"], "/local", 100, 0))
        controller._pending.append((["/remote/b.mp4"], "/local", 200, 1))
        controller._pending.append((["/remote/c.mp4"], "/local", 300, 2))

        with patch.object(controller, "_start_download"):
            controller._process_pending()

        assert len(controller._pending) == 0


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestDownloadSlotCleanup:
    def test_cleanup_closes_sftp_session(self, controller):
        """Cleanup should close the SFTP session."""
        sftp_session = MagicMock()
        slot = _DownloadSlot(sftp_session=sftp_session)
        controller._active.append(slot)

        controller._cleanup_slot(slot, remove=True)

        sftp_session.close.assert_called_once()
        assert slot not in controller._active

    def test_cleanup_waits_on_running_thread(self, controller):
        """Cleanup should wait for thread to finish before deleting."""
        thread = MagicMock()
        thread.isRunning.return_value = True
        slot = _DownloadSlot(thread=thread)
        controller._active.append(slot)

        controller._cleanup_slot(slot, remove=True)

        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(2000)
        thread.deleteLater.assert_called_once()

    def test_cleanup_handles_already_stopped_thread(self, controller):
        """Cleanup should handle threads that already stopped."""
        thread = MagicMock()
        thread.isRunning.return_value = False
        slot = _DownloadSlot(thread=thread)
        controller._active.append(slot)

        controller._cleanup_slot(slot, remove=True)

        thread.quit.assert_not_called()
        thread.deleteLater.assert_called_once()

    def test_cleanup_removes_from_active_list(self, controller):
        """Cleanup with remove=True should remove slot from active list."""
        slot = _DownloadSlot()
        controller._active.append(slot)
        assert len(controller._active) == 1

        controller._cleanup_slot(slot, remove=True)
        assert len(controller._active) == 0

    def test_cleanup_without_remove(self, controller):
        """Cleanup with remove=False should NOT remove slot from active list."""
        slot = _DownloadSlot()
        controller._active.append(slot)

        controller._cleanup_slot(slot, remove=False)
        assert len(controller._active) == 1

    def test_cleanup_handles_none_sftp(self, controller):
        """Cleanup should handle slot with no SFTP session."""
        slot = _DownloadSlot(sftp_session=None)
        controller._active.append(slot)
        # Should not raise
        controller._cleanup_slot(slot, remove=True)

    def test_cleanup_handles_sftp_close_error(self, controller):
        """Cleanup should handle SFTP close errors gracefully."""
        sftp_session = MagicMock()
        sftp_session.close.side_effect = Exception("already closed")
        slot = _DownloadSlot(sftp_session=sftp_session)
        controller._active.append(slot)

        # Should not raise
        controller._cleanup_slot(slot, remove=True)


# ---------------------------------------------------------------------------
# Download interface
# ---------------------------------------------------------------------------


class TestDownloadInterface:
    def test_download_item_calls_download_paths(self, controller):
        """download_item should delegate to _download_paths."""
        with patch.object(controller, "_download_paths") as mock:
            controller.download_item("/remote/file.mp4")
            mock.assert_called_once_with(["/remote/file.mp4"])

    def test_download_items_calls_download_paths(self, controller):
        """download_items should delegate to _download_paths."""
        paths = ["/remote/a.mp4", "/remote/b.mp4"]
        with patch.object(controller, "_download_paths") as mock:
            controller.download_items(paths)
            mock.assert_called_once_with(paths)

    def test_download_items_empty(self, controller):
        """Empty list should be a no-op."""
        with patch.object(controller, "_download_paths") as mock:
            controller.download_items([])
            mock.assert_not_called()


# ---------------------------------------------------------------------------
# _DownloadSlot dataclass
# ---------------------------------------------------------------------------


class TestDownloadSlot:
    def test_default_values(self):
        slot = _DownloadSlot()
        assert slot.thread is None
        assert slot.worker is None
        assert slot.sftp_session is None
        assert slot.queue_index == -1
        assert slot.attempts == 0
        assert slot.error_msg is None
        assert slot.remote_paths == []
        assert slot.local_dir == ""
        assert slot.total_bytes == 0

    def test_custom_values(self):
        slot = _DownloadSlot(
            queue_index=5,
            remote_paths=["/remote/a.mp4"],
            local_dir="/downloads",
            total_bytes=1024 * 1024,
        )
        assert slot.queue_index == 5
        assert slot.remote_paths == ["/remote/a.mp4"]
        assert slot.local_dir == "/downloads"
        assert slot.total_bytes == 1024 * 1024
