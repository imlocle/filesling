"""Shared local file and directory size helpers."""

from __future__ import annotations

import os


def format_bytes(size_bytes: int) -> str:
    """Format a byte count using FileSling's compact display units."""
    if size_bytes < 0:
        return "N/A"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024**3:
        return f"{size_bytes / (1024**2):.1f} MB"
    return f"{size_bytes / (1024**3):.2f} GB"


def get_directory_size(path: str, *, include_hidden: bool = True) -> int:
    """Return the size of regular files below a directory, ignoring unreadable files."""
    total = 0
    for directory, child_directories, filenames in os.walk(path):
        if not include_hidden:
            child_directories[:] = [
                name for name in child_directories if not name.startswith(".")
            ]
            filenames = [name for name in filenames if not name.startswith(".")]

        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(directory, filename))
            except OSError:
                continue
    return total


def get_local_path_size(path: str, *, include_hidden: bool = True) -> int:
    """Return a file or directory size, or zero when the path cannot be read."""
    try:
        if os.path.isdir(path):
            return get_directory_size(path, include_hidden=include_hidden)
        return os.path.getsize(path)
    except OSError:
        return 0
