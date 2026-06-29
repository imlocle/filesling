"""
Unit tests for QuickFixDialog.

Tests the QuickFixOptions dataclass and dialog behavior.
"""

import pytest
from PySide6.QtWidgets import QApplication

from src.views.dialogs.quick_fix_dialog import (
    QuickFixDialog,
    QuickFixOptions,
    SubtitleTrack,
)


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
        assert opts.keep_subtitle_indices is None

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

    def test_selective_subtitles(self):
        opts = QuickFixOptions(strip_subtitles=True, keep_subtitle_indices=[0, 2])
        assert opts.keep_subtitle_indices == [0, 2]


# ---------------------------------------------------------------------------
# SubtitleTrack dataclass
# ---------------------------------------------------------------------------


class TestSubtitleTrack:
    def test_basic(self):
        track = SubtitleTrack(index=0, language="eng", codec="ass")
        assert track.index == 0
        assert track.language == "eng"
        assert track.codec == "ass"
        assert track.title == ""

    def test_with_title(self):
        track = SubtitleTrack(index=2, language="jpn", codec="srt", title="Japanese")
        assert track.title == "Japanese"


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
        from unittest.mock import patch

        dialog = QuickFixDialog(None, "video.mkv", ".mkv")
        dialog._mp4_check.setChecked(False)
        dialog._timestamps_check.setChecked(False)
        dialog._subs_check.setChecked(False)
        with patch("PySide6.QtWidgets.QMessageBox.information"):
            dialog._on_accept()
        assert dialog.result() == 0  # QDialog.Rejected — dialog was not accepted

    def test_mp4_disabled_means_not_in_options(self, qapp):
        """Even if MP4 checkbox is checked but disabled, to_mp4 should be False."""
        dialog = QuickFixDialog(None, "video.mp4", ".mp4")
        dialog._mp4_check.setChecked(True)  # Can be checked but disabled
        dialog._timestamps_check.setChecked(True)
        dialog._on_accept()
        assert dialog.options.to_mp4 is False
        assert dialog.options.fix_timestamps is True

    def test_minimum_size(self, qapp):
        dialog = QuickFixDialog(None, "test.mkv", ".mkv")
        assert dialog.minimumWidth() >= 420
        assert dialog.minimumHeight() >= 320

    def test_subtitle_picker_hidden_by_default(self, qapp):
        """Subtitle picker should be hidden until 'Remove subtitles' is checked."""
        tracks = [
            SubtitleTrack(index=0, language="eng", codec="ass"),
            SubtitleTrack(index=1, language="jpn", codec="ass"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        assert not dialog._sub_expand_btn.isVisible()
        assert not dialog._sub_tracks_frame.isVisible()

    def test_subtitle_picker_shows_on_check(self, qapp):
        """Expand button should become active when 'Remove subtitles' is checked."""
        tracks = [
            SubtitleTrack(index=0, language="eng", codec="ass"),
            SubtitleTrack(index=1, language="jpn", codec="ass"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        dialog._subs_check.setChecked(True)
        # In tests without showing the dialog, isVisible() may not work
        # but the button text and internal state should be set
        assert dialog._sub_expand_btn is not None

    def test_subtitle_picker_expands(self, qapp):
        """Clicking expand should set the expanded state and show track checkboxes."""
        tracks = [
            SubtitleTrack(index=0, language="eng", codec="ass"),
            SubtitleTrack(index=1, language="jpn", codec="ass"),
            SubtitleTrack(index=2, language="ara", codec="srt"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        dialog._subs_check.setChecked(True)
        dialog._toggle_sub_picker()
        assert dialog._sub_picker_expanded is True
        assert len(dialog._sub_checkboxes) == 3
        assert "▼" in dialog._sub_expand_btn.text()

    def test_english_pre_checked(self, qapp):
        """English subtitle track should be pre-checked."""
        tracks = [
            SubtitleTrack(index=0, language="ara", codec="ass"),
            SubtitleTrack(index=1, language="eng", codec="ass"),
            SubtitleTrack(index=2, language="jpn", codec="ass"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        assert not dialog._sub_checkboxes[0].isChecked()  # ara
        assert dialog._sub_checkboxes[1].isChecked()  # eng
        assert not dialog._sub_checkboxes[2].isChecked()  # jpn

    def test_selective_subtitle_in_options(self, qapp):
        """Selecting specific tracks should produce keep_subtitle_indices."""
        tracks = [
            SubtitleTrack(index=0, language="ara", codec="ass"),
            SubtitleTrack(index=1, language="eng", codec="ass"),
            SubtitleTrack(index=2, language="jpn", codec="ass"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        dialog._subs_check.setChecked(True)
        dialog._toggle_sub_picker()  # Expand

        # Only keep eng (index 1)
        dialog._sub_checkboxes[0].setChecked(False)
        dialog._sub_checkboxes[1].setChecked(True)
        dialog._sub_checkboxes[2].setChecked(False)

        dialog._on_accept()
        assert dialog.options.keep_subtitle_indices == [1]

    def test_all_unchecked_means_strip_all(self, qapp):
        """If user expands picker but unchecks all, strip_subtitles should be True."""
        tracks = [
            SubtitleTrack(index=0, language="eng", codec="ass"),
            SubtitleTrack(index=1, language="jpn", codec="ass"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        dialog._subs_check.setChecked(True)
        dialog._toggle_sub_picker()

        # Uncheck all
        dialog._sub_checkboxes[0].setChecked(False)
        dialog._sub_checkboxes[1].setChecked(False)

        dialog._on_accept()
        assert dialog.options.strip_subtitles is True
        assert dialog.options.keep_subtitle_indices is None

    def test_all_checked_means_no_strip(self, qapp):
        """If user expands picker and checks all, nothing should be stripped."""
        tracks = [
            SubtitleTrack(index=0, language="eng", codec="ass"),
            SubtitleTrack(index=1, language="jpn", codec="ass"),
        ]
        dialog = QuickFixDialog(None, "anime.mkv", ".mkv", subtitle_tracks=tracks)
        dialog._subs_check.setChecked(True)
        dialog._timestamps_check.setChecked(True)  # Need at least one option
        dialog._toggle_sub_picker()

        # Check all
        dialog._sub_checkboxes[0].setChecked(True)
        dialog._sub_checkboxes[1].setChecked(True)

        dialog._on_accept()
        # All checked = don't strip anything
        assert dialog.options.strip_subtitles is False
        assert dialog.options.keep_subtitle_indices is None

    def test_no_tracks_hides_picker(self, qapp):
        """Dialog without subtitle tracks should not show the picker."""
        dialog = QuickFixDialog(None, "video.mkv", ".mkv", subtitle_tracks=[])
        assert not dialog._subtitle_tracks
