from __future__ import annotations

import os

from send2trash import send2trash

from src.models.errors import FileDeletionError
from src.utils.logging_signal import logger


class FileDeletionService:
    """Move files/folders to the trash (cross-platform when using send2trash)."""

    def delete_file(self, file_path: str) -> bool:
        """
        Move file to trash (recoverable deletion).

        Args:
            file_path: Path to file to delete

        Returns:
            True if deleted successfully

        Raises:
            FileDeletionError: If deletion fails
        """
        try:
            if not os.path.exists(file_path):
                logger.warn(f"Deletion: {file_path}: File not found")
                return False

            if not os.path.isfile(file_path):
                logger.warn(f"Deletion: {file_path}: Not a file")
                return False

            send2trash(file_path)
            logger.trash(f"Delete: {os.path.basename(file_path)}")
            return True

        except Exception as e:
            raise FileDeletionError(
                f"Failed to delete file", path=file_path, details=str(e)
            )

    def delete_folder(self, folder_path: str) -> bool:
        """
        Move folder to trash (recoverable deletion).

        Args:
            folder_path: Path to folder to delete

        Returns:
            True if deleted successfully

        Raises:
            FileDeletionError: If deletion fails
        """
        try:
            if not os.path.exists(folder_path):
                logger.warn(f"Delete: {folder_path}: Folder not found")
                return False

            if not os.path.isdir(folder_path):
                logger.warn(f"Delete: {folder_path}: Not a folder")
                return False

            send2trash(folder_path)
            logger.trash(f"Delete: {os.path.basename(folder_path)}")
            return True

        except Exception as e:
            raise FileDeletionError(
                f"Failed to delete folder", path=folder_path, details=str(e)
            )
