"""Repository for crash-recovery transfer queue state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.utils.constants import APP_DATA_DIR, TRANSFER_QUEUE_FILE
from src.utils.json_file import read_json_file, write_json_file_atomic


class TransferQueueRepository:
    """Persist the active upload and pending uploads as one JSON document."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or APP_DATA_DIR / TRANSFER_QUEUE_FILE

    def load(self) -> Optional[dict[str, Any]]:
        """Load persisted queue state, returning ``None`` when there is no file."""
        data = read_json_file(self.path)
        return data if isinstance(data, dict) else None

    def save(self, active: Optional[dict], pending: list[dict]) -> None:
        """Atomically save active and pending transfer records."""
        write_json_file_atomic(
            self.path,
            {"active": active, "pending": pending},
            indent=2,
            file_mode=0o600,
        )

    def clear(self) -> None:
        """Remove the queue document if it exists."""
        self.path.unlink(missing_ok=True)
