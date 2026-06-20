"""
Tests for the notification service.
"""

from unittest.mock import patch

from src.services.notification_service import (
    _escape,
    notify,
    notify_batch_complete,
    notify_transfer_complete,
    notify_transfer_failed,
    set_dock_badge,
)


class TestEscape:
    def test_plain_text(self):
        assert _escape("hello world") == "hello world"

    def test_escapes_quotes(self):
        assert _escape('say "hi"') == 'say \\"hi\\"'

    def test_escapes_backslashes(self):
        assert _escape("path\\to\\file") == "path\\\\to\\\\file"

    def test_escapes_both(self):
        result = _escape('a "b" c\\d')
        assert '\\"' in result
        assert "\\\\" in result

    def test_empty_string(self):
        assert _escape("") == ""


class TestNotify:
    @patch("src.services.notification_service.subprocess.run")
    def test_basic_notification(self, mock_run):
        notify("Title", "Message")
        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[0] == "osascript"
        assert cmd[1] == "-e"
        assert "Title" in cmd[2]
        assert "Message" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_notification_with_sound(self, mock_run):
        notify("Title", "Message", sound=True)
        cmd = mock_run.call_args[0][0]
        assert 'sound name "default"' in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_notification_without_sound(self, mock_run):
        notify("Title", "Message", sound=False)
        cmd = mock_run.call_args[0][0]
        assert "sound" not in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_notification_with_subtitle(self, mock_run):
        notify("Title", "Message", subtitle="Sub")
        cmd = mock_run.call_args[0][0]
        assert "Sub" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_handles_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=5)
        # Should not raise
        notify("Title", "Message")

    @patch("src.services.notification_service.subprocess.run")
    def test_handles_exception(self, mock_run):
        mock_run.side_effect = OSError("no such command")
        # Should not raise
        notify("Title", "Message")


class TestNotifyTransferComplete:
    @patch("src.services.notification_service.subprocess.run")
    def test_default_action(self, mock_run):
        notify_transfer_complete("file.mp4")
        cmd = mock_run.call_args[0][0]
        assert "file.mp4" in cmd[2]
        assert "uploaded" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_custom_action(self, mock_run):
        notify_transfer_complete("file.mp4", action="downloaded")
        cmd = mock_run.call_args[0][0]
        assert "downloaded" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_sound_parameter(self, mock_run):
        notify_transfer_complete("file.mp4", sound=False)
        cmd = mock_run.call_args[0][0]
        assert "sound" not in cmd[2]


class TestNotifyTransferFailed:
    @patch("src.services.notification_service.subprocess.run")
    def test_basic_failure(self, mock_run):
        notify_transfer_failed("file.mp4")
        cmd = mock_run.call_args[0][0]
        assert "file.mp4" in cmd[2]
        assert "failed" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_with_error_message(self, mock_run):
        notify_transfer_failed("file.mp4", error="connection lost")
        cmd = mock_run.call_args[0][0]
        assert "connection lost" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_truncates_long_error(self, mock_run):
        long_error = "x" * 200
        notify_transfer_failed("file.mp4", error=long_error)
        cmd = mock_run.call_args[0][0]
        # Error should be truncated to 60 chars
        assert len(cmd[2]) < 300


class TestNotifyBatchComplete:
    @patch("src.services.notification_service.subprocess.run")
    def test_batch_notification(self, mock_run):
        notify_batch_complete(5)
        cmd = mock_run.call_args[0][0]
        assert "5 files" in cmd[2]
        assert "downloaded" in cmd[2]

    @patch("src.services.notification_service.subprocess.run")
    def test_custom_action(self, mock_run):
        notify_batch_complete(3, action="uploaded")
        cmd = mock_run.call_args[0][0]
        assert "uploaded" in cmd[2]


class TestSetDockBadge:
    @patch("src.services.notification_service._set_badge_via_qt")
    def test_sets_badge(self, mock_badge):
        set_dock_badge(3)
        mock_badge.assert_called_once_with(3)

    @patch("src.services.notification_service._set_badge_via_qt")
    def test_clears_badge(self, mock_badge):
        set_dock_badge(0)
        mock_badge.assert_called_once_with(0)

    @patch("src.services.notification_service._set_badge_via_qt")
    def test_handles_exception(self, mock_badge):
        mock_badge.side_effect = RuntimeError("no app")
        # Should not raise
        set_dock_badge(1)
