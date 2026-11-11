"""Business rules for renaming multiple local or remote files."""

from __future__ import annotations

import os
from stat import S_ISDIR
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from src.services.activity_history_service import ActivityHistoryService
from src.services.media_file_service import MediaFileService
from src.utils.logging_signal import logger


class RemoteRenameClient(Protocol):
    """Remote file operations required by batch rename."""

    def stat(self, path: str) -> object: ...

    def rename(self, old_path: str, new_path: str) -> None: ...


@dataclass
class BatchRenameResult:
    """Summary of one batch rename operation."""

    renamed_count: int = 0
    collisions: List[str] = field(default_factory=list)


class BatchRenameService:
    """Resolve name collisions, perform renames, and record successful changes."""

    def __init__(self, history: ActivityHistoryService) -> None:
        self._history = history

    def rename_paths(
        self,
        paths: List[str],
        find_text: str,
        replace_text: str,
        *,
        is_remote: bool,
        sftp: Optional[RemoteRenameClient],
        server_name: str = "",
    ) -> BatchRenameResult:
        """Rename paths and append numbered suffixes when names already exist."""
        result = BatchRenameResult()
        if is_remote and sftp is None:
            return result

        for path in paths:
            old_name = os.path.basename(path)
            new_name = old_name.replace(find_text, replace_text)
            if new_name == old_name:
                continue

            new_path = os.path.join(os.path.dirname(path), new_name)
            if self._path_exists(new_path, is_remote, sftp):
                new_path = self._available_suffixed_path(
                    new_path, is_remote=is_remote, sftp=sftp
                )
                result.collisions.append(
                    f"{new_name} → {os.path.basename(new_path)}"
                )

            try:
                is_directory = self._is_directory(path, is_remote, sftp)
                MediaFileService().rename(
                    path,
                    new_path,
                    is_remote=is_remote,
                    sftp=sftp,
                    is_directory=is_directory,
                )
            except Exception as error:
                logger.error(f"Rename failed: {old_name}: {error}")
                continue

            result.renamed_count += 1
            self._history.add(
                filename=old_name,
                action="rename",
                source=path,
                destination=new_path,
                server_name=server_name,
            )

        if result.collisions:
            logger.warn(
                f"Batch rename: {len(result.collisions)} name collisions resolved"
            )
        return result

    @staticmethod
    def _is_directory(
        path: str, is_remote: bool, sftp: Optional[RemoteRenameClient]
    ) -> bool:
        if not is_remote:
            return os.path.isdir(path)
        if sftp is None:
            return False
        try:
            mode = getattr(sftp.stat(path), "st_mode", None)
            return bool(mode is not None and S_ISDIR(mode))
        except (IOError, OSError):
            return False

    def _available_suffixed_path(
        self, path: str, *, is_remote: bool, sftp: Optional[RemoteRenameClient]
    ) -> str:
        base, extension = os.path.splitext(path)
        suffix = 2
        candidate = f"{base}_{suffix}{extension}"
        while self._path_exists(candidate, is_remote, sftp):
            suffix += 1
            candidate = f"{base}_{suffix}{extension}"
        return candidate

    @staticmethod
    def _path_exists(
        path: str, is_remote: bool, sftp: Optional[RemoteRenameClient]
    ) -> bool:
        if not is_remote:
            return os.path.exists(path)
        if sftp is None:
            return False
        try:
            sftp.stat(path)
            return True
        except (IOError, OSError):
            return False
