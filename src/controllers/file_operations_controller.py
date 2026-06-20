"""
File operations controller — handles remote/local CRUD operations.

Handles:
- Delete (single and batch, remote and local)
- Rename (delegates to inline editor)
- Move (single and batch)
- Create folder
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, List

from paramiko import SFTPClient
from PySide6.QtWidgets import QMessageBox

from src.config.settings import Settings
from src.models.errors import ConnectionLostError, FileDeletionError
from src.services.activity_history_service import ActivityHistoryService
from src.utils.constants import (
    DIALOG_CONNECTION_LOST,
    DIALOG_CREATION_FAILED,
    DIALOG_DELETION_FAILED,
    DIALOG_FOLDER_EXISTS,
    DIALOG_MOVE_FAILED,
)
from src.utils.logging_signal import logger

if TYPE_CHECKING:
    from src.views.main_window import MainWindow


class FileOperationsController:
    """
    Handles file system CRUD operations for both remote and local paths.

    Operations: delete, rename, move, create folder.
    All operations record to ActivityHistoryService.
    """

    def __init__(
        self,
        view: "MainWindow",
        settings: Settings,
        history: ActivityHistoryService,
    ) -> None:
        self.view = view
        self.settings = settings
        self.history = history

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete_selected_item(self) -> None:
        """Delete all selected items in the explorer."""
        items = self.view.remote_explorer.tree_widget.selectedItems()
        if not items:
            return

        paths = [
            os.path.join(self.view.remote_explorer.current_path, item.text(0))
            for item in items
        ]

        if len(paths) == 1:
            self.delete_item(paths[0])
        else:
            self._delete_multiple(paths)

    def delete_items(self, paths: list) -> None:
        """Delete multiple items from a list of paths."""
        if not paths:
            return
        if len(paths) == 1:
            self.delete_item(paths[0])
        else:
            self._delete_multiple(paths)

    def _delete_multiple(self, paths: list) -> None:
        """Delete multiple paths with a single confirmation dialog."""
        reply = QMessageBox.question(
            self.view,
            "Delete",
            f"Are you sure you want to delete {len(paths)} items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = []
        failed = []
        for path in paths:
            try:
                is_remote = self.view.remote_explorer.sftp is not None
                if is_remote:
                    self._delete_remote(path)
                else:
                    self._delete_local(path)
                logger.trash(f"Deleted: {os.path.basename(path)}")
                deleted.append(path)
            except ConnectionLostError as e:
                logger.error(f"Delete failed: Connection lost: {e}")
                QMessageBox.warning(
                    self.view,
                    DIALOG_CONNECTION_LOST,
                    f"Connection was lost during deletion.\n\n"
                    f"{len(deleted)} of {len(paths)} items deleted before failure.",
                    QMessageBox.StandardButton.Ok,
                )
                break
            except Exception as e:
                logger.error(f"Delete failed: {os.path.basename(path)}: {e}")
                failed.append(os.path.basename(path))

        for path in deleted:
            self.history.add(
                filename=os.path.basename(path),
                action="delete",
                source=path,
                server_name=self.settings.config.current_server_id,
            )

        if failed:
            logger.warn(f"Delete: {len(failed)} items failed")

        self.view.remote_explorer.refresh()

    def delete_item(self, path: str) -> None:
        """Delete a file or folder with proper error handling."""
        basename = os.path.basename(path)
        is_remote = self.view.remote_explorer.sftp is not None

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
            self.history.add(
                filename=os.path.basename(path),
                action="delete",
                source=path,
                server_name=self.settings.config.current_server_id,
            )
        except ConnectionLostError as e:
            logger.error(f"Delete failed: Connection lost: {e}")
            QMessageBox.warning(
                self.view,
                DIALOG_CONNECTION_LOST,
                f"Connection was lost during deletion.\n\n"
                f"{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
        except FileDeletionError as e:
            logger.error(f"Delete failed: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_DELETION_FAILED,
                f"{e.message}\n\nPath: {e.path}\n\n"
                f"{e.details if e.details else ''}",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_DELETION_FAILED,
                f"An unexpected error occurred:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _is_remote_dir(self, path: str) -> bool:
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            return False
        try:
            from stat import S_ISDIR

            return S_ISDIR(sftp.stat(path).st_mode)
        except Exception:
            return False

    def _delete_remote(self, path: str) -> None:
        """Delete remote file or directory."""
        sftp = self.view.remote_explorer.sftp
        if not sftp:
            raise ConnectionLostError("No connection available")

        try:
            from src.clients.adb_client import ADBClient

            if isinstance(sftp, ADBClient):
                sftp.rmdir(path)
                return

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
                "Unexpected error during remote deletion",
                path=path,
                details=str(e),
            )

    def _delete_remote_dir(self, path: str, sftp: SFTPClient) -> None:
        """Recursively delete remote directory."""
        try:
            for item in sftp.listdir(path):
                item_path = os.path.join(path, os.path.basename(item)).replace(
                    "\\", "/"
                )
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
        """Delete local file or directory."""
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except PermissionError:
            raise FileDeletionError(
                "Permission denied",
                path=path,
                details="You don't have permission to delete this item",
            )
        except FileNotFoundError:
            raise FileDeletionError(
                "File not found",
                path=path,
                details="The file may have already been deleted",
            )
        except Exception as e:
            raise FileDeletionError(
                "Failed to delete local item", path=path, details=str(e)
            )

    # ------------------------------------------------------------------
    # RENAME
    # ------------------------------------------------------------------

    def rename_item(self, old_path: str) -> None:
        """Rename a file or folder using inline editing in the explorer."""
        explorer = self.view.remote_explorer
        basename = os.path.basename(old_path)

        for i in range(explorer.tree_widget.topLevelItemCount()):
            item = explorer.tree_widget.topLevelItem(i)
            if item and item.text(0) == basename:
                explorer._start_inline_rename(item, 0)
                return

    # ------------------------------------------------------------------
    # MOVE
    # ------------------------------------------------------------------

    def move_item(self, src_path: str, dest_path: str) -> None:
        """Move a file or folder to a new location."""
        self._move_single(src_path, dest_path, confirm=True)

    def move_items(self, moves: List[tuple]) -> None:
        """Move multiple files/folders with a single confirmation."""
        if not moves:
            return

        if len(moves) == 1:
            self._move_single(moves[0][0], moves[0][1], confirm=True)
            return

        dest_dir = os.path.dirname(moves[0][1])
        confirm = QMessageBox.question(
            self.view,
            "Move Items",
            f"Move {len(moves)} items to:\n{dest_dir}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        for src_path, dest_path in moves:
            self._move_single(src_path, dest_path, confirm=False)

        self.view.remote_explorer.refresh()

    def _move_single(self, src_path: str, dest_path: str, confirm: bool = True) -> None:
        """Move a single file or folder."""
        is_remote = self.view.remote_explorer.sftp is not None

        if is_remote != dest_path.startswith(self.settings.remote_base_dir):
            logger.error("Cannot move between local and remote filesystems")
            QMessageBox.critical(
                self.view,
                DIALOG_MOVE_FAILED,
                "Cannot move between local and remote filesystems.",
                QMessageBox.StandardButton.Ok,
            )
            return

        if dest_path.startswith(src_path + "/") or src_path == dest_path:
            logger.error("Cannot move item into itself")
            QMessageBox.critical(
                self.view,
                DIALOG_MOVE_FAILED,
                "Cannot move an item into itself or its subdirectories.",
                QMessageBox.StandardButton.Ok,
            )
            return

        if confirm:
            basename = os.path.basename(src_path)
            reply = QMessageBox.question(
                self.view,
                "Move Item",
                f"Move '{basename}' to:\n{dest_path}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            if is_remote:
                sftp = self.view.remote_explorer.sftp
                if not sftp:
                    raise RuntimeError("No connection available")
                sftp.rename(src_path, dest_path)
                if confirm:
                    self.view.remote_explorer.refresh()
            else:
                dest_dir = os.path.dirname(dest_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src_path, dest_path)

            logger.success(
                f"Moved: {os.path.basename(src_path)}: "
                f"To {os.path.basename(dest_path)}"
            )
            self.history.add(
                filename=os.path.basename(src_path),
                action="move",
                source=src_path,
                destination=dest_path,
                server_name=self.settings.config.current_server_id,
            )
        except FileExistsError:
            logger.warn(f"Destination already exists: {dest_path}")
            QMessageBox.warning(
                self.view,
                DIALOG_MOVE_FAILED,
                "An item with that name already exists at the destination.",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Move failed: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_MOVE_FAILED,
                f"Failed to move item:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    # ------------------------------------------------------------------
    # CREATE FOLDER
    # ------------------------------------------------------------------

    def create_folder(self, folder_path: str) -> None:
        """Create a new folder (remote or local)."""
        is_remote = self.view.remote_explorer.sftp is not None

        try:
            if is_remote:
                sftp = self.view.remote_explorer.sftp
                if not sftp:
                    raise RuntimeError("No connection available")
                sftp.mkdir(folder_path)
                self.view.remote_explorer.refresh()
            else:
                os.makedirs(folder_path, exist_ok=True)

            logger.success(f"Folder: {os.path.basename(folder_path)}: Created")
        except FileExistsError:
            logger.warn(f"Folder already exists: {folder_path}")
            QMessageBox.warning(
                self.view,
                DIALOG_FOLDER_EXISTS,
                "A folder with this name already exists.",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            QMessageBox.critical(
                self.view,
                DIALOG_CREATION_FAILED,
                f"Failed to create folder:\n{str(e)}",
                QMessageBox.StandardButton.Ok,
            )
