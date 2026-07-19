"""
Download controller — manages file downloads from remote to local.

Supports parallel downloads (up to MAX_PARALLEL_DOWNLOADS concurrent) with:
- Per-download retry logic (up to 3 attempts)
- Per-download progress tracking via transfer queue widget
- Activity history recording
- macOS notifications on completion/failure
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtWidgets import QMessageBox

from src.config.settings import Settings
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.constants import (
    CONN_TYPE_ADB,
    CONN_TYPE_KEY,
    CONN_TYPE_SSH,
    DIALOG_FILE_ALREADY_EXISTS,
    MAX_DOWNLOAD_RETRIES,
    MAX_PARALLEL_DOWNLOADS,
)
from src.utils.logging_signal import logger

if TYPE_CHECKING:
    from src.controllers.transfer_controller import ManualTransferController
    from src.views.main_window import MainWindow


@dataclass
class _DownloadSlot:
    """State for a single active download."""

    thread: Optional[QThread] = None
    worker: object = None
    sftp_session: object = None
    queue_index: int = -1
    attempts: int = 0
    error_msg: Optional[str] = None
    remote_paths: List[str] = field(default_factory=list)
    local_dir: str = ""
    total_bytes: int = 0


class DownloadController(QObject):
    """
    Controls file download operations from remote devices.

    Supports up to MAX_PARALLEL_DOWNLOADS concurrent downloads. Each download
    gets its own SFTP session and QThread.

    Inherits QObject so Qt can auto-detect cross-thread signal connections
    from download workers back to the main thread.
    """

    def __init__(
        self,
        view: "MainWindow",
        settings: Settings,
        connection_manager: ConnectionManagerService,
        transfer_controller: "ManualTransferController",
    ) -> None:
        super().__init__(view)  # QObject parent = main thread affinity
        self.view = view
        self.settings = settings
        self.connection_manager = connection_manager
        self.transfer_controller = transfer_controller

        # Active download slots
        self._active: List[_DownloadSlot] = []
        # Pending downloads waiting for a free slot
        self._pending: List[tuple] = (
            []
        )  # (remote_paths, local_dir, total_bytes, queue_index)

    @property
    def is_active(self) -> bool:
        """True if any download is currently in progress."""
        return len(self._active) > 0

    @property
    def active_count(self) -> int:
        return len(self._active)

    def download_item(self, remote_path: str) -> None:
        """Download a single file or folder."""
        self._download_paths([remote_path])

    def download_items(self, remote_paths: List[str]) -> None:
        """Download multiple files/folders."""
        if remote_paths:
            self._download_paths(remote_paths)

    def _download_paths(self, remote_paths: List[str]) -> None:
        """
        Prepare download: duplicate detection, queue display, then start or enqueue.
        """
        # Use per-server download directory if configured, else global
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        local_dir = (
            server_config.get("download_directory")
            if server_config and server_config.get("download_directory")
            else self.settings.download_directory
        )
        os.makedirs(local_dir, exist_ok=True)

        # Duplicate detection
        paths_to_download = []
        for remote_path in remote_paths:
            filename = os.path.basename(remote_path)
            local_path = os.path.join(local_dir, filename)
            if os.path.exists(local_path):
                if len(remote_paths) == 1:
                    reply = QMessageBox.question(
                        self.view,
                        DIALOG_FILE_ALREADY_EXISTS,
                        f"'{filename}' already exists in your download folder."
                        "\n\nOverwrite it?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        logger.info(f"Download: Skipped (already exists): {filename}")
                        return
                else:
                    logger.info(f"Download: Skipping (already exists): {filename}")
                    continue
            paths_to_download.append(remote_path)

        if not paths_to_download:
            logger.info("Download: All files already exist locally, nothing to do")
            return

        # Get connection
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            logger.error("Download: No connection available")
            return

        # Calculate total bytes
        total_bytes = 0
        for remote_path in paths_to_download:
            try:
                st = sftp.stat(remote_path)
                if st.st_size:
                    total_bytes += st.st_size
            except (IOError, OSError):
                pass

        # Display name
        if len(paths_to_download) == 1:
            display_name = f"⬇ {os.path.basename(paths_to_download[0])}"
        else:
            names = [os.path.basename(p) for p in paths_to_download[:3]]
            display_name = f"⬇ {', '.join(names)}"
            if len(paths_to_download) > 3:
                display_name += f" (+{len(paths_to_download) - 3} more)"

        # Add to visual queue
        queue_index = -1
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            method = self.transfer_controller.get_transfer_method()
            queue_index = queue.add_transfer(
                display_name, total_bytes, local_dir, method
            )

        # Start or enqueue
        if len(self._active) < MAX_PARALLEL_DOWNLOADS:
            self._start_download(paths_to_download, local_dir, total_bytes, queue_index)
        else:
            self._pending.append(
                (paths_to_download, local_dir, total_bytes, queue_index)
            )
            logger.info(f"Download: Queued (waiting for slot): {display_name}")

    def _start_download(
        self,
        remote_paths: List[str],
        local_dir: str,
        total_bytes: int,
        queue_index: int,
    ) -> None:
        """Start a download on a free slot."""
        from src.workers.download_worker import DownloadWorker

        # Mark as in-progress in queue
        if hasattr(self.view, "transfer_queue") and queue_index >= 0:
            self.view.transfer_queue.set_in_progress(queue_index)

        # Get SFTP session
        server_config = self.settings.get_server(self.settings.config.current_server_id)
        connection_type = (
            server_config.get(CONN_TYPE_KEY, CONN_TYPE_SSH)
            if server_config
            else CONN_TYPE_SSH
        )

        sftp = self.view.remote_explorer.sftp
        if connection_type == CONN_TYPE_ADB:
            download_sftp = sftp
            sftp_session = None
        else:
            try:
                download_sftp = self.connection_manager.open_sftp_session()
                if download_sftp is None:
                    logger.error("Download: Could not open SFTP session")
                    if hasattr(self.view, "transfer_queue") and queue_index >= 0:
                        self.view.transfer_queue.set_failed(
                            queue_index, "Could not open SFTP session"
                        )
                    self._process_pending()
                    return
                sftp_session = download_sftp
            except Exception as e:
                logger.error(f"Download: Failed to open session: {e}")
                if hasattr(self.view, "transfer_queue") and queue_index >= 0:
                    self.view.transfer_queue.set_failed(queue_index, str(e))
                self._process_pending()
                return

        # Create slot
        slot = _DownloadSlot(
            queue_index=queue_index,
            remote_paths=remote_paths,
            local_dir=local_dir,
            total_bytes=total_bytes,
            sftp_session=sftp_session,
        )
        self._active.append(slot)

        # Create thread and worker
        slot.thread = QThread(self.view)
        slot.worker = DownloadWorker(
            sftp=download_sftp,
            remote_paths=remote_paths,
            local_destination=local_dir,
            total_bytes=total_bytes,
        )
        slot.worker.moveToThread(slot.thread)

        # Connect signals — use lambdas with explicit QueuedConnection
        # because lambdas don't have QObject affinity for auto-detection.
        from PySide6.QtCore import Qt

        slot.thread.started.connect(slot.worker.run)
        slot.worker.progress.connect(
            lambda pct, s=slot: self._on_progress(s, pct),
            Qt.ConnectionType.QueuedConnection,
        )
        slot.worker.finished.connect(slot.thread.quit)
        slot.worker.error.connect(
            lambda msg, s=slot: self._on_error(s, msg),
            Qt.ConnectionType.QueuedConnection,
        )
        slot.worker.error.connect(slot.thread.quit)
        # thread.finished is emitted on the main thread — safe without QueuedConnection
        slot.thread.finished.connect(lambda s=slot: self._on_finished(s))

        slot.thread.start()

        if len(remote_paths) == 1:
            logger.download(f"Download: {os.path.basename(remote_paths[0])}")
        else:
            logger.download(f"Download: {len(remote_paths)} items")
        logger.info(f"Saving to: {local_dir}")

        # Update menu bar activity
        if hasattr(self.view, "menu_bar_service"):
            uploads = (
                1 if self.transfer_controller.is_busy() else 0
            ) + self.transfer_controller.queue_size()
            downloads = len(self._active) + len(self._pending)
            conversions = 0
            if hasattr(self.view, "convert_manager"):
                manager = self.view.convert_manager
                if hasattr(manager, "_is_running") and manager._is_running:
                    conversions = 1
            self.view.menu_bar_service.update_activity(
                uploads=uploads, downloads=downloads, conversions=conversions
            )

    def _on_progress(self, slot: _DownloadSlot, percent: int) -> None:
        """Handle download progress for a specific slot."""
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            idx = slot.queue_index
            if 0 <= idx < len(queue._items):
                item = queue._items[idx]
                item.transferred_bytes = int(item.total_bytes * percent / 100)

    def _on_error(self, slot: _DownloadSlot, error_msg: str) -> None:
        """Store error for a slot (read on main thread when thread finishes)."""
        slot.error_msg = error_msg

    def _on_finished(self, slot: _DownloadSlot) -> None:
        """Handle download thread completion for a slot."""
        error_msg = slot.error_msg

        if error_msg:
            # Retry logic
            if slot.attempts < MAX_DOWNLOAD_RETRIES:
                slot.attempts += 1
                slot.error_msg = None
                logger.warn(
                    f"Download: Retry {slot.attempts}/{MAX_DOWNLOAD_RETRIES}: "
                    f"{error_msg.split(chr(10))[0][:60]}"
                )
                self._cleanup_slot(slot, remove=True)
                # Re-enqueue at front for retry after delay
                QTimer.singleShot(
                    1000,
                    lambda: self._start_download(
                        slot.remote_paths,
                        slot.local_dir,
                        slot.total_bytes,
                        slot.queue_index,
                    ),
                )
                return

            # All retries exhausted
            if hasattr(self.view, "transfer_queue") and slot.queue_index >= 0:
                self.view.transfer_queue.set_failed(slot.queue_index, error_msg)

            if self.settings.config.notify_on_transfer_complete:
                from src.services.notification_service import notify_transfer_failed

                if slot.remote_paths:
                    filename = os.path.basename(slot.remote_paths[0])
                    notify_transfer_failed(filename, error_msg.split("\n")[0][:60])
        else:
            # Success
            if hasattr(self.view, "transfer_queue") and slot.queue_index >= 0:
                self.view.transfer_queue.set_completed(slot.queue_index)

            if slot.remote_paths and slot.local_dir:
                per_file_bytes = (
                    slot.total_bytes // len(slot.remote_paths)
                    if slot.remote_paths
                    else 0
                )
                last_local_path = None
                for remote_path in slot.remote_paths:
                    filename = os.path.basename(remote_path)
                    last_local_path = os.path.join(slot.local_dir, filename)
                    self.transfer_controller.history.add(
                        filename=filename,
                        action="download",
                        source=remote_path,
                        destination=slot.local_dir,
                        size_bytes=per_file_bytes,
                        server_name=self.settings.config.current_server_id,
                    )

                if (
                    self.settings.config.reveal_in_finder_after_download
                    and last_local_path
                ):
                    self._reveal_in_finder(last_local_path)

                if self.settings.config.notify_on_transfer_complete:
                    from src.services.notification_service import (
                        notify_batch_complete,
                        notify_transfer_complete,
                    )

                    use_sound = self.settings.config.notify_sound
                    if len(slot.remote_paths) == 1:
                        notify_transfer_complete(
                            os.path.basename(slot.remote_paths[0]),
                            action="downloaded",
                            sound=use_sound,
                        )
                    else:
                        notify_batch_complete(
                            len(slot.remote_paths),
                            action="downloaded",
                            sound=use_sound,
                        )

        # Update dock badge
        from src.services.notification_service import set_dock_badge

        pending = self.transfer_controller.queue_size()
        active = 1 if self.transfer_controller.is_busy() else 0
        set_dock_badge(pending + active)

        # Update menu bar activity
        if hasattr(self.view, "menu_bar_service"):
            uploads = (
                1 if self.transfer_controller.is_busy() else 0
            ) + self.transfer_controller.queue_size()
            downloads = (
                len(self._active) - 1
            )  # -1 because current slot is about to be removed
            downloads = max(0, downloads) + len(self._pending)
            conversions = 0
            if hasattr(self.view, "convert_manager"):
                manager = self.view.convert_manager
                if hasattr(manager, "_is_running") and manager._is_running:
                    conversions = 1
            self.view.menu_bar_service.update_activity(
                uploads=uploads, downloads=downloads, conversions=conversions
            )

        # Cleanup slot and start next pending
        self._cleanup_slot(slot, remove=True)
        self._process_pending()

    def _process_pending(self) -> None:
        """Start the next pending download if a slot is free."""
        while self._pending and len(self._active) < MAX_PARALLEL_DOWNLOADS:
            remote_paths, local_dir, total_bytes, queue_index = self._pending.pop(0)
            self._start_download(remote_paths, local_dir, total_bytes, queue_index)

    def _cleanup_slot(self, slot: _DownloadSlot, remove: bool = False) -> None:
        """Clean up a download slot's resources."""
        if slot.sftp_session:
            try:
                slot.sftp_session.close()
            except Exception:
                pass
            slot.sftp_session = None

        if slot.thread:
            if slot.thread.isRunning():
                slot.thread.quit()
                slot.thread.wait(2000)
            slot.thread.deleteLater()
            slot.thread = None
        if slot.worker:
            slot.worker.deleteLater()
            slot.worker = None

        if remove and slot in self._active:
            self._active.remove(slot)

    def _reveal_in_finder(self, path: str) -> None:
        """Reveal a file in the system file manager."""
        from src.platform import reveal_in_file_manager

        reveal_in_file_manager(path)
