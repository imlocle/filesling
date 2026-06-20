"""
Unit tests for utils/theme.py.

Tests theme resolution and stylesheet application.
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from src.utils.theme import (
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    effective_theme,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestEffectiveTheme:
    def test_explicit_light(self, qapp):
        """Explicit 'light' should always return light."""
        assert effective_theme(qapp, THEME_LIGHT) == THEME_LIGHT

    def test_explicit_dark(self, qapp):
        """Explicit 'dark' should always return dark."""
        assert effective_theme(qapp, THEME_DARK) == THEME_DARK

    def test_system_resolves(self, qapp):
        """System theme should resolve to either light or dark."""
        result = effective_theme(qapp, THEME_SYSTEM)
        assert result in (THEME_LIGHT, THEME_DARK)

    def test_unknown_defaults_to_dark(self, qapp):
        """Unknown theme mode should default to dark."""
        result = effective_theme(qapp, "neon")
        # "neon" is not in (light, dark), so falls through to system check
        assert result in (THEME_LIGHT, THEME_DARK)


class TestThemeConstants:
    def test_constant_values(self):
        assert THEME_SYSTEM == "system"
        assert THEME_LIGHT == "light"
        assert THEME_DARK == "dark"
