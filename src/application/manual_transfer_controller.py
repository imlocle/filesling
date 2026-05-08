"""
Manual transfer controller with queue support.

Handles user-initiated transfers (drag-and-drop). Transfers are queued
and processed sequentially so the user can keep browsing and dropping
files while uploads run in the background.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from src.application.path_mapper import PathMapper
from src.config.settings import Settings
from src.controllers.transfer_worker import TransferWorker
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.logging_signal import logger


@dataclass
class QueuedTransfer:
    """A transfer waiting in the queue."""
    local_paths: List[str]
    remote_destination: str
    delete_after: bool
    display_name: str = ""

    def __post_init__(self):
        if not self.display_name:
            names = [os.path.basename(p) for p in self.local_paths]
            self.display_name = ", ".join(names[:3])
            if len(names) > 3:
                self.display_name += f" (+{len(names) - 3} more)"


class ManualTransferController(QObject):
    """
    Controller for manual (user-initiated) transfers with queue support.

    Users can drop files at any time. Transfers are queued and processed
    one at a time in the background. The explorer stays interactive.
    """

    # Signals
    transfer_started = Signal(str)  # path
    transfer_completed = Signal(str)  # path
    transfer_failed = Signal(str, str)  # path, error
    queue_changed = Signal(int)  # queue size (including current)

    def __init__(
        self,
        settings: Settings,
        connection_manager: ConnectionManagerService,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.connection_manager = connection_manager
        self.path_mapper = PathMapper(
            settings.local_watch_dir, settings.remote_base_dir
        )

        # Queue state
        self._queue: List[QueuedTransfer] = []
        self._is_processing = False

        # Active transfer state
        self._active_worker: Optional[TransferWorker] = None
        self._active_thread: Optional[QThread] = None
        self._current_transfer: Optional[QueuedTransfer] = None

    def is_busy(self) -> bool:
        """Check if a transfer is currently in progress."""
        return self._is_processing

    def queue_size(self) -> int:
        """Number of pending transfers (not including current)."""
        return len(self._queue)

    def transfer_to_pi(
        self,
        local_paths: List[str],
        remote_destination: Optional[str] = None,
        delete_after: Optional[bool] = None,
    ) -> bool:
        """
        Queue files for transfer to remote server.

        Unlike the old implementation, this never rejects because "busy".
        It always queues and processes sequentially.

        Args:
            local_paths: List of local file/folder paths to transfer
            remote_destination: Remote directory to upload into
            delete_after: Whether to delete local files after transfer

        Returns:
            True if queued successfully
        """
        if not local_paths:
            logger.warn("Transfer: No paths provided")
            return False

        # Determine delete preference
        if delete_after is None:
            delete_after = self.settings.delete_after_transfer

        # Determine remote destination
        if remote_destination:
            remote_dir = remote_destination
        else:
            try:
                first_path = Path(local_paths[0])
                if self.path_mapper.is_under_local_base(first_path):
                    remote_path = self.path_mapper.map_to_remote(first_path)
                    remote_dir = str(remote_path.parent)
                else:
                    remote_dir = self.settings.remote_base_dir
            except Exception as e:
                logger.error(f"Transfer: Path mapping failed: {e}")
                return False

        # Add to queue
        transfer = QueuedTransfer(
            local_paths=list(local_paths),
            remote_destination=remote_dir,
            delete_after=delete_after,
        )
        self._queue.append(transfer)
        total = len(self._queue) + (1 if self._is_processing else 0)
        self.queue_changed.emit(total)

        logger.info(f"Transfer: Queued: {transfer.display_name} → {os.path.basename(remote_dir)}/")

        # Start processing if not already running
        if not self._is_processing:
            self._process_next()

        return True

    def _process_next(self) -> None:
        """Process the next item in the queue."""
        if not self._queue:
            self._is_processing = False
            self.queue_changed.emit(0)
            return

        self._is_processing = True
        self._current_transfer = self._queue.pop(0)
        transfer = self._current_transfer

        # Ensure connection
        if not self.connection_manager.is_connected():
            if not self.connection_manager.connect():
                logger.error("Transfer: Connection failed")
                self.transfer_failed.emit(
                    transfer.local_paths[0], "Connection failed"
                )
                # Try next item
                QTimer.singleShot(100, self._process_next)
                return

        # Open a dedicated SFTP session for this transfer
        try:
            sftp = self.connection_manager.open_sftp_session()
            if sftp is None:
                logger.error("Transfer: Could not open SFTP session")
                self.transfer_failed.emit(
                    transfer.local_paths[0], "Could not open SFTP session"
                )
                QTimer.singleShot(100, self._process_next)
                return

            # Create thread and worker
            self._active_thread = QThread(self)
            self._active_worker = TransferWorker(
                sftp=sftp,
                local_paths=transfer.local_paths,
                remote_root=transfer.remote_destination,
            )
            self._active_worker.moveToThread(self._active_thread)

            # Connect signals
            self._active_thread.started.connect(self._active_worker.run)
            self._active_worker.finished.connect(self._on_transfer_finished)
            self._active_worker.error.connect(self._on_transfer_error)
            self._active_worker.finished.connect(self._active_thread.quit)
            self._active_worker.error.connect(self._active_thread.quit)
            self._active_thread.finished.connect(self._cleanup_and_next)

            # Start
            self._active_thread.start()

            logger.upload(f"Transfer: Started: {transfer.display_name}")
            self.transfer_started.emit(transfer.local_paths[0])

        except Exception as e:
            logger.error(f"Transfer: Failed to start: {e}")
            self.transfer_failed.emit(transfer.local_paths[0], str(e))
            QTimer.singleShot(100, self._process_next)

    def _on_transfer_finished(self) -> None:
        """Handle successful transfer completion."""
        if not self._current_transfer:
            return

        transfer = self._current_transfer
        logger.success(f"Transfer: Complete: {transfer.display_name}")

        # Delete local files if configured
        if transfer.delete_after:
            from src.services.file_deletion_service import FileDeletionService

            deletion_service = FileDeletionService()
            for path in transfer.local_paths:
                try:
                    if os.path.isdir(path):
                        deletion_service.delete_folder(path)
                    elif os.path.isfile(path):
                        deletion_service.delete_file(path)
                except Exception as e:
                    logger.warn(
                        f"Transfer: {os.path.basename(path)}: Could not delete - {e}"
                    )

        self.transfer_completed.emit(transfer.local_paths[0])

    def _on_transfer_error(self, error_msg: str) -> None:
        """Handle transfer error."""
        if not self._current_transfer:
            return

        transfer = self._current_transfer
        logger.error(f"Transfer: Failed: {transfer.display_name}: {error_msg}")
        self.transfer_failed.emit(transfer.local_paths[0], error_msg)

    def _cleanup_and_next(self) -> None:
        """Clean up current transfer and process next in queue."""
        if self._active_worker:
            self._active_worker.deleteLater()
            self._active_worker = None
        if self._active_thread:
            self._active_thread.deleteLater()
            self._active_thread = None
        self._current_transfer = None

        # Process next item
        QTimer.singleShot(100, self._process_next)

    def cancel_transfer(self) -> bool:
        """Cancel not yet implemented."""
        logger.warn("Transfer: Cancellation not yet implemented")
        return False

    def clear_queue(self) -> None:
        """Clear all pending (not in-progress) transfers."""
        count = len(self._queue)
        self._queue.clear()
        if count > 0:
            logger.info(f"Transfer: Cleared {count} queued item(s)")
        self.queue_changed.emit(1 if self._is_processing else 0)
