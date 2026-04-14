from __future__ import annotations

import os

import paramiko

from src.models.errors import (
    ConnectionLostError,
    FileUploadError,
    RemoteDirectoryError,
    TransferVerificationError,
)
from src.services.file_deletion_service import FileDeletionService
from src.utils.logging_signal import logger


class BaseTransferService:
    """
    Base class that performs SFTP-based transfers and ensures remote directories exist.
    Uses an already-connected paramiko.SFTPClient instance.
    """

    def __init__(
        self, sftp: paramiko.SFTPClient, watch_dir: str, pi_root_dir: str
    ) -> None:
        self.sftp: paramiko.SFTPClient = sftp
        self.watch_dir = watch_dir
        self.pi_root_dir = pi_root_dir
        self.file_deletion_service: FileDeletionService = FileDeletionService()

    def ensure_remote_directory(self, remote_dir: str) -> None:
        """
        Ensure remote directory exists. Creates intermediate directories if required.

        Args:
            remote_dir: Absolute remote path (e.g., /mnt/external/TV_shows/show/s01)

        Raises:
            RemoteDirectoryError: If directory creation fails
            ConnectionLostError: If SFTP connection is lost
        """
        # Normalize
        remote_dir = remote_dir.rstrip("/")
        if remote_dir == "":
            return

        parts = remote_dir.split("/")
        # Build path progressively (skip leading empty string from split)
        cur = ""
        for p in parts:
            if p == "":
                continue
            cur += "/" + p
            try:
                self.sftp.stat(cur)
            except IOError:
                # Remote dir doesn't exist -> create
                try:
                    self.sftp.mkdir(cur)
                    # logger.info(f"Transfer: Created remote directory: {cur}")
                except IOError as e:
                    raise RemoteDirectoryError(
                        f"Failed to create remote directory: {cur}", details=str(e)
                    )
                except Exception as e:
                    # Check if connection was lost
                    if "Socket is closed" in str(e) or "not open" in str(e).lower():
                        raise ConnectionLostError(
                            "SFTP connection lost during directory creation",
                            details=str(e),
                        )
                    raise RemoteDirectoryError(
                        f"Unexpected error creating directory: {cur}", details=str(e)
                    )

    def _verify_transfer(self, local_path: str, remote_path: str) -> bool:
        """
        Verify that file was transferred successfully by comparing sizes.

        Args:
            local_path: Local file path
            remote_path: Remote file path

        Returns:
            True if verification succeeds

        Raises:
            TransferVerificationError: If verification fails
        """
        try:
            local_size = os.path.getsize(local_path)
            remote_stat = self.sftp.stat(remote_path)
            remote_size = remote_stat.st_size

            if local_size != remote_size:
                raise TransferVerificationError(
                    f"File size mismatch after transfer",
                    file_path=local_path,
                    details=f"Local: {local_size} bytes, Remote: {remote_size} bytes",
                )

            logger.info(
                f"Transfer: {os.path.basename(local_path)}: Verified"
            )
            return True

        except TransferVerificationError:
            raise
        except Exception as e:
            raise TransferVerificationError(
                f"Failed to verify transfer", file_path=local_path, details=str(e)
            )

    def transfer_folder(
        self, local_folder: str, remote_folder: str, skip_hidden: bool = True
    ) -> None:
        """
        Recursively upload local_folder (all files) into remote_folder preserving
        subpaths relative to local_folder.

        Args:
            local_folder: Local source directory
            remote_folder: Remote destination directory
            skip_hidden: Skip files starting with . or ._

        Raises:
            FileUploadError: If file upload fails
            RemoteDirectoryError: If directory creation fails
            ConnectionLostError: If connection is lost during transfer
        """

        local_folder = os.path.abspath(local_folder)

        def progress_callback(transferred_bytes, total_bytes):
            if total_bytes == 0:
                return

            progress = min(100, max(0, int((transferred_bytes / total_bytes) * 100)))
            if progress % 5 == 0 or progress == 100:
                logger.progress_signal.emit(progress)

        for root, _, files in os.walk(local_folder):
            for f in files:
                if skip_hidden and (f.startswith(".") or f.startswith("._")):
                    continue

                local_file = os.path.join(root, f)
                rel = os.path.relpath(local_file, local_folder)
                remote_file = os.path.join(remote_folder, rel).replace("\\", "/")
                remote_dir = os.path.dirname(remote_file)

                try:
                    self.ensure_remote_directory(remote_dir)
                except (RemoteDirectoryError, ConnectionLostError) as e:
                    logger.error(f"Transfer: Failed to create directory: {e}")
                    logger.progress_signal.emit(0)
                    raise

                try:
                    logger.progress_signal.emit(0)
                    logger.upload(f"Transfer: {os.path.basename(local_file)}: Start")

                    # Upload file
                    self.sftp.put(local_file, remote_file, callback=progress_callback)

                    # Verify transfer
                    try:
                        self._verify_transfer(local_file, remote_file)
                    except TransferVerificationError as e:
                        logger.error(
                            f"Transfer: {os.path.basename(local_file)}: Verification failed"
                        )
                        # Try to remove incomplete remote file
                        try:
                            self.sftp.remove(remote_file)
                            logger.info(
                                f"Transfer: {os.path.basename(remote_file)}: Removed incomplete"
                            )
                        except Exception:
                            pass
                        raise FileUploadError(
                            f"Transfer verification failed",
                            file_path=local_file,
                            details=str(e),
                        )

                    logger.success(
                        f"Transfer: {os.path.basename(local_file)}: Uploaded"
                    )

                    # Only delete after successful verification
                    try:
                        self.file_deletion_service.delete_file(local_file)
                    except Exception as e:
                        logger.warn(
                            f"Transfer: {os.path.basename(local_file)}: Could not delete local copy"
                        )
                        # Don't fail the transfer if deletion fails

                except IOError as e:
                    logger.error(f"Transfer: {os.path.basename(local_file)}: IO error")
                    logger.progress_signal.emit(0)
                    raise FileUploadError(
                        f"Failed to upload file", file_path=local_file, details=str(e)
                    )
                except Exception as e:
                    # Check if connection was lost
                    if "Socket is closed" in str(e) or "not open" in str(e).lower():
                        logger.error(
                            f"Transfer: {os.path.basename(local_file)}: Connection lost"
                        )
                        logger.progress_signal.emit(0)
                        raise ConnectionLostError(
                            "SFTP connection lost during transfer", details=str(e)
                        )
                    logger.error(f"Transfer: {os.path.basename(local_file)}: Failed")
                    logger.progress_signal.emit(0)
                    raise FileUploadError(
                        f"Unexpected error during upload",
                        file_path=local_file,
                        details=str(e),
                    )
