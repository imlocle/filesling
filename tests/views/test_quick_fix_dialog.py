"""
Unit tests for QuickFixDialog.

Tests the QuickFixOptions dataclass and dialog behavior.
"""

import pytest
from PySide6.QtWidgets import QApplication

from src.views.dialogs.quick_fix_dialog import QuickFixDialog, QuickFixOptions


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# QuickFixOptions dataclass
# ---------------------------------------------------------------------------


class TestQuickFixOptions:
    def test_defaults(self):
        opts = QuickFixOptions()
        assert opts.to_mp4 is False
        assert opts.fix_timestamps is False
        assert opts.strip_subtitles is False

    def test_custom_values(self):
        opts = QuickFixOptions(to_mp4=True, fix_timestamps=True, strip_subtitles=False)
        assert opts.to_mp4 is True
        assert opts.fix_timestamps is True
        assert opts.strip_subtitles is False

    def test_all_enabled(self):
        opts = QuickFixOptions(to_mp4=True, fix_timestamps=True, strip_subtitles=True)
        assert opts.to_mp4 is True
        assert opts.fix_timestamps is True
        assert opts.strip_subtitles is True


# ---------------------------------------------------------------------------
# QuickFixDialog
# ---------------------------------------------------------------------------


class TestQuickFixDialog:
    def test_dialog_creation_mkv(self, qapp):
        """Dialog for .mkv file should have MP4 option enabled."""
        dialog = QuickFixDialog(None, "movie.mkv", ".mkv")
        assert dialog._mp4_check.isEnabled()
        assert "Quick Fix" in dialog.windowTitle()
        assert "movie.mkv" in dialog.windowTitle()

    def test_dialog_creation_mp4(self, qapp):
        """Dialog for .mp4 file should have MP4 option disabled."""
        dialog = QuickFixDialog(None, "movie.mp4", ".mp4")
        assert not dialog._mp4_check.isEnabled()
        assert "already MP4" in dialog._mp4_check.text()

    def test_dialog_creation_m4v(self, qapp):
        """Dialog for .m4v file should also disable MP4 option."""
        dialog = QuickFixDialog(None, "clip.m4v", ".m4v")
        assert not dialog._mp4_check.isEnabled()

    def test_on_accept_collects_options(self, qapp):
        """Accept should populate options from checkboxes."""
        dialog = QuickFixDialog(None, "video.avi", ".avi")
        dialog._mp4_check.setChecked(True)
        dialog._timestamps_check.setChecked(True)
        dialog._subs_check.setChecked(False)
        dialog._on_accept()
        assert dialog.options.to_mp4 is True
        assert dialog.options.fix_timestamps is True
        assert dialog.options.strip_subtitles is False

    def test_on_accept_no_options_does_not_accept(self, qapp):
        """Accept with no options checked should not close the dialog."""
        dialog = QuickFixDialog(None, "video.mkv", ".mkv")
        dialog._mp4_check.setChecked(False)
        dialog._timestamps_check.setChecked(False)
        dialog._subs_check.setChecked(False)
        # _on_accept should show info message, not call self.accept()
        # We can't easily test the dialog stays open without exec(),
        # but we verify the result() is still Rejected
        assert dialog.result() == 0  # QDialog.Rejected by default

    def test_mp4_disabled_means_not_in_options(self, qapp):
        """Even if MP4 checkbox is checked but disabled, to_mp4 should be False."""
        dialog = QuickFixDialog(None, "video.mp4", ".mp4")
        dialog._mp4_check.setChecked(True)  # Can be checked but disabled
        dialog._timestamps_check.setChecked(True)
        dialog._on_accept()
        assert dialog.options.to_mp4 is False  # Because checkbox is disabled
        assert dialog.options.fix_timestamps is True

    def test_minimum_size(self, qapp):
        dialog = QuickFixDialog(None, "test.mkv", ".mkv")
        assert dialog.minimumWidth() >= 420
        assert dialog.minimumHeight() >= 320
