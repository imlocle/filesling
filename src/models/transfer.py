"""Data model for a queued local-to-remote upload."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List

from src.utils.file_size import get_local_path_size


@dataclass
class QueuedTransfer:
    """An upload request that can be serialized for crash recovery."""

    local_paths: List[str]
    remote_destination: str
    delete_after: bool
    total_bytes: int = 0
    display_name: str = ""
    attempts: int = 0

    def __post_init__(self) -> None:
        if not self.display_name:
            names = [os.path.basename(path.rstrip("/\\")) for path in self.local_paths]
            self.display_name = ", ".join(names[:3])
            if len(names) > 3:
                self.display_name += f" (+{len(names) - 3} more)"

        if self.total_bytes <= 0:
            self.total_bytes = sum(
                get_local_path_size(path, include_hidden=True)
                for path in self.local_paths
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the transfer for crash recovery."""
        return {
            "local_paths": self.local_paths,
            "remote_destination": self.remote_destination,
            "delete_after": self.delete_after,
            "total_bytes": self.total_bytes,
            "display_name": self.display_name,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueuedTransfer":
        """Rebuild a transfer from persisted state using safe defaults."""
        return cls(
            local_paths=list(data.get("local_paths", [])),
            remote_destination=str(data.get("remote_destination", "")),
            delete_after=bool(data.get("delete_after", True)),
            total_bytes=int(data.get("total_bytes", 0) or 0),
            display_name=str(data.get("display_name", "")),
            attempts=int(data.get("attempts", 0) or 0),
        )
