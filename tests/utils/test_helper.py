"""
Unit tests for utils/helper.py.

Tests path resolution for development and PyInstaller environments.
"""

import sys
from pathlib import Path
from unittest.mock import patch

from src.utils.helper import get_path


class TestGetPath:
    def test_development_mode(self):
        """In development, should resolve relative to main.py directory."""
        result = get_path("assets/styles/modern_theme.qss")
        assert isinstance(result, Path)
        assert "assets" in str(result)
        assert "modern_theme.qss" in str(result)

    def test_pyinstaller_mode(self):
        """With sys._MEIPASS set, should resolve relative to MEIPASS."""
        with patch.object(sys, "_MEIPASS", "/tmp/pyinstaller_bundle", create=True):
            result = get_path("assets/icons/logo.png")
            assert str(result) == "/tmp/pyinstaller_bundle/assets/icons/logo.png"

    def test_relative_path(self):
        """Should handle simple relative paths."""
        result = get_path("README.md")
        assert isinstance(result, Path)
        assert "README.md" in str(result)

    def test_nested_path(self):
        """Should handle deeply nested paths."""
        result = get_path("src/config/settings.py")
        assert "src" in str(result)
        assert "settings.py" in str(result)
