"""
Manual transfer controller with queue support.

Handles user-initiated transfers (drag-and-drop). Transfers are queued
and processed sequentially so the user can keep browsing and dropping
files while uploads run in the background.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from src.config.settings import Settings
from src.services.activity_history_service import ActivityHistoryService
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import SOFTWARE_NAME
from src.utils.logging_signal import logger
from src.workers.transfer_worker import TransferWorker

QUEUE_JSON = "transfer_queue.json"
MAX_AUTO_RETRIES = 3


@dataclass
class QueuedTransfer:
    """A transfer waiting in the queue."""

    local_paths: List[str]
    remote_destination: str
    delete_after: bool
    total_bytes: int = 0
    display_name: str = ""
    attempts: int = 0

    def __post_init__(self):
        if not self.display_name:
            names = [os.path.basename(p.rstrip("/")) for p in self.local_paths]
            self.display_name = ", ".join(names[:3])
            if len(names) > 3:
                self.display_name += f" (+{len(names) - 3} more)"
        # Calculate total bytes if not provided
        if self.total_bytes == 0:
            for p in self.local_paths:
                if os.path.isdir(p):
                    for root, _, files in os.walk(p):
                        for f in files:
                            if not f.startswith("."):
                                try:
                                    self.total_bytes += os.path.getsize(
                                        os.path.join(root, f)
                                    )
                                except OSError:
                                    pass
                elif os.path.isfile(p):
                    try:
                        self.total_bytes += os.path.getsize(p)
                    except OSError:
                        pass

    def to_dict(self) -> dict:
        """Serialize a queued transfer for crash recovery."""
        return {
            "local_paths": self.local_paths,
            "remote_destination": self.remote_destination,
            "delete_after": self.delete_after,
            "total_bytes": self.total_bytes,
            "display_name": self.display_name,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueuedTransfer":
        """Create a queued transfer from persisted state."""
        return cls(
            local_paths=list(data.get("local_paths", [])),
            remote_destination=data.get("remote_destination", ""),
            delete_after=bool(data.get("delete_after", True)),
            total_bytes=int(data.get("total_bytes", 0) or 0),
            display_name=data.get("display_name", ""),
            attempts=int(data.get("attempts", 0) or 0),
        )


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
    transfer_progress = Signal(int)  # percentage 0-100
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
        self.history = ActivityHistoryService()

        # Queue state
        self._queue: List[QueuedTransfer] = []
        self._is_processing = False

        # Active transfer state
        self._active_worker: Optional[TransferWorker] = None
        self._active_thread: Optional[QThread] = None
        self._current_transfer: Optional[QueuedTransfer] = None
        self._transfer_errored = False
        self._retry_current_transfer = False
        self._restored_from_disk = False

    def _queue_file_path(self) -> Path:
        """Path used to persist pending upload queue state."""
        return Path.home() / f".{SOFTWARE_NAME}" / QUEUE_JSON

    def _persist_queue(self) -> None:
        """Persist active and pending transfers for crash recovery."""
        payload = {
            "active": (
                self._current_transfer.to_dict()
                if self._current_transfer is not None
                else None
            ),
            "pending": [transfer.to_dict() for transfer in self._queue],
        }
        queue_path = self._queue_file_path()
        try:
            queue_path.parent.mkdir(exist_ok=True)
            with open(queue_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.warn(f"Transfer: Could not persist queue: {e}")

    def _clear_persisted_queue(self) -> None:
        """Remove persisted queue state when there is nothing left to recover."""
        try:
            self._queue_file_path().unlink(missing_ok=True)
        except Exception as e:
            logger.warn(f"Transfer: Could not clear persisted queue: {e}")

    def restore_persisted_queue(self) -> list[QueuedTransfer]:
        """
        Restore queued uploads from disk.

        Returns the restored transfers so the UI can recreate queue rows.
        """
        if self._restored_from_disk:
            return []
        self._restored_from_disk = True

        queue_path = self._queue_file_path()
        if not queue_path.exists():
            return []

        try:
            with open(queue_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.warn(f"Transfer: Could not restore queue: {e}")
            self._clear_persisted_queue()
            return []

        restored = []
        active = data.get("active")
        if active:
            restored.append(QueuedTransfer.from_dict(active))
        restored.extend(
            QueuedTransfer.from_dict(item) for item in data.get("pending", [])
        )
        restored = [transfer for transfer in restored if transfer.local_paths]
        restored = [
            transfer
            for transfer in restored
            if any(os.path.exists(path) for path in transfer.local_paths)
        ]
        if not restored:
            self._clear_persisted_queue()
            return []

        self._queue.extend(restored)
        logger.info(f"Transfer: Restored {len(restored)} queued upload(s)")
        self.queue_changed.emit(len(self._queue))
        return restored

    def start_processing(self) -> None:
        """Start processing queued transfers if the controller is idle."""
        if not self._is_processing and self._queue:
            self._process_next()

    def is_busy(self) -> bool:
        """Check if a transfer is currently in progress."""
        return self._is_processing

    def queue_size(self) -> int:
        """Number of pending transfers (not including current)."""
        return len(self._queue)

    def queue_transfer(
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
            # No destination specified — use remote base dir
            remote_dir = self.settings.remote_base_dir

        # Add to queue
        transfer = QueuedTransfer(
            local_paths=list(local_paths),
            remote_destination=remote_dir,
            delete_after=delete_after,
        )
        self._queue.append(transfer)
        self._persist_queue()
        total = len(self._queue) + (1 if self._is_processing else 0)
        self.queue_changed.emit(total)

        # Start processing if not already running
        if not self._is_processing:
            self._process_next()

        return True

    def _process_next(self) -> None:
        """Process the next item in the queue."""
        if not self._queue:
            self._is_processing = False
            self._current_transfer = None
            self._clear_persisted_queue()
            self.queue_changed.emit(0)
            return

        self._is_processing = True
        self._current_transfer = self._queue.pop(0)
        transfer = self._current_transfer
        self._transfer_errored = False
        self._retry_current_transfer = False
        self._persist_queue()
        self.transfer_started.emit(transfer.local_paths[0])

        # Determine connection type
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get("connection_type", "ssh") if server_config else "ssh"
        )

        # Get the appropriate client
        sftp = None
        if connection_type == "adb":
            # For ADB, use the client already on the explorer (no session needed)
            view = self.parent()
            if view and hasattr(view, "remote_explorer") and view.remote_explorer.sftp:  # type: ignore
                sftp = view.remote_explorer.sftp  # type: ignore
            else:
                logger.error("Transfer: No ADB connection available")
                self._handle_start_failure("No ADB connection")
                return
        else:
            # For SSH, ensure connection and open dedicated session
            if not self.connection_manager.is_connected():
                if not self.connection_manager.connect():
                    logger.error("Transfer: Connection failed")
                    self._handle_start_failure("Connection failed")
                    return

            try:
                sftp = self.connection_manager.open_sftp_session()
                if sftp is None:
                    logger.error("Transfer: Could not open SFTP session")
                    self._handle_start_failure("Could not open SFTP session")
                    return
            except Exception as e:
                logger.error(f"Transfer: Failed to start: {e}")
                self._handle_start_failure(str(e))
                return

        # Create thread and worker
        try:
            self._active_thread = QThread(self)
            self._active_worker = TransferWorker(
                sftp=sftp,
                local_paths=transfer.local_paths,
                remote_root=transfer.remote_destination,
                total_bytes=transfer.total_bytes,
            )
            self._active_worker.moveToThread(self._active_thread)

            # Connect signals
            self._active_thread.started.connect(self._active_worker.run)
            self._active_worker.finished.connect(self._on_transfer_finished)
            self._active_worker.error.connect(self._on_transfer_error)
            self._active_worker.progress.connect(self._on_transfer_progress)
            self._active_worker.finished.connect(self._active_thread.quit)
            self._active_worker.error.connect(self._active_thread.quit)
            self._active_thread.finished.connect(self._cleanup_and_next)

            self._active_thread.start()

            # Log: transfer start with name and destination
            logger.upload(f"Transfer: {transfer.display_name}")
            logger.info(f"Destination: {transfer.remote_destination}")

        except Exception as e:
            logger.error(f"Transfer: Failed to start: {e}")
            self._handle_start_failure(str(e))

    def _on_transfer_finished(self) -> None:
        """Handle transfer completion. Only delete files if no error occurred."""
        if not self._current_transfer:
            return

        # If error already handled this transfer, don't delete or emit success
        if self._transfer_errored:
            return

        transfer = self._current_transfer
        logger.success(f"Transfer: Complete: {transfer.display_name}")

        # Record in history
        for path in transfer.local_paths:
            self.history.add(
                filename=os.path.basename(path.rstrip("/")),
                action="upload",
                source=path,
                destination=transfer.remote_destination,
                size_bytes=transfer.total_bytes,
                server_name=self.settings.config.current_server_id,
            )

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

    def _should_retry(self, transfer: QueuedTransfer) -> bool:
        """Return whether a failed transfer should be retried automatically."""
        return transfer.attempts < MAX_AUTO_RETRIES

    def _schedule_retry(self, transfer: QueuedTransfer, error_msg: str) -> None:
        """Mark the current transfer for retry after worker cleanup."""
        transfer.attempts += 1
        self._retry_current_transfer = True
        self._persist_queue()
        logger.warn(
            "Transfer: Retrying "
            f"{transfer.display_name} ({transfer.attempts}/{MAX_AUTO_RETRIES})"
        )
        first_line = error_msg.split("\n")[0]
        if first_line:
            logger.info(f"Retry reason: {first_line}")
        self.transfer_progress.emit(0)

    def _handle_start_failure(self, error_msg: str) -> None:
        """Handle failures before the worker thread starts."""
        if not self._current_transfer:
            return

        transfer = self._current_transfer
        if self._should_retry(transfer):
            self._schedule_retry(transfer, error_msg)
        else:
            self._transfer_errored = True
            logger.error(f"Transfer: Failed: {transfer.display_name}: {error_msg}")
            self.transfer_failed.emit(transfer.local_paths[0], error_msg)

        QTimer.singleShot(100, self._cleanup_and_next)

    def _on_transfer_error(self, error_msg: str) -> None:
        """Handle transfer error. Marks transfer as errored to prevent deletion."""
        self._transfer_errored = True

        if not self._current_transfer:
            return

        transfer = self._current_transfer
        if self._should_retry(transfer):
            self._schedule_retry(transfer, error_msg)
            return

        logger.error(f"Transfer: Failed: {transfer.display_name}: {error_msg}")
        self.transfer_failed.emit(transfer.local_paths[0], error_msg)

    def _on_transfer_progress(self, percentage: int) -> None:
        """Forward progress from worker to UI."""
        self.transfer_progress.emit(percentage)

    def _cleanup_and_next(self) -> None:
        """Clean up current transfer and process next in queue."""
        if self._active_worker:
            self._active_worker.deleteLater()
            self._active_worker = None
        if self._active_thread:
            self._active_thread.deleteLater()
            self._active_thread = None

        if self._retry_current_transfer and self._current_transfer:
            self._queue.insert(0, self._current_transfer)
            self._current_transfer = None
            self._retry_current_transfer = False
            self._persist_queue()
            QTimer.singleShot(1000, self._process_next)
            return

        self._current_transfer = None
        self._persist_queue()

        # Process next item
        QTimer.singleShot(100, self._process_next)

    def clear_queue(self) -> None:
        """Clear all pending (not in-progress) transfers."""
        count = len(self._queue)
        self._queue.clear()
        self._persist_queue()
        if count > 0:
            logger.info(f"Transfer: Cleared {count} queued item(s)")
        self.queue_changed.emit(1 if self._is_processing else 0)

    def cancel_queued_item(self, visual_index: int) -> None:
        """
        Cancel a pending item by its position in the internal queue.

        Args:
            queue_index: Index relative to pending items (0 = next pending)
        """
        # The visual queue index includes completed/in-progress items,
        # but the internal queue only has pending items.
        # We need to map: count how many pending items precede this visual index.
        if 0 <= visual_index < len(self._queue):
            removed = self._queue.pop(visual_index)
            self._persist_queue()
            logger.info(f"Transfer: Cancelled: {removed.display_name}")
            self.queue_changed.emit(
                len(self._queue) + (1 if self._is_processing else 0)
            )
