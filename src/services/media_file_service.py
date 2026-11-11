"""Safe media file operations that keep Jellyfin sidecars in step."""

from __future__ import annotations

import errno
import os
import posixpath
from typing import Optional

from src.models.errors import ConnectionLostError
from src.services.ffmpeg_service import is_video_file
from src.services.remote_file_service import safe_rename, safe_stat
from src.utils.logging_signal import logger


class MediaFileService:
    """Coordinate media file renames and their matching NFO sidecars."""

    def rename(
        self,
        old_path: str,
        new_path: str,
        *,
        is_remote: bool,
        sftp: Optional[object] = None,
        is_directory: bool = False,
    ) -> Optional[str]:
        """Rename a media file and its same-basename NFO when present."""
        if is_remote:
            old_path = old_path.replace("\\", "/")
            new_path = new_path.replace("\\", "/")
        if is_directory or not is_video_file(old_path):
            self._rename_path(old_path, new_path, is_remote=is_remote, sftp=sftp)
            return None

        if is_remote:
            if sftp is None:
                raise ConnectionLostError("No connection available for rename")
            if self._remote_file_exists(sftp, new_path):
                raise FileExistsError(f"A file already exists at {new_path}")
        elif os.path.exists(new_path) and not os.path.samefile(old_path, new_path):
            raise FileExistsError(f"A file already exists at {new_path}")

        split_path = posixpath.splitext if is_remote else os.path.splitext
        old_nfo = split_path(old_path)[0] + ".nfo"
        new_nfo = split_path(new_path)[0] + ".nfo"
        if is_remote:
            if sftp is None:
                raise ConnectionLostError("No connection available for rename")
            sidecar_exists = self._remote_file_exists(sftp, old_nfo)
            if sidecar_exists and self._remote_file_exists(sftp, new_nfo):
                raise FileExistsError(f"NFO sidecar already exists: {new_nfo}")
        else:
            sidecar_exists = os.path.isfile(old_nfo)
            if sidecar_exists and os.path.exists(new_nfo):
                same_case_insensitive_path = (
                    os.path.samefile(old_nfo, new_nfo)
                )
                if not same_case_insensitive_path:
                    raise FileExistsError(f"NFO sidecar already exists: {new_nfo}")

        self._rename_path(old_path, new_path, is_remote=is_remote, sftp=sftp)
        if not sidecar_exists:
            return None

        try:
            self._rename_path(old_nfo, new_nfo, is_remote=is_remote, sftp=sftp)
        except Exception as sidecar_error:
            try:
                self._rename_path(new_path, old_path, is_remote=is_remote, sftp=sftp)
            except Exception as rollback_error:
                logger.error(
                    f"Rename: NFO sidecar failed and video rollback failed: "
                    f"{rollback_error}"
                )
                raise RuntimeError(
                    f"Video renamed to {new_path}, but its NFO could not be moved "
                    f"and the video could not be restored: {rollback_error}"
                ) from sidecar_error
            raise RuntimeError(
                f"Could not rename NFO sidecar. Video rename was rolled back: "
                f"{sidecar_error}"
            ) from sidecar_error
        return new_nfo

    @staticmethod
    def _remote_file_exists(sftp: object, path: str) -> bool:
        try:
            safe_stat(sftp, path)
            return True
        except (IOError, OSError) as error:
            if getattr(error, "errno", None) == errno.ENOENT:
                return False
            if "no such file" in str(error).lower():
                return False
            raise

    @staticmethod
    def _rename_path(
        old_path: str,
        new_path: str,
        *,
        is_remote: bool,
        sftp: Optional[object],
    ) -> None:
        if is_remote:
            if sftp is None:
                raise ConnectionLostError("No connection available for rename")
            safe_rename(
                sftp,
                old_path.replace("\\", "/"),
                new_path.replace("\\", "/"),
            )
            return
        os.rename(old_path, new_path)
