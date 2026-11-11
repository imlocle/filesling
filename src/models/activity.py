"""Data model for one FileSling activity history entry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ActivityRecord:
    """A completed or failed file operation recorded for the user."""

    filename: str
    action: str
    source: str = ""
    destination: str = ""
    size_bytes: int = 0
    timestamp: str = ""
    server_name: str = ""
    status: str = "completed"

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
