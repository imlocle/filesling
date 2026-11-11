"""
Activity history service: persists file operation records to JSON.

Stores the last MAX_ACTIVITY_HISTORY actions in ~/.FileSling/activity_history.json.
Tracks: uploads, downloads, renames, deletes, moves.
"""

from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Protocol

from src.models.activity import ActivityRecord
from src.repositories.activity_history_repository import ActivityHistoryRepository
from src.utils.constants import ACTIVITY_HISTORY_FILE, APP_DATA_DIR, MAX_ACTIVITY_HISTORY
from src.utils.logging_signal import logger


class ActivityHistorySettings(Protocol):
    """Settings required by activity history policy."""

    def get_activity_history_enabled_for_server(self) -> bool: ...


class ActivityHistoryService:
    """Apply activity-history rules and coordinate repository persistence."""

    def __init__(
        self,
        repository: Optional[ActivityHistoryRepository] = None,
        settings: Optional[ActivityHistorySettings] = None,
    ) -> None:
        self._repository = repository or ActivityHistoryRepository()
        self._history_path = self._repository.path
        self._settings = settings
        self._records: List[ActivityRecord] = []
        self._load()

    def _get_repository(self) -> ActivityHistoryRepository:
        """Return the configured repository, supporting older test fixtures."""
        repository = getattr(self, "_repository", None)
        if repository is None:
            path = getattr(
                self,
                "_history_path",
                APP_DATA_DIR / ACTIVITY_HISTORY_FILE,
            )
            repository = ActivityHistoryRepository(Path(path))
            self._repository = repository
        return repository

    def _load(self) -> None:
        """Load history from disk."""
        try:
            records = []
            for record_data in self._get_repository().load():
                if "direction" in record_data and "action" not in record_data:
                    record_data = {**record_data, "action": record_data["direction"]}
                record_data.pop("direction", None)
                records.append(ActivityRecord(**record_data))
            self._records = records
        except (TypeError, ValueError, KeyError) as error:
            logger.warn(f"Activity history: Could not load records: {error}")
            self._records = []

    def _save(self) -> None:
        """Save history to disk."""
        try:
            self._get_repository().save(
                [asdict(record) for record in self._records[-MAX_ACTIVITY_HISTORY:]]
            )
        except OSError as error:
            logger.warn(f"Activity history: Could not save records: {error}")

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
        """Add an activity record. Skipped if history is disabled for the active server."""
        settings = self._settings
        if settings is None:
            from src.config.settings import Settings

            settings = Settings()
        if not settings.get_activity_history_enabled_for_server():
            return

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
        if len(self._records) > MAX_ACTIVITY_HISTORY:
            self._records = self._records[-MAX_ACTIVITY_HISTORY:]
        self._save()

    @property
    def records(self) -> List[ActivityRecord]:
        """Get all records (newest last)."""
        return list(self._records)

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
