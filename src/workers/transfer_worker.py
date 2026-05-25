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
from src.utils.logging_signal import logger


class TransferWorker(QObject):
    """
    Performs manual uploads (drag-and-drop or 'Upload All') on a background thread.

    NOTE: This does NOT delete local files. It's copy semantics.
    """

    finished = Signal()
    error = Signal(str)
    progress = Signal(int)  # percentage 0-100

    def __init__(
        self,
        sftp: SFTPClient,
        local_paths: List[str],
        remote_root: str,
        total_bytes: int = 0,
        compress_folders: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.sftp = sftp
        self.local_paths = local_paths
        self.remote_root = remote_root
        self._total_bytes = total_bytes
        self._cumulative_bytes = 0
        self._compress_folders = compress_folders

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
        Skipped for ADB connections (adb push handles its own verification).

        Args:
            local_path: Local file path
            remote_path: Remote file path

        Returns:
            True if verification succeeds

        Raises:
            TransferVerificationError: If verification fails
        """
        # Skip verification for ADB — adb push validates internally
        # and stat() may return 0 before filesystem syncs
        from src.services.adb_client import ADBClient

        if isinstance(self.sftp, ADBClient):
            return True

        try:
            local_size = os.path.getsize(local_path)
            remote_stat = self.sftp.stat(remote_path)
            remote_size = remote_stat.st_size

            if local_size != remote_size:
                raise TransferVerificationError(
                    "File size mismatch after upload",
                    file_path=local_path,
                    details=f"Local: {local_size} bytes, Remote: {remote_size} bytes",
                )

            return True
        except TransferVerificationError:
            raise
        except Exception as e:
            raise TransferVerificationError(
                "Failed to verify upload", file_path=local_path, details=str(e)
            )

    def _upload_file(self, local_path: str, remote_dir: str) -> None:
        """
        Upload a single file with verification and resume support.

        If a partial file exists on the remote with the same size, skip it.
        This enables effective resume after interrupted transfers.

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
                "Cannot access local file", file_path=local_path, details=str(e)
            )

        # Resume support: check if file already exists with correct size
        try:
            remote_stat = self.sftp.stat(remote_file)
            if remote_stat.st_size == size_bytes:
                # File already fully uploaded — skip
                self._cumulative_bytes += size_bytes
                if self._total_bytes > 0:
                    overall_pct = int(self._cumulative_bytes * 100 / self._total_bytes)
                    self.progress.emit(min(overall_pct, 100))
                logger.info(f"Skipped (already uploaded): {filename}")
                return
        except (IOError, OSError):
            pass  # File doesn't exist — proceed with upload

        # progress callback
        def progress_callback(transferred: int, total: int):
            if total <= 0:
                return
            pct = int(transferred * 100 / total)
            if pct % 5 == 0:
                logger.progress_signal.emit(pct)
            # Emit overall percentage
            if self._total_bytes > 0:
                overall_pct = int(
                    (self._cumulative_bytes + transferred) * 100 / self._total_bytes
                )
                self.progress.emit(min(overall_pct, 100))

        logger.progress_signal.emit(0)

        try:
            self.sftp.put(local_path, remote_file, callback=progress_callback)

            # Verify upload
            self._verify_upload(local_path, remote_file)

            # Add this file's size to cumulative total
            self._cumulative_bytes += size_bytes

            logger.progress_signal.emit(100)

        except TransferVerificationError as e:
            logger.error(f"Manual: {filename}: Verification failed")
            # Try to remove incomplete file
            try:
                self.sftp.remove(remote_file)
            except Exception:
                pass
            raise FileUploadError(
                "Upload verification failed", file_path=local_path, details=str(e)
            )
        except IOError as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError(
                    "Connection lost during upload", details=str(e)
                )
            raise FileUploadError(
                "Failed to upload file", file_path=local_path, details=str(e)
            )
        except Exception as e:
            raise FileUploadError(
                "Unexpected error during upload", file_path=local_path, details=str(e)
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

    def _upload_folder_compressed(self, local_folder: str, remote_root: str) -> None:
        """
        Compress a folder to zip, upload the zip, then clean up.

        Args:
            local_folder: Local folder path
            remote_root: Remote root directory
        """
        import shutil
        import tempfile

        folder_name = os.path.basename(local_folder)
        temp_dir = tempfile.mkdtemp(prefix="filesling_zip_")
        zip_path = os.path.join(temp_dir, folder_name)

        try:
            # Create zip archive
            archive_path = shutil.make_archive(zip_path, "zip", local_folder)
            # Update total bytes to reflect zip size
            zip_size = os.path.getsize(archive_path)
            self._total_bytes = zip_size

            # Upload the zip file
            self._upload_file(archive_path, remote_root)

        finally:
            # Clean up temp zip
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    # ----------------------------
    #  Public entrypoint for QThread
    # ----------------------------
    def run(self) -> None:
        """Execute the transfer operation."""
        try:
            for path in self.local_paths:
                if os.path.isdir(path):
                    if self._compress_folders:
                        self._upload_folder_compressed(path, self.remote_root)
                    else:
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
