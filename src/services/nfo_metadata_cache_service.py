"""In-memory cache for NFO metadata in the currently browsed directory."""

from __future__ import annotations

import os
import posixpath
from typing import Dict, Optional


class NfoMetadataCacheService:
    """Keep parsed sidecar metadata ready for detail panel lookups."""

    def __init__(self) -> None:
        self._directory = ""
        self._metadata_by_video_base: Dict[str, Dict[str, str]] = {}
        self._is_ready = False

    def begin_directory(self, directory: str) -> None:
        """Clear stale entries while a directory listing and cache load run."""
        self._directory = self._normalize_path(directory)
        self._metadata_by_video_base.clear()
        self._is_ready = False

    def replace_directory(
        self, directory: str, metadata_by_path: Dict[str, Dict[str, str]]
    ) -> None:
        """Publish cache data only for the directory currently being browsed."""
        normalized_directory = self._normalize_path(directory)
        if normalized_directory != self._directory:
            return
        self._metadata_by_video_base = {
            os.path.splitext(self._normalize_path(path))[0]: dict(metadata)
            for path, metadata in metadata_by_path.items()
        }
        self._is_ready = True

    def get_for_video(self, video_path: str) -> Optional[Dict[str, str]]:
        """Return cached metadata, or None while this folder is still loading."""
        normalized_path = self._normalize_path(video_path)
        if not self._is_ready or posixpath.dirname(normalized_path) != self._directory:
            return None
        video_base = os.path.splitext(normalized_path)[0]
        return dict(self._metadata_by_video_base.get(video_base, {}))

    def invalidate_file(self, nfo_path: str) -> bool:
        """Invalidate the current directory cache after an NFO write."""
        normalized_path = self._normalize_path(nfo_path)
        if posixpath.dirname(normalized_path) != self._directory:
            return False
        video_base = os.path.splitext(normalized_path)[0]
        self._metadata_by_video_base.pop(video_base, None)
        self._is_ready = False
        return True

    def clear(self) -> None:
        """Drop cached values when the remote connection changes."""
        self._directory = ""
        self._metadata_by_video_base.clear()
        self._is_ready = False

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize remote paths independently of the local OS."""
        return posixpath.normpath(path.replace("\\", "/"))
