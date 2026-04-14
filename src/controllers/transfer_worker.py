from __future__ import annotations

import os
from typing import List

from paramiko import SFTPClient
from PySide6.QtCore import QObject, Signal

from src.models.errors import (
    ConnectionLostError,
    FileUploadError,
    RemoteDirectoryError,
    TransferVerificationError,
)
from src.utils.helper import format_size
from src.utils.logging_signal import logger


class TransferWorker(QObject):
    """
    Performs manual uploads (drag-and-drop or 'Upload All') on a background thread.

    NOTE: This does NOT delete local files. It's copy semantics.
    """

    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        sftp: SFTPClient,
        local_paths: List[str],
        remote_root: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.sftp = sftp
        self.local_paths = local_paths
        self.remote_root = remote_root

    # ----------------------------
    #  Internal helpers
    # ----------------------------
    def _ensure_remote_directory(self, remote_dir: str) -> None:
        """
        Ensure remote directory exists. Creates intermediate directories as needed.

        Raises:
            RemoteDirectoryError: If directory creation fails
            ConnectionLostError: If connection is lost
        """
        remote_dir = remote_dir.rstrip("/")
        if not remote_dir:
            return

        parts = remote_dir.split("/")
        cur = ""
        for p in parts:
            if not p:
                continue
            cur += "/" + p
            try:
                self.sftp.stat(cur)
            except IOError:
                try:
                    self.sftp.mkdir(cur)
                except IOError as e:
                    raise RemoteDirectoryError(
                        f"Failed to create remote directory: {cur}", details=str(e)
                    )
                except Exception as e:
                    if "Socket is closed" in str(e) or "not open" in str(e).lower():
                        raise ConnectionLostError(
                            "Connection lost during directory creation", details=str(e)
                        )
                    raise

    def _verify_upload(self, local_path: str, remote_path: str) -> bool:
        """
        Verify file was uploaded successfully by comparing sizes.

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
                    f"File size mismatch after upload",
                    file_path=local_path,
                    details=f"Local: {local_size} bytes, Remote: {remote_size} bytes",
                )

            return True
        except TransferVerificationError:
            raise
        except Exception as e:
            raise TransferVerificationError(
                f"Failed to verify upload", file_path=local_path, details=str(e)
            )

    def _upload_file(self, local_path: str, remote_dir: str) -> None:
        """
        Upload a single file with verification.

        Args:
            local_path: Local file path
            remote_dir: Remote directory to upload to

        Raises:
            FileUploadError: If upload fails
            RemoteDirectoryError: If directory creation fails
            ConnectionLostError: If connection is lost
        """
        filename = os.path.basename(local_path)
        remote_file = os.path.join(remote_dir, filename).replace("\\", "/")
        remote_dir = os.path.dirname(remote_file)

        try:
            self._ensure_remote_directory(remote_dir)
        except (RemoteDirectoryError, ConnectionLostError):
            raise

        try:
            size_bytes = os.path.getsize(local_path)
        except OSError as e:
            raise FileUploadError(
                f"Cannot access local file", file_path=local_path, details=str(e)
            )

        # progress callback
        def progress_callback(transferred: int, total: int):
            if total <= 0:
                return
            pct = int(transferred * 100 / total)
            if pct % 5 == 0:  # throttle logs a bit
                logger.progress_signal.emit(pct)

        logger.upload(f"Manual: {filename}: Start upload")
        logger.progress_signal.emit(0)

        try:
            self.sftp.put(local_path, remote_file, callback=progress_callback)

            # Verify upload
            self._verify_upload(local_path, remote_file)

            logger.success(f"Manual: {filename}: Uploaded ({format_size(size_bytes)})")
            logger.progress_signal.emit(100)

        except TransferVerificationError as e:
            logger.error(f"Manual: {filename}: Verification failed")
            # Try to remove incomplete file
            try:
                self.sftp.remove(remote_file)
            except Exception:
                pass
            raise FileUploadError(
                f"Upload verification failed", file_path=local_path, details=str(e)
            )
        except IOError as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during upload", details=str(e)
                )
            raise FileUploadError(
                f"Failed to upload file", file_path=local_path, details=str(e)
            )
        except Exception as e:
            raise FileUploadError(
                f"Unexpected error during upload", file_path=local_path, details=str(e)
            )

    def _upload_folder(self, local_folder: str, remote_root: str) -> None:
        """
        Upload folder recursively.

        Args:
            local_folder: Local folder path
            remote_root: Remote root directory

        Raises:
            FileUploadError: If upload fails
            RemoteDirectoryError: If directory creation fails
            ConnectionLostError: If connection is lost
        """
        local_folder = os.path.abspath(local_folder)
        base_name = os.path.basename(local_folder)
        target_root = os.path.join(remote_root, base_name).replace("\\", "/")

        for root, _, files in os.walk(local_folder):
            for f in files:
                if f.startswith(".") or f.startswith("._"):
                    continue
                local_file = os.path.join(root, f)
                rel = os.path.relpath(local_file, local_folder)
                remote_dir = os.path.dirname(
                    os.path.join(target_root, rel).replace("\\", "/")
                )
                self._upload_file(local_file, remote_dir)

    # ----------------------------
    #  Public entrypoint for QThread
    # ----------------------------
    def run(self) -> None:
        """Execute the transfer operation."""
        try:
            for path in self.local_paths:
                if os.path.isdir(path):
                    self._upload_folder(path, self.remote_root)
                else:
                    self._upload_file(path, self.remote_root)

            self.finished.emit()

        except ConnectionLostError as e:
            msg = f"Connection lost during transfer: {e.message}"
            if e.details:
                msg += f"\nDetails: {e.details}"
            logger.error(msg)
            self.error.emit(msg)
            self.finished.emit()

        except (FileUploadError, RemoteDirectoryError, TransferVerificationError) as e:
            msg = f"{e.message}"
            if e.file_path:
                msg += f"\nFile: {e.file_path}"
            if e.details:
                msg += f"\nDetails: {e.details}"
            logger.error(msg)
            self.error.emit(msg)
            self.finished.emit()

        except Exception as e:
            msg = f"Manual transfer failed: {e}"
            logger.error(msg)
            self.error.emit(msg)
            self.finished.emit()
