"""
File type icon generation for FileSling.

Uses native macOS QStyle icons (play button for video, etc.) and tints them
white when dark mode is active so they remain visible against dark backgrounds.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

# Extension sets by file type
EXT_VIDEO = frozenset((".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"))
EXT_AUDIO = frozenset((".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma"))
EXT_IMAGE = frozenset(
    (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff")
)
EXT_ARCHIVE = frozenset((".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz"))
EXT_CODE = frozenset(
    (".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yaml", ".yml")
)
EXT_DOCUMENT = frozenset((".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"))
EXT_EXECUTABLE = frozenset((".apk", ".ipa", ".exe", ".dmg", ".app", ".deb", ".rpm"))

# Extensions whose icons are solid/simple and safe to tint white in dark mode
EXT_TINT_WHITE = EXT_VIDEO | EXT_AUDIO


def _is_dark_mode() -> bool:
    """Check if the app is currently using a dark theme."""
    app = QApplication.instance()
    if not app:
        return False
    theme = app.property("filesling_theme")
    if theme == "light":
        return False
    if theme == "dark":
        return True
    try:
        color_scheme = app.styleHints().colorScheme()
        return color_scheme != Qt.ColorScheme.Light
    except Exception:
        return True


def _tint_icon_white(icon: QIcon, size: int = 16) -> QIcon:
    """Create a white-tinted version of an icon for dark backgrounds."""
    pixmap = icon.pixmap(QSize(size, size))
    if pixmap.isNull():
        return icon

    white_pixmap = QPixmap(pixmap.size())
    white_pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(white_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(white_pixmap.rect(), QColor(255, 255, 255, 220))
    painter.end()

    return QIcon(white_pixmap)


def get_file_icon(is_dir: bool, filename: str = "") -> QIcon:
    """
    Get a file/folder icon based on type.

    Uses native QStyle icons (play for video, volume for audio, etc.)
    and tints solid icons white in dark mode for visibility.
    """
    from PySide6.QtWidgets import QStyle

    app = QApplication.instance()
    if not app:
        return QIcon()

    style = app.style()
    dark = _is_dark_mode()

    if is_dir:
        return style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    ext = os.path.splitext(filename)[1].lower() if filename else ""

    if ext in EXT_VIDEO:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
    elif ext in EXT_AUDIO:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
    elif ext in EXT_IMAGE:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
    elif ext in EXT_ARCHIVE:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
    elif ext in EXT_CODE:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
    elif ext in EXT_DOCUMENT:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
    elif ext in EXT_EXECUTABLE:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    else:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    if dark and ext in EXT_TINT_WHITE:
        return _tint_icon_white(icon)

    return icon
