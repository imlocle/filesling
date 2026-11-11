"""Data models used by media inspection and repair workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SubtitleTrack:
    """One subtitle stream reported by ffprobe."""

    index: int
    language: str
    codec: str
    title: str = ""


@dataclass
class AudioTrack:
    """One audio stream reported by ffprobe."""

    index: int
    language: str
    codec: str
    title: str = ""


@dataclass
class QuickFixOptions:
    """User-selected media repair operations."""

    to_mp4: bool = False
    fix_timestamps: bool = False
    strip_subtitles: bool = False
    keep_subtitle_indices: Optional[List[int]] = None
    strip_audio: bool = False
    keep_audio_indices: Optional[List[int]] = None
