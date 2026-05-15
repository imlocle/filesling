"""
Transfer history service — persists upload/download records to JSON.

Stores the last 200 transfers in ~/.Shuttle/transfer_history.json.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from src.utils.constants import SOFTWARE_NAME

HISTORY_FILE = "transfer_history.json"
MAX_HISTORY = 200


@dataclass
class TransferRecord:
    """A single transfer record."""

    filename: str
    direction: str  # "upload" or "download"
    source: str  # local path (upload) or remote path (download)
    destination: str  # remote path (upload) or local path (download)
    size_bytes: int = 0
    timestamp: str = ""
    server_name: str = ""
    status: str = "completed"  # "completed" or "failed"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TransferHistoryService:
    """Manages persistent transfer history."""

    def __init__(self):
        self._history_path = Path.home() / f".{SOFTWARE_NAME}" / HISTORY_FILE
        self._records: List[TransferRecord] = []
        self._load()

    def _load(self) -> None:
        """Load history from disk."""
        try:
            if self._history_path.exists():
                with open(self._history_path, "r") as f:
                    data = json.load(f)
                self._records = [TransferRecord(**r) for r in data]
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
            pass  # Non-critical — don't crash if we can't write history

    def add(
        self,
        filename: str,
        direction: str,
        source: str,
        destination: str,
        size_bytes: int = 0,
        server_name: str = "",
        status: str = "completed",
    ) -> None:
        """Add a transfer record."""
        record = TransferRecord(
            filename=filename,
            direction=direction,
            source=source,
            destination=destination,
            size_bytes=size_bytes,
            server_name=server_name,
            status=status,
        )
        self._records.append(record)
        # Trim to max
        if len(self._records) > MAX_HISTORY:
            self._records = self._records[-MAX_HISTORY:]
        self._save()

    @property
    def records(self) -> List[TransferRecord]:
        """Get all records (newest last)."""
        return self._records

    def search(self, query: str) -> List[TransferRecord]:
        """Search history by filename."""
        query = query.lower()
        return [r for r in self._records if query in r.filename.lower()]

    def has_been_uploaded(self, filename: str, destination: str) -> bool:
        """Check if a file was previously uploaded to a destination."""
        return any(
            r.filename == filename
            and r.destination == destination
            and r.direction == "upload"
            and r.status == "completed"
            for r in self._records
        )

    def clear(self) -> None:
        """Clear all history."""
        self._records = []
        self._save()
