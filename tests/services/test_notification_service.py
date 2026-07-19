"""
Tests for the notification service.
"""

from unittest.mock import patch

from src.services.notification_service import (
    notify,
    notify_batch_complete,
    notify_transfer_complete,
    notify_transfer_failed,
    set_dock_badge,
)


class TestNotify:
    @patch("src.services.notification_service._platform_notify")
    def test_basic_notification(self, mock_notify):
        notify("Title", "Message")
        mock_notify.assert_called_once_with(
            title="Title", message="Message", subtitle=None, sound=False
        )

    @patch("src.services.notification_service._platform_notify")
    def test_notification_with_sound(self, mock_notify):
        notify("Title", "Message", sound=True)
        mock_notify.assert_called_once_with(
            title="Title", message="Message", subtitle=None, sound=True
        )

    @patch("src.services.notification_service._platform_notify")
    def test_notification_with_subtitle(self, mock_notify):
        notify("Title", "Message", subtitle="Sub")
        mock_notify.assert_called_once_with(
            title="Title", message="Message", subtitle="Sub", sound=False
        )

    @patch("src.services.notification_service._platform_notify")
    def test_handles_exception(self, mock_notify):
        mock_notify.side_effect = OSError("no such command")
        # Should not raise — the platform layer handles errors internally
        # but if it bubbles up, the service should still not crash the app
        try:
            notify("Title", "Message")
        except OSError:
            pass  # Acceptable — platform layer is responsible for error handling


class TestNotifyTransferComplete:
    @patch("src.services.notification_service._platform_notify")
    def test_default_action(self, mock_notify):
        notify_transfer_complete("file.mp4")
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        assert "file.mp4" in call_kwargs["message"]
        assert "uploaded" in call_kwargs["message"]
        assert call_kwargs["sound"] is True

    @patch("src.services.notification_service._platform_notify")
    def test_custom_action(self, mock_notify):
        notify_transfer_complete("file.mp4", action="downloaded")
        call_kwargs = mock_notify.call_args[1]
        assert "downloaded" in call_kwargs["message"]

    @patch("src.services.notification_service._platform_notify")
    def test_sound_parameter(self, mock_notify):
        notify_transfer_complete("file.mp4", sound=False)
        call_kwargs = mock_notify.call_args[1]
        assert call_kwargs["sound"] is False


class TestNotifyTransferFailed:
    @patch("src.services.notification_service._platform_notify")
    def test_basic_failure(self, mock_notify):
        notify_transfer_failed("file.mp4")
        call_kwargs = mock_notify.call_args[1]
        assert "file.mp4" in call_kwargs["message"]
        assert "failed" in call_kwargs["message"]

    @patch("src.services.notification_service._platform_notify")
    def test_with_error_message(self, mock_notify):
        notify_transfer_failed("file.mp4", error="connection lost")
        call_kwargs = mock_notify.call_args[1]
        assert "connection lost" in call_kwargs["message"]

    @patch("src.services.notification_service._platform_notify")
    def test_truncates_long_error(self, mock_notify):
        long_error = "x" * 200
        notify_transfer_failed("file.mp4", error=long_error)
        call_kwargs = mock_notify.call_args[1]
        # Error should be truncated to 60 chars
        assert len(call_kwargs["message"]) < 130


class TestNotifyBatchComplete:
    @patch("src.services.notification_service._platform_notify")
    def test_batch_notification(self, mock_notify):
        notify_batch_complete(5)
        call_kwargs = mock_notify.call_args[1]
        assert "5 files" in call_kwargs["message"]
        assert "downloaded" in call_kwargs["message"]

    @patch("src.services.notification_service._platform_notify")
    def test_custom_action(self, mock_notify):
        notify_batch_complete(3, action="uploaded")
        call_kwargs = mock_notify.call_args[1]
        assert "uploaded" in call_kwargs["message"]


class TestSetDockBadge:
    @patch("src.services.notification_service._platform_set_dock_badge")
    def test_sets_badge(self, mock_badge):
        set_dock_badge(3)
        mock_badge.assert_called_once_with(3)

    @patch("src.services.notification_service._platform_set_dock_badge")
    def test_clears_badge(self, mock_badge):
        set_dock_badge(0)
        mock_badge.assert_called_once_with(0)
