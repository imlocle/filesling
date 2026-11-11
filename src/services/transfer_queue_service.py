"""Application service for transfer queue persistence and recovery."""

from __future__ import annotations

import os
from typing import List, Optional

from src.models.transfer import QueuedTransfer
from src.repositories.transfer_queue_repository import TransferQueueRepository
from src.utils.logging_signal import logger


class TransferQueueService:
    """Coordinate serialization and recovery of queued uploads."""

    def __init__(self, repository: Optional[TransferQueueRepository] = None) -> None:
        self._repository = repository or TransferQueueRepository()

    def save(
        self,
        active: Optional[QueuedTransfer],
        pending: List[QueuedTransfer],
    ) -> None:
        """Persist the active and pending transfers."""
        try:
            self._repository.save(
                active.to_dict() if active else None,
                [transfer.to_dict() for transfer in pending],
            )
        except OSError as error:
            logger.warn(f"Transfer: Could not persist queue: {error}")

    def restore(self) -> List[QueuedTransfer]:
        """Load transfers whose local source paths still exist."""
        try:
            data = self._repository.load()
        except Exception as error:
            logger.warn(f"Transfer: Could not restore queue: {error}")
            self.clear()
            return []

        if not data:
            return []

        try:
            restored: List[QueuedTransfer] = []
            active = data.get("active")
            if isinstance(active, dict):
                restored.append(QueuedTransfer.from_dict(active))

            pending = data.get("pending", [])
            if isinstance(pending, list):
                restored.extend(
                    QueuedTransfer.from_dict(item)
                    for item in pending
                    if isinstance(item, dict)
                )
        except (TypeError, ValueError) as error:
            logger.warn(f"Transfer: Could not parse persisted queue: {error}")
            self.clear()
            return []

        restored = [
            transfer
            for transfer in restored
            if transfer.local_paths
            and any(os.path.exists(path) for path in transfer.local_paths)
        ]
        if not restored:
            self.clear()
        else:
            logger.info(f"Transfer: Restored {len(restored)} queued upload(s)")
        return restored

    def clear(self) -> None:
        """Remove persisted state after all queued work is complete."""
        try:
            self._repository.clear()
        except OSError as error:
            logger.warn(f"Transfer: Could not clear persisted queue: {error}")
