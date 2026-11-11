from __future__ import annotations

import hashlib
import os
import posixpath
import shlex
import tempfile
import uuid
from typing import BinaryIO, List, Optional

from paramiko import SFTPClient
from PySide6.QtCore import QObject, Signal

from src.clients.ssh_command_client import open_ssh_session
from src.models.errors import (
    ConnectionLostError,
    FileUploadError,
    RemoteDirectoryError,
    TransferVerificationError,
)
from src.services.rclone_service import RcloneConfig, RcloneTransfer, is_rclone_available
from src.services.rsync_service import RsyncConfig, RsyncTransfer, is_rsync_available
from src.utils.file_size import get_local_path_size
from src.utils.logging_signal import logger


class TransferWorker(QObject):
    """
    Performs manual uploads (drag-and-drop or 'Upload All') on a background thread.

    NOTE: This does NOT delete local files. It's copy semantics.

    When an `rsync_config` is provided and rsync is available, uploads use the
    rsync fast path (delta transfers, compression, resume). Otherwise they fall
    back to SFTP via the provided client.
    """

    finished = Signal()
    error = Signal(str)
    progress = Signal(int)  # percentage 0-100
    method_changed = Signal(str)  # emitted when transfer method changes (e.g. fallback)

    def __init__(
        self,
        sftp: SFTPClient,
        local_paths: List[str],
        remote_root: str,
        total_bytes: int = 0,
        compress_folders: bool = False,
        rclone_config: Optional[RcloneConfig] = None,
        rsync_config: Optional[RsyncConfig] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.sftp = sftp
        self.local_paths = local_paths
        self.remote_root = remote_root
        self._total_bytes = total_bytes
        self._cumulative_bytes = 0
        self._compress_folders = compress_folders
        self._rclone_config = rclone_config
        self._rsync_config = rsync_config
        self._active_rclone: Optional[RcloneTransfer] = None
        self._active_rsync: Optional[RsyncTransfer] = None

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

    @staticmethod
    def _hash_stream(stream: BinaryIO) -> str:
        digest = hashlib.sha256()
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()

    def _remote_sha256(self, remote_path: str) -> str:
        """Hash a remote file without loading it all into memory."""
        # Ask SSH servers and Android devices to hash the file in place. This
        # avoids downloading large media files a second time just for verification.
        try:
            if callable(getattr(self.sftp, "get_channel", None)):
                channel = self.sftp.get_channel()
                transport = channel.get_transport() if channel else None
                if transport and transport.is_active():
                    for command in (
                        f"sha256sum -- {shlex.quote(remote_path)}",
                        f"shasum -a 256 -- {shlex.quote(remote_path)}",
                    ):
                        with open_ssh_session(transport, command) as session:
                            output = session.makefile("r").read().strip()
                            exit_code = session.recv_exit_status()
                        if exit_code == 0:
                            digest = output.split(maxsplit=1)[0].lower()
                            if len(digest) == 64 and all(
                                char in "0123456789abcdef" for char in digest
                            ):
                                return digest

            from src.clients.adb_client import ADBClient

            if isinstance(self.sftp, ADBClient):
                return self.sftp.sha256(remote_path)
        except Exception:
            # Fall back to reading the file through its native client API.
            pass

        remote_open = getattr(self.sftp, "open", None)
        remote_mode = "rb"
        if not callable(remote_open):
            afc = getattr(self.sftp, "_afc", None)
            remote_open = getattr(afc, "open", None)
            remote_mode = "r"

        if callable(remote_open):
            with remote_open(remote_path, remote_mode) as remote_file:
                return self._hash_stream(remote_file)

        # ADB exposes pull/get but no file stream API, so stage the read locally.
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                prefix="filesling_verify_", delete=False
            ) as f:
                temp_path = f.name
            self.sftp.get(remote_path, temp_path)
            with open(temp_path, "rb") as remote_file:
                return self._hash_stream(remote_file)
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _verify_upload(self, local_path: str, remote_path: str) -> bool:
        """
        Verify an upload by comparing SHA-256 content hashes.

        Args:
            local_path: Local file path
            remote_path: Remote file path

        Returns:
            True if verification succeeds

        Raises:
            TransferVerificationError: If verification fails
        """
        try:
            with open(local_path, "rb") as local_file:
                local_hash = self._hash_stream(local_file)
            remote_hash = self._remote_sha256(remote_path)
            if local_hash != remote_hash:
                raise TransferVerificationError(
                    "File contents differ after upload",
                    file_path=local_path,
                    details=f"Local SHA-256: {local_hash}, Remote SHA-256: {remote_hash}",
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

        Upload to a temporary remote file, verify its contents, then replace the
        destination. A same-sized destination is skipped only when its checksum
        matches the local file.

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
        target_dir = os.path.dirname(remote_file)

        try:
            self._ensure_remote_directory(target_dir)
        except (RemoteDirectoryError, ConnectionLostError):
            raise

        try:
            size_bytes = os.path.getsize(local_path)
        except OSError as e:
            raise FileUploadError(
                "Cannot access local file", file_path=local_path, details=str(e)
            )

        # Skip only an exact content match, never a same-size file alone.
        try:
            self.sftp.stat(remote_file)
            if self._verify_upload(local_path, remote_file):
                self._cumulative_bytes += size_bytes
                if self._total_bytes > 0:
                    overall_pct = int(self._cumulative_bytes * 100 / self._total_bytes)
                    self.progress.emit(min(overall_pct, 100))
                logger.info(f"Skipped (already uploaded): {filename}")
                return
        except (IOError, OSError, TransferVerificationError):
            pass  # File doesn't exist: proceed with upload

        temp_file = os.path.join(
            target_dir,
            f".filesling-{uuid.uuid4().hex}.part",
        ).replace("\\", "/")

        # progress callback
        def progress_callback(transferred: int, total: int) -> None:
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
            self.sftp.put(local_path, temp_file, callback=progress_callback)

            # Verify upload
            self._verify_upload(local_path, temp_file)

            # Install only after verification. Keep the prior destination as a
            # rollback file on clients without the SFTP posix-rename extension.
            try:
                self.sftp.stat(remote_file)
                target_exists = True
            except (IOError, OSError):
                target_exists = False

            committed = False
            if target_exists and callable(getattr(self.sftp, "posix_rename", None)):
                try:
                    self.sftp.posix_rename(temp_file, remote_file)
                    committed = True
                except Exception as rename_error:
                    logger.info(
                        f"Transfer: Atomic SFTP replace unavailable for {filename}: "
                        f"{rename_error}"
                    )

            if target_exists and not committed:
                backup_file = os.path.join(
                    target_dir, f".filesling-{uuid.uuid4().hex}.backup"
                ).replace("\\", "/")
                self.sftp.rename(remote_file, backup_file)
                try:
                    self.sftp.rename(temp_file, remote_file)
                except Exception:
                    try:
                        self.sftp.rename(backup_file, remote_file)
                    except Exception as rollback_error:
                        logger.error(
                            f"Transfer: Could not restore previous {filename}: "
                            f"{rollback_error}"
                        )
                    raise
                try:
                    self.sftp.remove(backup_file)
                except Exception as cleanup_error:
                    logger.warn(
                        f"Transfer: Replaced {filename}, but could not remove "
                        f"its backup: {cleanup_error}"
                    )
            elif not target_exists:
                self.sftp.rename(temp_file, remote_file)

            # Add this file's size to cumulative total
            self._cumulative_bytes += size_bytes

            logger.progress_signal.emit(100)

        except TransferVerificationError as e:
            logger.error(f"Manual: {filename}: Verification failed")
            # Try to remove incomplete file
            try:
                self.sftp.remove(temp_file)
            except Exception:
                pass
            raise FileUploadError(
                "Upload verification failed", file_path=local_path, details=str(e)
            )
        except IOError as e:
            try:
                self.sftp.remove(temp_file)
            except Exception:
                pass
            error_str = str(e).lower()
            if "socket is closed" in error_str or "not open" in error_str:
                raise ConnectionLostError(
                    "Connection lost during upload", details=str(e)
                )
            if "no space" in error_str or "disk full" in error_str:
                raise FileUploadError(
                    "No space left on remote device",
                    file_path=local_path,
                    details="The remote filesystem is full. Free up space and try again.",
                )
            raise FileUploadError(
                "Failed to upload file", file_path=local_path, details=str(e)
            )
        except Exception as e:
            try:
                self.sftp.remove(temp_file)
            except Exception:
                pass
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
            # Use local variable for zip progress: don't overwrite _total_bytes
            # which tracks the overall transfer across all items.
            zip_size = os.path.getsize(archive_path)
            original_total = self._total_bytes
            if self._total_bytes <= 0:
                self._total_bytes = zip_size

            # Upload the zip file
            self._upload_file(archive_path, remote_root)

            # Restore original total if we had to set it temporarily
            if original_total > 0:
                self._total_bytes = original_total

        finally:
            # Clean up temp zip
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    def _upload_via_rsync(self) -> None:
        """
        Upload all paths in a single rsync invocation.

        rsync handles recursion, delta transfers, compression, and resume on
        its own, so we hand it every path at once and let it do the work.

        Raises:
            RuntimeError: If the rsync transfer fails (caller falls back/handles)
        """
        assert self._rsync_config is not None

        # Ensure the remote destination exists first. rsync can create the
        # final directory but not always intermediate ones, so create it via
        # SFTP which we already have a session for.
        try:
            self._ensure_remote_directory(self.remote_root)
        except (RemoteDirectoryError, ConnectionLostError):
            raise

        def progress_cb(pct: int) -> None:
            self.progress.emit(min(pct, 100))

        transfer = RsyncTransfer(
            config=self._rsync_config,
            local_paths=self.local_paths,
            remote_dir=self.remote_root,
        )
        self._active_rsync = transfer
        transfer.run(progress_cb=progress_cb)

    def _verify_rclone_upload(self, local_path: str, remote_path: str) -> None:
        """Verify rclone output through the existing SHA-256 upload checks."""
        if os.path.isdir(local_path):
            for root, _, filenames in os.walk(local_path):
                relative_root = os.path.relpath(root, local_path)
                remote_dir = (
                    remote_path
                    if relative_root == "."
                    else posixpath.join(remote_path, relative_root.replace("\\", "/"))
                )
                for filename in filenames:
                    source = os.path.join(root, filename)
                    destination = posixpath.join(remote_dir, filename)
                    self._verify_upload(source, destination)
            return

        self._verify_upload(local_path, remote_path)

    def _upload_via_rclone(self) -> None:
        """Upload each selected path with rclone, then verify every file."""
        assert self._rclone_config is not None
        total_bytes = self._total_bytes or sum(
            get_local_path_size(path, include_hidden=True) for path in self.local_paths
        )

        for local_path in self.local_paths:
            filename = os.path.basename(local_path.rstrip("/\\"))
            remote_path = posixpath.join(self.remote_root, filename)
            item_bytes = get_local_path_size(local_path, include_hidden=True)
            transfer = RcloneTransfer(self._rclone_config)
            self._active_rclone = transfer

            def progress_callback(percent: int) -> None:
                if total_bytes > 0:
                    completed = self._cumulative_bytes + int(item_bytes * percent / 100)
                    self.progress.emit(min(int(completed * 100 / total_bytes), 100))
                else:
                    self.progress.emit(percent)

            transfer.run(local_path, remote_path, progress_callback)
            self._verify_rclone_upload(local_path, remote_path)
            self._cumulative_bytes += item_bytes
            self._active_rclone = None

        self.progress.emit(100)

    # ----------------------------
    #  Public entrypoint for QThread
    # ----------------------------
    def run(self) -> None:
        """Execute the transfer operation."""
        use_rclone = (
            self._rclone_config is not None
            and not self._compress_folders
            and is_rclone_available()
        )
        if use_rclone:
            try:
                self._upload_via_rclone()
                self.finished.emit()
                return
            except Exception as error:
                if self._active_rclone and self._active_rclone.cancelled:
                    self.error.emit("Transfer cancelled by user")
                    return
                logger.warn(f"rclone failed, falling back to rsync or SFTP: {error}")
                self._active_rclone = None
                self._cumulative_bytes = 0
                self.method_changed.emit(
                    "rsync" if self._rsync_config and is_rsync_available() else "sftp"
                )

        # Fast path: rsync for SSH key-based connections when available.
        # Compression-to-zip is a separate, mutually exclusive feature, so we
        # only use rsync when the user hasn't asked to zip folders first.
        use_rsync = (
            self._rsync_config is not None
            and not self._compress_folders
            and is_rsync_available()
        )

        if use_rsync:
            try:
                self._upload_via_rsync()
                self.finished.emit()
                return
            except Exception as e:
                # rsync failed: log and fall back to SFTP rather than failing
                logger.warn(f"rsync failed, falling back to SFTP: {e}")
                self._cumulative_bytes = 0
                self.method_changed.emit("sftp")
        elif (
            self._rsync_config is not None
            and self._compress_folders
            and is_rsync_available()
        ):
            # Inform user that compress_folders disables rsync fast path
            logger.info(
                "Transfer: Using SFTP (folder compression enabled, rsync skipped)"
            )
            self.method_changed.emit("sftp")

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

        except (FileUploadError, RemoteDirectoryError, TransferVerificationError) as e:
            msg = f"{e.message}"
            if e.file_path:
                msg += f"\nFile: {e.file_path}"
            if e.details:
                msg += f"\nDetails: {e.details}"
            logger.error(msg)
            self.error.emit(msg)

        except Exception as e:
            msg = f"Manual transfer failed: {e}"
            logger.error(msg)
            self.error.emit(msg)
