"""
Unit tests for BookmarksBar — edit, remove, and default bookmark logic.

The context menu itself is user-driven, so these tests exercise the underlying
mutation methods (_edit_bookmark, _remove_bookmark, toggle_default) against a
fake in-memory settings object rather than driving the Qt menu.
"""

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from src.widgets.bookmarks_bar import BookmarksBar


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeSettings:
    """Minimal in-memory stand-in for the Settings bookmark API."""

    def __init__(self, bookmarks=None, default=""):
        self._bookmarks = list(bookmarks or [])
        self._default = default

    def get_bookmarks(self):
        return list(self._bookmarks)

    def set_bookmarks(self, bookmarks):
        self._bookmarks = list(bookmarks)

    def get_default_bookmark(self):
        return self._default

    def set_default_bookmark(self, bookmark):
        self._default = bookmark


@pytest.fixture
def bar(qapp):
    settings = FakeSettings(
        bookmarks=["/mnt/movies", "/mnt/tv", "/mnt/music"],
        default="/mnt/tv",
    )
    widget = BookmarksBar(settings)
    return widget, settings


class TestRemoveBookmark:
    def test_removes_path(self, bar):
        widget, settings = bar
        widget._remove_bookmark("/mnt/movies")
        assert "/mnt/movies" not in settings.get_bookmarks()
        assert settings.get_bookmarks() == ["/mnt/tv", "/mnt/music"]

    def test_removing_default_clears_default(self, bar):
        widget, settings = bar
        widget._remove_bookmark("/mnt/tv")
        assert "/mnt/tv" not in settings.get_bookmarks()
        assert settings.get_default_bookmark() == ""


class TestEditBookmark:
    def test_edit_replaces_in_place_preserving_order(self, bar):
        widget, settings = bar
        with patch(
            "src.widgets.bookmarks_bar.QInputDialog.getText",
            return_value=("/mnt/films", True),
        ):
            widget._edit_bookmark("/mnt/movies")
        # Order preserved, path replaced
        assert settings.get_bookmarks() == ["/mnt/films", "/mnt/tv", "/mnt/music"]

    def test_edit_moves_default_pointer(self, bar):
        widget, settings = bar
        with patch(
            "src.widgets.bookmarks_bar.QInputDialog.getText",
            return_value=("/mnt/shows", True),
        ):
            widget._edit_bookmark("/mnt/tv")
        assert settings.get_default_bookmark() == "/mnt/shows"
        assert "/mnt/shows" in settings.get_bookmarks()
        assert "/mnt/tv" not in settings.get_bookmarks()

    def test_edit_cancelled_is_noop(self, bar):
        widget, settings = bar
        before = settings.get_bookmarks()
        with patch(
            "src.widgets.bookmarks_bar.QInputDialog.getText",
            return_value=("/mnt/whatever", False),
        ):
            widget._edit_bookmark("/mnt/movies")
        assert settings.get_bookmarks() == before

    def test_edit_empty_is_noop(self, bar):
        widget, settings = bar
        before = settings.get_bookmarks()
        with patch(
            "src.widgets.bookmarks_bar.QInputDialog.getText",
            return_value=("   ", True),
        ):
            widget._edit_bookmark("/mnt/movies")
        assert settings.get_bookmarks() == before

    def test_edit_to_existing_path_is_rejected(self, bar):
        widget, settings = bar
        before = settings.get_bookmarks()
        with patch(
            "src.widgets.bookmarks_bar.QInputDialog.getText",
            return_value=("/mnt/music", True),
        ), patch("src.widgets.bookmarks_bar.QMessageBox.information"):
            widget._edit_bookmark("/mnt/movies")
        # Unchanged — duplicate rejected
        assert settings.get_bookmarks() == before


class TestToggleDefault:
    def test_set_default(self, bar):
        widget, settings = bar
        widget.toggle_default("/mnt/movies")
        assert settings.get_default_bookmark() == "/mnt/movies"

    def test_clear_default(self, bar):
        widget, settings = bar
        widget.toggle_default("/mnt/tv")  # currently default
        assert settings.get_default_bookmark() == ""
