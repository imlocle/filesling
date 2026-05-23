"""
Activity history service — persists file operation records to JSON.

Stores the last 500 actions in ~/.Shuttle/activity_history.json.
Tracks: uploads, downloads, renames, deletes, moves.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from src.utils.constants import SOFTWARE_NAME

HISTORY_FILE = "activity_history.json"
MAX_HISTORY = 500


@dataclass
class ActivityRecord:
    """A single activity record."""

    filename: str
    action: str  # "upload", "download", "rename", "delete", "move"
    source: str = ""  # original path
    destination: str = ""  # new path (for upload/download/move/rename)
    size_bytes: int = 0
    timestamp: str = ""
    server_name: str = ""
    status: str = "completed"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ActivityHistoryService:
    """Manages persistent activity history."""

    def __init__(self):
        self._history_path = Path.home() / f".{SOFTWARE_NAME}" / HISTORY_FILE
        self._records: List[ActivityRecord] = []
        self._load()

    def _load(self) -> None:
        """Load history from disk."""
        path = self._history_path

        try:
            if path.exists():
                with open(path, "r") as f:
                    data = json.load(f)
                self._records = []
                for r in data:
                    # Handle old "direction" field → "action"
                    if "direction" in r and "action" not in r:
                        r["action"] = r.pop("direction")
                    self._records.append(ActivityRecord(**r))
        except (json.JSONDecodeError, TypeError, KeyError):
            self._records = []

    def _save(self) -> None:
        """Save history to disk."""
        try:
            self._history_path.parent.mkdir(exist_ok=True)
            with open(self._history_path, "w") as f:
                json.dump(
                    [asdict(r) for r in self._records[-MAX_HISTORY:]],
                    f,
                    indent=2,
                )
        except (OSError, PermissionError):
            pass

    def add(
        self,
        filename: str,
        action: str,
        source: str = "",
        destination: str = "",
        size_bytes: int = 0,
        server_name: str = "",
        status: str = "completed",
        # Keep backward compat for old callers using "direction"
        direction: str = "",
    ) -> None:
        """Add an activity record."""
        actual_action = direction or action
        record = ActivityRecord(
            filename=filename,
            action=actual_action,
            source=source,
            destination=destination,
            size_bytes=size_bytes,
            server_name=server_name,
            status=status,
        )
        self._records.append(record)
        if len(self._records) > MAX_HISTORY:
            self._records = self._records[-MAX_HISTORY:]
        self._save()

    @property
    def records(self) -> List[ActivityRecord]:
        """Get all records (newest last)."""
        return self._records

    def search(self, query: str) -> List[ActivityRecord]:
        """Search history by filename."""
        query = query.lower()
        return [r for r in self._records if query in r.filename.lower()]

    def has_been_uploaded(self, filename: str, destination: str) -> bool:
        """Check if a file was previously uploaded to a destination."""
        return any(
            r.filename == filename
            and r.destination == destination
            and r.action == "upload"
            and r.status == "completed"
            for r in self._records
        )

    def clear(self) -> None:
        """Clear all history."""
        self._records = []
        self._save()
