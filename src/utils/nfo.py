"""Shared parsing helpers for Jellyfin-compatible NFO metadata."""

from __future__ import annotations

import xml.etree.ElementTree as ET


def parse_nfo_content(content: str) -> dict[str, str]:
    """Parse supported NFO child fields into a normalized key/value mapping."""
    if not content.strip() or not content.lstrip().startswith("<"):
        return {}

    root = ET.fromstring(content)
    metadata: dict[str, str] = {}
    for element in root:
        if not element.text:
            continue
        key = element.tag.lower()
        value = element.text.strip()
        if key == "genre" and key in metadata:
            metadata[key] += ";" + value
        else:
            metadata[key] = value
    return metadata
