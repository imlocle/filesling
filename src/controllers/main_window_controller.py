from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from src.config.settings import Settings
from src.controllers.transfer_controller import ManualTransferController
from src.services.connection_manager_service import ConnectionManagerService
from src.services.sleep_inhibitor_service import SleepInhibitorService
from src.utils.theme import apply_theme
from src.views.settings_window import SettingsWindow
from src.widgets.transfer_queue_widget import TransferStatus

if TYPE_CHECKING:
    from src.views.main_window import MainWindow  # noqa: F401


class MainWindowController:
    """
    Controller for MainWindow.

    Handles:
    - Connection management
    - Manual transfers (via ManualTransferController)
    - UI coordination
    - Settings management
    - File operations (delete, rename, move, create folder)
    """

    def __init__(
        self,
        view: "MainWindow",
        connection_manager: ConnectionManagerService,
    ) -> None:
        self.view = view
        self.settings: Settings = view.settings
        self.connection_manager = connection_manager

        # Create specialized controllers
        self.manual_transfer = ManualTransferController(
            self.settings, self.connection_manager, parent=view
        )

        from src.controllers.connection_controller import ConnectionController
        from src.controllers.download_controller import DownloadController
        from src.controllers.file_operations_controller import FileOperationsController

        self.connection_ctrl = ConnectionController(
            view=view,
            settings=self.settings,
            connection_manager=self.connection_manager,
            parent=view,
        )

        self.download_ctrl = DownloadController(
            view=view,
            settings=self.settings,
            connection_manager=self.connection_manager,
            transfer_controller=self.manual_transfer,
        )

        self.file_ops = FileOperationsController(
            view=view,
            settings=self.settings,
            history=self.manual_transfer.history,
        )

        self._queue_signals_connected = False

        # Sleep inhibitor — prevents macOS idle sleep during active work
        self._sleep_inhibitor = SleepInhibitorService()

        # Connect controller signals to UI updates
        self._connect_controller_signals()

        self.selected_item: Optional[str] = None
        self._current_queue_index: int = -1

    def _connect_controller_signals(self) -> None:
        """Connect controller signals to UI updates."""
        # Manual transfer signals
        self.manual_transfer.transfer_started.connect(self._on_manual_transfer_started)
        self.manual_transfer.transfer_completed.connect(
            self._on_manual_transfer_completed
        )
        self.manual_transfer.transfer_failed.connect(self._on_manual_transfer_failed)
        self.manual_transfer.transfer_progress.connect(self._on_transfer_progress)
        self.manual_transfer.transfer_method_changed.connect(
            self._on_transfer_method_changed
        )
        self.manual_transfer.queue_changed.connect(self._on_queue_changed)

        # Queue widget signals
        self._connect_queue_signals()

    def _connect_queue_signals(self) -> None:
        """Connect transfer queue UI signals once the widget exists."""
        if self._queue_signals_connected or not hasattr(self.view, "transfer_queue"):
            return
        self.view.transfer_queue.cancel_transfer.connect(self._on_cancel_transfer)
        self.view.transfer_queue.cancel_active.connect(
            self.manual_transfer.cancel_active_transfer
        )
        self.view.transfer_queue.indices_changed.connect(self._on_queue_indices_changed)
        self._queue_signals_connected = True

    def initialize_transfer_queue(self) -> None:
        """Connect queue UI controls and restore persisted uploads."""
        if not hasattr(self.view, "transfer_queue"):
            return

        queue = self.view.transfer_queue
        self._connect_queue_signals()

        restored = self.manual_transfer.restore_persisted_queue()
        for transfer in restored:
            queue.add_transfer(
                transfer.display_name,
                transfer.total_bytes,
                transfer.remote_destination,
            )

        if restored:
            QTimer.singleShot(500, self.manual_transfer.start_processing)

    # --------------------------------------------------------------
    #  SIGNAL HANDLERS
    # --------------------------------------------------------------
    def _on_manual_transfer_started(self, path: str) -> None:
        """Handle manual transfer started — mark current item as in-progress."""
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue

            # If the previous item hasn't been marked complete yet (race condition),
            # force-complete it now before starting the next one.
            if self._current_queue_index >= 0:
                if self._current_queue_index < len(queue._items):
                    prev = queue._items[self._current_queue_index]
                    if prev.status == TransferStatus.IN_PROGRESS:
                        queue.set_completed(self._current_queue_index)
                self._current_queue_index = -1

            # Find the first pending item and mark it as in-progress.
            for i, item in enumerate(queue._items):
                if item.status == TransferStatus.PENDING:
                    queue.set_in_progress(i)
                    self._current_queue_index = i
                    break

        # Update dock badge
        self._update_dock_badge()
        self._update_sleep_inhibitor()

    def _on_manual_transfer_completed(self, path: str) -> None:
        """Handle manual transfer completed — mark item as done."""
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            # Find the in-progress item and mark it complete.
            # Don't rely solely on _current_queue_index — it can be stale.
            if self._current_queue_index >= 0:
                if self._current_queue_index < len(queue._items):
                    queue.set_completed(self._current_queue_index)
            else:
                # Fallback: find any in-progress item and complete it
                for i, item in enumerate(queue._items):
                    if item.status == TransferStatus.IN_PROGRESS:
                        queue.set_completed(i)
                        break
            self._current_queue_index = -1
        self.refresh_explorers()

        # Update dock badge
        self._update_dock_badge()
        self._update_sleep_inhibitor()

        # Send macOS notification
        if self.settings.config.notify_on_transfer_complete:
            from src.services.notification_service import notify_transfer_complete

            filename = os.path.basename(path)
            notify_transfer_complete(
                filename,
                action="uploaded",
                sound=self.settings.config.notify_sound,
            )

    def _on_manual_transfer_failed(self, path: str, error: str) -> None:
        """Handle manual transfer failed — mark item as failed."""
        if hasattr(self.view, "transfer_queue"):
            queue = self.view.transfer_queue
            short_error = error.split("\n")[0][:80]
            if self._current_queue_index >= 0:
                if self._current_queue_index < len(queue._items):
                    queue.set_failed(self._current_queue_index, short_error)
            else:
                # Fallback: find any in-progress item and fail it
                for i, item in enumerate(queue._items):
                    if item.status == TransferStatus.IN_PROGRESS:
                        queue.set_failed(i, short_error)
                        break
            self._current_queue_index = -1

        # Update dock badge
        self._update_dock_badge()
        self._update_sleep_inhibitor()

        # Send macOS notification
        if self.settings.config.notify_on_transfer_complete:
            from src.services.notification_service import notify_transfer_failed

            filename = os.path.basename(path)
            notify_transfer_failed(filename, error.split("\n")[0][:60])

    def _on_transfer_progress(self, percentage: int) -> None:
        """Handle transfer progress update."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            # Convert percentage back to bytes for the queue widget
            queue = self.view.transfer_queue
            if self._current_queue_index < len(queue._items):
                item = queue._items[self._current_queue_index]
                transferred = int(item.total_bytes * percentage / 100)
                queue.update_progress(self._current_queue_index, transferred, 0)

    def _on_transfer_method_changed(self, method: str) -> None:
        """Handle transfer method change (e.g. rsync fallback to SFTP)."""
        if hasattr(self.view, "transfer_queue") and self._current_queue_index >= 0:
            queue = self.view.transfer_queue
            if self._current_queue_index < len(queue._items):
                queue._items[self._current_queue_index].transfer_method = method
                queue._item_widgets[self._current_queue_index]._update_method_dot()

    def _on_queue_changed(self, total: int) -> None:
        """Handle transfer queue size change — update dock badge."""
        self._update_dock_badge()

    def _on_cancel_transfer(self, pending_index: int) -> None:
        """Handle cancel request from queue widget."""
        self.manual_transfer.cancel_queued_item(pending_index)

    def _on_queue_indices_changed(self) -> None:
        """Re-sync _current_queue_index after items were removed from the queue."""
        if not hasattr(self.view, "transfer_queue"):
            return
        queue = self.view.transfer_queue
        # Find the in-progress item's new index
        self._current_queue_index = -1
        for i, item in enumerate(queue._items):
            if item.status == TransferStatus.IN_PROGRESS:
                self._current_queue_index = i
                break

    def _update_dock_badge(self) -> None:
        """Update the Dock icon badge with pending transfer count."""
        from src.services.notification_service import set_dock_badge

        pending = self.manual_transfer.queue_size()
        active = 1 if self.manual_transfer.is_busy() else 0
        set_dock_badge(pending + active)

    def _update_sleep_inhibitor(self) -> None:
        """Acquire or release sleep inhibition based on active work."""
        if not self.settings.config.prevent_sleep_during_transfer:
            self._sleep_inhibitor.release()
            return

        has_active_work = self.manual_transfer.is_busy() or self.download_ctrl.is_active
        if has_active_work:
            self._sleep_inhibitor.acquire()
        else:
            self._sleep_inhibitor.release()

    # --------------------------------------------------------------
    #  CONNECTION (delegated to ConnectionController)
    # --------------------------------------------------------------
    def connect(self) -> None:
        """Establish connection to remote server."""
        self.connection_ctrl.connect()

    def handle_remote_explorer_failure(self, error_msg: str) -> None:
        """Handle remote explorer errors by attempting to reconnect."""
        self.connection_ctrl.handle_explorer_failure(error_msg)

    # --------------------------------------------------------------
    #  EXPLORER OPS
    # --------------------------------------------------------------
    def refresh_explorers(self) -> None:
        """Refresh the remote file explorer."""
        # If explorer has an active connection (SSH or ADB), just refresh
        if self.view.remote_explorer.sftp:
            self.view.remote_explorer.refresh()
        elif (
            self.connection_manager.is_connected()
            and self.connection_manager.sftp_client
        ):
            self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
            self.view.remote_explorer.refresh()
        else:
            # Don't spam errors; just reflect disconnected state
            self.view.connection_status_label.setText("● Disconnected")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.setStyle(
                self.view.connection_status_label.style()
            )

    def handle_selection_changed(self, path: str) -> None:
        """Handle selection change in explorer."""
        self.selected_item = path or None
        self.view.delete_btn.setEnabled(bool(self.selected_item))

    # --------------------------------------------------------------
    #  FILE OPERATIONS (delegated to FileOperationsController)
    # --------------------------------------------------------------
    def delete_selected_item(self) -> None:
        self.file_ops.delete_selected_item()

    def delete_items(self, paths: list) -> None:
        self.file_ops.delete_items(paths)

    def delete_item(self, path: str) -> None:
        self.file_ops.delete_item(path)

    def rename_item(self, old_path: str) -> None:
        self.file_ops.rename_item(old_path)

    def create_folder(self, folder_path: str) -> None:
        self.file_ops.create_folder(folder_path)

    def move_item(self, src_path: str, dest_path: str) -> None:
        self.file_ops.move_item(src_path, dest_path)

    def move_items(self, moves: List[tuple]) -> None:
        self.file_ops.move_items(moves)

    # --------------------------------------------------------------
    #  DOWNLOAD (delegated to DownloadController)
    # --------------------------------------------------------------
    def download_item(self, remote_path: str) -> None:
        self.download_ctrl.download_item(remote_path)

    def download_items(self, remote_paths: List[str]) -> None:
        self.download_ctrl.download_items(remote_paths)

    # --------------------------------------------------------------
    #  SETTINGS
    # --------------------------------------------------------------
    def open_settings(self) -> None:
        settings_window = SettingsWindow(self.settings)
        if settings_window.exec() == QDialog.DialogCode.Accepted:
            # Config is reloaded in-place by SettingsWindow — all references
            # already point to the updated singleton. Just apply theme and refresh.
            app = QApplication.instance()
            if app:
                apply_theme(app, self.settings.config.theme_mode)  # type: ignore
            self.refresh_explorers()

    # --------------------------------------------------------------
    #  SHUTDOWN
    # --------------------------------------------------------------
    def shutdown(self) -> None:
        """Clean shutdown of connections."""
        self._sleep_inhibitor.release()
        self.connection_ctrl.shutdown()
