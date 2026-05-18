from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.utils.helper import get_path

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"


def effective_theme(app: QApplication, theme_mode: str) -> str:
    """Resolve system/light/dark preference to a concrete theme."""
    if theme_mode in (THEME_LIGHT, THEME_DARK):
        return theme_mode

    try:
        color_scheme = app.styleHints().colorScheme()
        if color_scheme == Qt.ColorScheme.Light:
            return THEME_LIGHT
    except Exception:
        pass

    return THEME_DARK


def apply_theme(app: QApplication, theme_mode: str) -> None:
    """Load and apply the selected application stylesheet."""
    resolved = effective_theme(app, theme_mode)
    stylesheet_name = (
        "assets/styles/macos_light.qss"
        if resolved == THEME_LIGHT
        else "assets/styles/modern_theme.qss"
    )
    stylesheet_path = get_path(stylesheet_name)

    try:
        with open(stylesheet_path, "r") as f:
            app.setStyleSheet(f.read())
        app.setProperty("shuttle_theme", resolved)
    except FileNotFoundError:
        print("No stylesheet found - using default theme.")
