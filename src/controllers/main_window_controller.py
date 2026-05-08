from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Optional

from paramiko import SFTPClient
from PySide6.QtWidgets import QDialog, QMessageBox

from src.application.manual_transfer_controller import ManualTransferController
from src.components.settings_window import SettingsWindow
from src.config.settings import Settings
from src.models.errors import (
    AuthenticationError,
    ConnectionLostError,
    FileAccessError,
    FileDeletionError,
    SSHConnectionError,
)
from src.services.connection_manager_service import ConnectionManagerService
from src.utils.logging_signal import logger

if TYPE_CHECKING:
    from src.components.main_window import MainWindow


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
        view,
        connection_manager: ConnectionManagerService,
    ):
        self.view = view
        self.settings: Settings = view.settings
        self.connection_manager = connection_manager

        # Create specialized controllers
        self.manual_transfer = ManualTransferController(
            self.settings, self.connection_manager, parent=view
        )

        # Connect controller signals to UI updates
        self._connect_controller_signals()

        self.selected_item: Optional[str] = None

    def _connect_controller_signals(self) -> None:
        """Connect controller signals to UI updates."""
        # Manual transfer signals
        self.manual_transfer.transfer_started.connect(self._on_manual_transfer_started)
        self.manual_transfer.transfer_completed.connect(
            self._on_manual_transfer_completed
        )
        self.manual_transfer.transfer_failed.connect(self._on_manual_transfer_failed)
        self.manual_transfer.queue_changed.connect(self._on_queue_changed)

    # --------------------------------------------------------------
    #  SIGNAL HANDLERS
    # --------------------------------------------------------------
    def _on_manual_transfer_started(self, path: str) -> None:
        """Handle manual transfer started."""
        logger.info(f"Transfer started: {os.path.basename(path)}")

    def _on_manual_transfer_completed(self, path: str) -> None:
        """Handle manual transfer completed."""
        self.refresh_explorers()

    def _on_manual_transfer_failed(self, path: str, error: str) -> None:
        """Handle manual transfer failed."""
        QMessageBox.warning(
            self.view,
            "Transfer Failed",
            f"Failed to transfer {os.path.basename(path)}\n\n{error}",
            QMessageBox.StandardButton.Ok,
        )

    def _on_queue_changed(self, total: int) -> None:
        """Handle transfer queue size change."""
        if total > 1:
            self.view.progress_bar.setFormat(f"📤 {total} transfers in queue")
        elif total == 1:
            self.view.progress_bar.setFormat("📤 Transferring...")
        else:
            self.view.progress_bar.setFormat("")
            self.view.progress_bar.setValue(0)

    # --------------------------------------------------------------
    #  CONNECTION MANAGEMENT
    # --------------------------------------------------------------
    def connect(self) -> None:
        """Establish connection to remote server with error handling."""
        try:
            if not self.connection_manager.connect():
                self.view.connection_status_label.setText("● Disconnected")
                self.view.connection_status_label.setObjectName(
                    "connection_disconnected"
                )
                self.view.connection_status_label.style().polish(
                    self.view.connection_status_label
                )
                self.view.handle_connection_failure()
                return

            # Connection successful - reset attempt counter
            self.view.connection_attempts = 0

            self.view.connection_status_label.setText(
                f"● Connected to {self.settings.pi_ip}"
            )
            self.view.connection_status_label.setObjectName("connection_connected")
            self.view.connection_status_label.setStyleSheet(
                "color: #4ec9b0; font-weight: 500;"
            )

            # bind sftp to remote explorer
            if self.connection_manager.sftp_client:
                self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
                self.view.remote_explorer.refresh()
                logger.success("Connected to server")

        except AuthenticationError as e:
            self.view.connection_status_label.setText("● Authentication Failed")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            QMessageBox.critical(
                self.view,
                "Authentication Error",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()
        except FileAccessError as e:
            self.view.connection_status_label.setText("● SSH Key Error")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            QMessageBox.critical(
                self.view,
                "SSH Key Error",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()
        except SSHConnectionError as e:
            self.view.connection_status_label.setText("● Connection Failed")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            QMessageBox.warning(
                self.view,
                "Connection Failed",
                f"{e.message}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()
        except Exception as e:
            self.view.connection_status_label.setText("● Error")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.style().polish(
                self.view.connection_status_label
            )
            logger.error(f"Unexpected connection error: {e}")
            QMessageBox.critical(
                self.view,
                "Connection Error",
                f"An unexpected error occurred:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )
            self.view.handle_connection_failure()

    def handle_remote_explorer_failure(self, error_msg: str) -> None:
        """Handle remote explorer errors by attempting to reconnect."""
        logger.error(f"Explorer Error: {error_msg}")
        ok = self.connection_manager.connect()
        if ok and self.connection_manager.sftp_client:
            self.view.remote_explorer.set_sftp(self.connection_manager.sftp_client)
            self.view.remote_explorer.refresh(self.settings.remote_base_dir)
        else:
            self.view.connection_status_label.setText("● Disconnected")
            self.view.connection_status_label.setObjectName("connection_disconnected")
            self.view.connection_status_label.setStyle(
                self.view.connection_status_label.style()
            )
            logger.error("Cannot recover connection.")

    # --------------------------------------------------------------
    #  EXPLORER OPS
    # --------------------------------------------------------------
    def refresh_explorers(self) -> None:
        """Refresh the remote file explorer."""
        if (
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

        logger.success("Explorer refreshed")

    def handle_file_open(self, path: str) -> None:
        """Handle file open event from explorer."""
        logger.info(f"📂 Opened file: {path}")

    def handle_selection_changed(self, path: str) -> None:
        """Handle selection change in explorer."""
        self.selected_item = path or None
        self.view.delete_btn.setEnabled(bool(self.selected_item))

    # --------------------------------------------------------------
    #  DELETE
    # --------------------------------------------------------------
    def delete_selected_item(self) -> None:
        if self.selected_item:
            self.delete_item(self.selected_item)

    def delete_item(self, path: str) -> None:
        """
        Delete a file or folder with proper error handling.

        Args:
            path: Path to file or folder to delete
        """
        basename = os.path.basename(path)
        is_remote = path.startswith(self.settings.remote_base_dir)

        reply = QMessageBox.question(
            self.view,
            "Delete",
            f"Are you sure you want to delete:\n{basename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if is_remote:
                self._delete_remote(path)
                self.view.remote_explorer.refresh()
            else:
                self._delete_local(path)

            logger.trash(f"Deletion: {os.path.basename(path)}: Deleted")

        except ConnectionLostError as e:
            logger.error(f"Delete failed: Connection lost: {e}")
            QMessageBox.warning(
                self.view,
                "Connection Lost",
                f"Connection to Pi was lost during deletion.\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
            # Try to reconnect
            self.connect()
        except FileDeletionError as e:
            logger.error(f"Delete failed: {e}")
            QMessageBox.critical(
                self.view,
                "Deletion Failed",
                f"{e.message}\n\nPath: {e.path}\n\n{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            QMessageBox.critical(
                self.view,
                "Deletion Failed",
                f"An unexpected error occurred:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _is_remote_dir(self, path: str) -> bool:
        if not self.connection_manager.sftp_client:
            return False
        try:
            self.connection_manager.sftp_client.listdir(path)
            return True
        except Exception:
            return False

    def _delete_remote(self, path: str) -> None:
        """
        Delete remote file or directory.

        Args:
            path: Remote path to delete

        Raises:
            ConnectionLostError: If connection is lost
            FileDeletionError: If deletion fails
        """
        sftp = self.connection_manager.sftp_client
        if not sftp:
            raise ConnectionLostError("No SFTP connection available")

        try:
            if self._is_remote_dir(path):
                self._delete_remote_dir(path, sftp)
            else:
                sftp.remove(path)
        except IOError as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during remote deletion", details=str(e)
                )
            raise FileDeletionError(
                "Failed to delete remote item", path=path, details=str(e)
            )
        except Exception as e:
            raise FileDeletionError(
                "Unexpected error during remote deletion", path=path, details=str(e)
            )

    def _delete_remote_dir(self, path: str, sftp: SFTPClient) -> None:
        """
        Recursively delete remote directory.

        Args:
            path: Remote directory path
            sftp: SFTP client

        Raises:
            ConnectionLostError: If connection is lost
            FileDeletionError: If deletion fails
        """
        try:
            for item in sftp.listdir(path):
                item_path = f"{path}/{item}"
                if self._is_remote_dir(item_path):
                    self._delete_remote_dir(item_path, sftp)
                else:
                    sftp.remove(item_path)
            sftp.rmdir(path)
        except IOError as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during directory deletion", details=str(e)
                )
            raise FileDeletionError(
                "Failed to delete remote directory", path=path, details=str(e)
            )

    def _delete_local(self, path: str) -> None:
        """
        Delete local file or directory.

        Args:
            path: Local path to delete

        Raises:
            FileDeletionError: If deletion fails
        """
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except PermissionError as e:
            raise FileDeletionError(
                "Permission denied",
                path=path,
                details="You don't have permission to delete this item",
            )
        except FileNotFoundError as e:
            raise FileDeletionError(
                "File not found",
                path=path,
                details="The file may have already been deleted",
            )
        except Exception as e:
            raise FileDeletionError(
                "Failed to delete local item", path=path, details=str(e)
            )

    # --------------------------------------------------------------
    #  RENAME
    # --------------------------------------------------------------
    def rename_item(self, old_path: str) -> None:
        """
        Rename a file or folder.

        Args:
            old_path: Current path of item to rename
        """
        explorer = self.view.remote_explorer
        new_name = explorer.prompt_rename(old_path)
        if not new_name:
            return

        new_path = os.path.join(os.path.dirname(old_path), new_name)

        try:
            if old_path.startswith(self.settings.remote_base_dir):
                if not self.connection_manager.sftp_client:
                    raise RuntimeError("No SFTP connection")
                self.connection_manager.sftp_client.rename(old_path, new_path)
                self.view.remote_explorer.refresh()
            else:
                os.rename(old_path, new_path)

            logger.success(f"Renamed: {os.path.basename(old_path)}: → {new_name}")
        except Exception as e:
            logger.error(f"Rename failed: {e}")
            QMessageBox.critical(
                self.view,
                "Rename Failed",
                f"Failed to rename item:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    # --------------------------------------------------------------
    #  CREATE FOLDER
    # --------------------------------------------------------------
    def create_folder(self, folder_path: str) -> None:
        """
        Create a new folder.

        Args:
            folder_path: Full path to the new folder to create
        """
        is_remote = folder_path.startswith(self.settings.remote_base_dir)

        try:
            if is_remote:
                if not self.connection_manager.sftp_client:
                    raise RuntimeError("No SFTP connection")
                self.connection_manager.sftp_client.mkdir(folder_path)
                self.view.remote_explorer.refresh()
            else:
                os.makedirs(folder_path, exist_ok=True)

            logger.success(f"Folder: {os.path.basename(folder_path)}: Created")
        except FileExistsError:
            logger.warn(f"Folder already exists: {folder_path}")
            QMessageBox.warning(
                self.view,
                "Folder Exists",
                f"A folder with this name already exists.",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            QMessageBox.critical(
                self.view,
                "Creation Failed",
                f"Failed to create folder:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    # --------------------------------------------------------------
    #  MOVE ITEM
    # --------------------------------------------------------------
    def move_item(self, src_path: str, dest_path: str) -> None:
        """
        Move a file or folder to a new location.

        Args:
            src_path: Current path of item to move
            dest_path: Destination path for the item
        """
        is_remote = src_path.startswith(self.settings.remote_base_dir)

        # Validate that source and destination are in the same filesystem
        if is_remote != dest_path.startswith(self.settings.remote_base_dir):
            logger.error("Cannot move between local and remote filesystems")
            QMessageBox.critical(
                self.view,
                "Move Failed",
                "Cannot move between local and remote filesystems.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Prevent moving into itself or its subdirectories
        if dest_path.startswith(src_path + os.sep) or src_path == dest_path:
            logger.error("Cannot move item into itself")
            QMessageBox.critical(
                self.view,
                "Move Failed",
                "Cannot move an item into itself or its subdirectories.",
                QMessageBox.StandardButton.Ok,
            )
            return

        basename = os.path.basename(src_path)
        confirm = QMessageBox.question(
            self.view,
            "Move Item",
            f"Move '{basename}' to:\n{dest_path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            if is_remote:
                if not self.connection_manager.sftp_client:
                    raise RuntimeError("No SFTP connection")
                self.connection_manager.sftp_client.rename(src_path, dest_path)
                self.view.remote_explorer.refresh()
            else:
                # Create destination directory if it doesn't exist
                dest_dir = os.path.dirname(dest_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src_path, dest_path)

            logger.success(
                f"Moved: {os.path.basename(src_path)}: To {os.path.basename(dest_path)}"
            )
        except FileExistsError:
            logger.warn(f"Destination already exists: {dest_path}")
            QMessageBox.warning(
                self.view,
                "Move Failed",
                f"An item with that name already exists at the destination.",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Move failed: {e}")
            QMessageBox.critical(
                self.view,
                "Move Failed",
                f"Failed to move item:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    # --------------------------------------------------------------
    #  SETTINGS
    # --------------------------------------------------------------
    def open_settings(self):
        settings_window = SettingsWindow(self.settings)
        if settings_window.exec() == QDialog.DialogCode.Accepted:
            # Reload settings since the singleton was reset during save
            self.settings = Settings()
            self.view.settings = self.settings
            self.refresh_explorers()

    # --------------------------------------------------------------
    #  SHUTDOWN
    # --------------------------------------------------------------
    def shutdown(self) -> None:
        """Clean shutdown of connections."""
        try:
            self.connection_manager.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
