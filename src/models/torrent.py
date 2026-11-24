"""Typed torrent status returned by qBittorrent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _as_string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_integer(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class TorrentInfo:
    """Small, display-ready subset of qBittorrent's torrent record."""

    hash: str
    name: str
    state: str
    progress: float
    download_speed: int
    upload_speed: int
    save_path: str

    @classmethod
    def from_api(cls, data: Mapping[str, object]) -> "TorrentInfo":
        """Parse the fields used by FileSling from a Web API torrent record."""
        return cls(
            hash=_as_string(data.get("hash")),
            name=_as_string(data.get("name")) or "Unnamed torrent",
            state=_as_string(data.get("state")) or "unknown",
            progress=max(0.0, min(1.0, _as_float(data.get("progress")))),
            download_speed=max(0, _as_integer(data.get("dlspeed"))),
            upload_speed=max(0, _as_integer(data.get("upspeed"))),
            save_path=_as_string(data.get("save_path")),
        )
