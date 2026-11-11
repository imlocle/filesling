"""Filename and folder hints for media metadata workflows."""

from __future__ import annotations

import os
import re

_EPISODE_PATTERN = re.compile(r"\bS(\d{1,2})E(\d{1,3})(?:E\d{1,3})?\b", re.IGNORECASE)
_SEASON_PATTERN = re.compile(r"^season[ ._-]*(\d{1,2})$", re.IGNORECASE)


def infer_tv_metadata_from_path(media_path: str) -> dict[str, str]:
    """Infer show, season, episode, and title from common Jellyfin paths."""
    normalized = media_path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return {}

    filename = os.path.splitext(parts[-1])[0]
    episode_match = _EPISODE_PATTERN.search(filename)
    season_match = _SEASON_PATTERN.match(parts[-2]) if len(parts) > 1 else None
    if not episode_match and not season_match:
        return {}

    fields: dict[str, str] = {}
    show_index = len(parts) - 2
    if season_match:
        fields["season_number"] = season_match.group(1).lstrip("0") or "0"
        show_index -= 1
    if episode_match:
        fields["season_number"] = episode_match.group(1).lstrip("0") or "0"
        fields["episode_sort"] = episode_match.group(2).lstrip("0") or "0"

    if show_index >= 0:
        show_name = parts[show_index]
        if show_name.casefold() not in {"tv", "shows", "series", "media"}:
            fields["show"] = show_name
            fields["album"] = show_name

    title = filename
    if episode_match:
        title = _EPISODE_PATTERN.sub(" ", title)
    show_name = fields.get("show", "")
    if show_name and title.casefold().startswith(show_name.casefold()):
        title = title[len(show_name) :]
    title = re.sub(r"^[\s._-]+|[\s._-]+$", "", title)
    if title:
        fields["title"] = title
    return fields
