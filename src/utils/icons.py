"""
File type icon generation for FileSling.

Creates colored file icons that are visible in both light and dark themes.
Folder icons use the native macOS style; file icons are custom-drawn with
color coding by extension type.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication


def get_file_icon(is_dir: bool, filename: str = "") -> QIcon:
    """Get a file/folder icon based on type. Uses colored pixmaps for theme compatibility."""
    from PySide6.QtWidgets import QStyle

    app = QApplication.instance()
    if not app:
        return QIcon()

    style = app.style()

    # Folders always use the native icon (macOS folder icons work in both themes)
    if is_dir:
        return style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    # For files, determine a color based on type and create a simple colored icon
    ext = os.path.splitext(filename)[1].lower() if filename else ""

    # Map extensions to colors (visible in both light and dark mode)
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"):
        color = QColor("#ff6b6b")  # Red for video
    elif ext in (".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma"):
        color = QColor("#a855f7")  # Purple for audio
    elif ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff"):
        color = QColor("#22c55e")  # Green for images
    elif ext in (".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz"):
        color = QColor("#f59e0b")  # Amber for archives
    elif ext in (".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yaml"):
        color = QColor("#3b82f6")  # Blue for code
    elif ext in (".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"):
        color = QColor("#6366f1")  # Indigo for documents
    elif ext in (".srt", ".sub", ".ass", ".vtt"):
        color = QColor("#14b8a6")  # Teal for subtitles
    elif ext in (".apk", ".ipa", ".exe", ".dmg", ".app"):
        color = QColor("#ec4899")  # Pink for executables
    else:
        color = QColor("#94a3b8")  # Slate gray for unknown

    # Create a small colored file icon
    size = QSize(16, 16)
    pixmap = QPixmap(size)
    pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw a rounded rectangle as the file shape
    pen = QPen(color)
    pen.setWidth(1)
    painter.setPen(pen)
    painter.setBrush(color.lighter(160))

    # File body
    painter.drawRoundedRect(2, 1, 11, 14, 2, 2)

    # Dog-ear (top-right corner fold)
    painter.setBrush(color)
    painter.drawPolygon(
        [
            QPoint(9, 1),
            QPoint(13, 5),
            QPoint(9, 5),
        ]
    )

    painter.end()
    return QIcon(pixmap)
