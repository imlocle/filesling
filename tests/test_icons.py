"""
Tests for the file icon generation utility.

Note: These tests require a QApplication instance (Qt GUI).
They are skipped if no display is available.
"""

import os
import sys

import pytest

# Skip all tests in this module if no display is available
pytestmark = pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and sys.platform != "darwin",
    reason="No display available for Qt tests",
)


@pytest.fixture(scope="module")
def qapp():
    """Create a QApplication for the test module."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestGetFileIcon:
    def test_directory_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=True)
        assert not icon.isNull()

    def test_video_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="movie.mp4")
        assert not icon.isNull()

    def test_audio_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="song.flac")
        assert not icon.isNull()

    def test_image_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="photo.jpg")
        assert not icon.isNull()

    def test_archive_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="backup.zip")
        assert not icon.isNull()

    def test_code_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="main.py")
        assert not icon.isNull()

    def test_document_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="readme.pdf")
        assert not icon.isNull()

    def test_subtitle_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="movie.srt")
        assert not icon.isNull()

    def test_executable_file_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="app.dmg")
        assert not icon.isNull()

    def test_unknown_extension_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="data.xyz")
        assert not icon.isNull()

    def test_no_filename_icon(self, qapp):
        from src.utils.icons import get_file_icon

        icon = get_file_icon(is_dir=False, filename="")
        assert not icon.isNull()

    def test_case_insensitive_extension(self, qapp):
        from src.utils.icons import get_file_icon

        icon_lower = get_file_icon(is_dir=False, filename="video.mp4")
        icon_upper = get_file_icon(is_dir=False, filename="VIDEO.MP4")
        # Both should produce valid icons (same color)
        assert not icon_lower.isNull()
        assert not icon_upper.isNull()
