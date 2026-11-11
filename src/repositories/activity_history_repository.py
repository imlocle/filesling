"""Repository for persisted activity records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.utils.constants import ACTIVITY_HISTORY_FILE, APP_DATA_DIR
from src.utils.json_file import read_json_file, write_json_file_atomic


class ActivityHistoryRepository:
    """Load and save the activity history document."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or APP_DATA_DIR / ACTIVITY_HISTORY_FILE

    def load(self) -> list[dict[str, Any]]:
        """Return stored records, treating a missing or malformed file as empty."""
        try:
            data = read_json_file(self.path, default=[])
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [record for record in data if isinstance(record, dict)]

    def save(self, records: list[dict[str, Any]]) -> None:
        """Atomically persist records so an interrupted write cannot truncate history."""
        write_json_file_atomic(self.path, records, indent=2, file_mode=0o600)
