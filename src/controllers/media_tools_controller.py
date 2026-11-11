"""Coordinate media dialogs, remote media services, and background repairs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional, Protocol

from paramiko import SFTPClient
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from src.config.settings import Settings
from src.models.media import AudioTrack, QuickFixOptions, SubtitleTrack
from src.services.activity_history_service import ActivityHistoryService
from src.services.remote_media_service import RemoteMediaService
from src.utils.icons import get_file_icon
from src.utils.logging_signal import logger
from src.workers.quick_fix_worker import QuickFixWorker
from src.widgets.transfer_queue_widget import TransferStatus
from src.widgets.tree_widgets import SortableTreeWidgetItem

if TYPE_CHECKING:
    from src.widgets.video_convert_manager import VideoConvertManager


class MediaToolsView(Protocol):
    """Small view interface required by media workflow coordination."""

    sftp: Optional[SFTPClient]

    def refresh(self) -> None: ...

    def window(self) -> QWidget: ...


class DetailPanelView(Protocol):
    """Display operations used by the metadata workflow."""

    def show_metadata(self, metadata: dict[str, str]) -> None: ...

    def clear_metadata(self) -> None: ...

    def show_stream_info(self, data: dict) -> None: ...

    def clear_stream_info(self) -> None: ...


class MediaToolsController:
    """Coordinate media dialogs, services, worker lifetimes, and history."""

    def __init__(
        self,
        view: MediaToolsView,
        settings: Settings,
        history: ActivityHistoryService,
    ) -> None:
        self._view = view
        self._settings = settings
        self._history = history
        self._convert_manager: Optional[VideoConvertManager] = None
        self._quick_fix_threads: list[tuple[QThread, QuickFixWorker]] = []
        self._quick_fix_queue: list[
            tuple[str, QuickFixOptions, str, int]
        ] = []
        self._quick_fix_active = False
        self._quick_fix_needs_refresh = False

    def handle_convert_video(self, remote_path: str, codec: str = "h264") -> None:
        """Delegate a conversion request to the conversion queue manager."""
        if self._convert_manager is None:
            from src.widgets.video_convert_manager import VideoConvertManager

            self._convert_manager = VideoConvertManager(
                self._view, self._settings, self._history
            )
        self._convert_manager.request_conversion(
            remote_path, self._view.sftp, codec=codec
        )

    def show_convert_settings(self) -> None:
        """Show conversion preferences."""
        from src.views.dialogs.convert_settings_dialog import ConvertSettingsDialog

        ConvertSettingsDialog(self._view).exec()

    def load_detail_info(
        self,
        panel: DetailPanelView,
        sftp: SFTPClient,
        remote_path: str,
        nfo_metadata: Optional[dict[str, str]],
    ) -> None:
        """Load stream details and render NFO values supplied from the cache."""
        service = RemoteMediaService(sftp)
        try:
            panel.show_stream_info(service.probe_media(remote_path))
        except Exception:
            panel.clear_stream_info()

        if nfo_metadata is None:
            panel.clear_metadata()
        else:
            panel.show_metadata(nfo_metadata)

    def show_media_info(self, remote_path: str, open_tab: str = "info") -> None:
        """Load remote metadata and present it in the media information dialog."""
        sftp = self._view.sftp
        if not sftp:
            return

        from src.views.dialogs.media_info_dialog import MediaInfoDialog

        try:
            media_service = RemoteMediaService(sftp)
            probe_data = media_service.probe_media(remote_path)
            try:
                nfo_data = media_service.read_nfo(remote_path)
            except Exception:
                nfo_data = {}
            nfo_path = os.path.splitext(remote_path)[0] + ".nfo"

            dialog = MediaInfoDialog(
                remote_path=remote_path,
                probe_data=probe_data,
                nfo_data=nfo_data,
                sftp=sftp,
                parent=self._view,
                open_tab=open_tab,
            )
            dialog.exec()

            if dialog.result() == MediaInfoDialog.DialogCode.Accepted:
                if not self._settings.config.hide_nfo_files:
                    self._add_nfo_item(os.path.basename(nfo_path))
                invalidate_cache = getattr(self._view, "invalidate_nfo_cache", None)
                if callable(invalidate_cache):
                    invalidate_cache(nfo_path)
        except Exception as error:
            logger.error(f"Media Info: Failed to get metadata: {error}")

    def probe_subtitle_tracks(self, remote_path: str) -> list[SubtitleTrack]:
        """Load subtitle tracks, returning an empty list when probing fails."""
        sftp = self._view.sftp
        if not sftp:
            return []
        try:
            return RemoteMediaService(sftp).probe_subtitle_tracks(remote_path)
        except Exception:
            return []

    def probe_audio_tracks(self, remote_path: str) -> list[AudioTrack]:
        """Load audio tracks, returning an empty list when probing fails."""
        sftp = self._view.sftp
        if not sftp:
            return []
        try:
            return RemoteMediaService(sftp).probe_audio_tracks(remote_path)
        except Exception:
            return []

    def quick_fix_video(self, remote_path: str) -> None:
        """Show repair options and queue one video fix."""
        sftp = self._view.sftp
        if not sftp:
            return

        from src.views.dialogs.quick_fix_dialog import QuickFixDialog

        filename = os.path.basename(remote_path)
        extension = os.path.splitext(remote_path)[1]
        try:
            audio_tracks, subtitle_tracks = RemoteMediaService(
                sftp
            ).probe_stream_tracks(remote_path)
        except Exception:
            audio_tracks, subtitle_tracks = [], []
        dialog = QuickFixDialog(
            self._view,
            filename,
            extension,
            subtitle_tracks=subtitle_tracks,
            audio_tracks=audio_tracks,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._queue_quick_fix_jobs(
            [remote_path], dialog.options, len(subtitle_tracks)
        )

    def quick_fix_videos(self, remote_paths: list[str]) -> None:
        """Apply container or timestamp fixes to several selected videos."""
        sftp = self._view.sftp
        if not sftp or not remote_paths:
            return
        from src.services.ffmpeg_service import is_video_file

        paths = [path for path in remote_paths if is_video_file(path)]
        if not paths:
            return
        if len(paths) == 1:
            self.quick_fix_video(paths[0])
            return

        from src.views.dialogs.quick_fix_dialog import QuickFixDialog

        dialog = QuickFixDialog(
            self._view,
            f"{len(paths)} videos",
            "",
            batch_mode=True,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._queue_quick_fix_jobs(paths, dialog.options, 0)

    def _queue_quick_fix_jobs(
        self,
        remote_paths: list[str],
        options: QuickFixOptions,
        subtitle_track_count: int,
    ) -> None:
        """Build queue entries for one or more selected Quick Fix jobs."""
        sftp = self._view.sftp
        if not sftp:
            return
        basenames = [os.path.basename(path) for path in remote_paths]
        duplicate_names = {
            name for name in basenames if basenames.count(name) > 1
        }
        for path, filename in zip(remote_paths, basenames):
            display_name = f"🔧 {filename}"
            if filename in duplicate_names:
                display_name += f" ({os.path.dirname(path)})"
            self._quick_fix_queue.append(
                (path, options, display_name, subtitle_track_count)
            )
            main_window = self._view.window()
            if hasattr(main_window, "transfer_queue"):
                main_window.transfer_queue.add_transfer(
                    display_name, 0, os.path.dirname(path)
                )

        if not self._quick_fix_active:
            self._process_next_quick_fix()

    def _process_next_quick_fix(self) -> None:
        """Run the next Quick Fix job and refresh once the queue drains."""
        if self._quick_fix_active:
            return
        if not self._quick_fix_queue:
            if self._quick_fix_needs_refresh:
                self._view.refresh()
                self._quick_fix_needs_refresh = False
            return

        sftp = self._view.sftp
        if not sftp:
            self._fail_pending_quick_fixes("SSH connection is unavailable")
            return
        media_service = RemoteMediaService(sftp)
        try:
            transport = media_service.get_transport()
            if transport is None:
                raise RuntimeError("No SSH connection available")
        except Exception as error:
            logger.error(f"Quick Fix: {error}")
            self._fail_pending_quick_fixes(str(error))
            return

        remote_path, options, display_name, subtitle_track_count = (
            self._quick_fix_queue.pop(0)
        )
        try:
            command, action_summary = media_service.build_quick_fix_command(
                remote_path,
                options,
                subtitle_track_count=subtitle_track_count,
            )
        except Exception as error:
            logger.error(f"Quick Fix: Could not prepare {remote_path}: {error}")
            transfer_queue = getattr(self._view.window(), "transfer_queue", None)
            index = self._find_quick_fix_row(
                transfer_queue, display_name, TransferStatus.PENDING
            )
            if transfer_queue is not None and index >= 0:
                transfer_queue.set_failed(index, str(error)[:80])
            QTimer.singleShot(0, self._process_next_quick_fix)
            return
        self._quick_fix_active = True
        logger.info(f"Quick Fix: {os.path.basename(remote_path)} ({action_summary})")

        main_window = self._view.window()
        transfer_queue = getattr(main_window, "transfer_queue", None)
        queue_index = self._find_quick_fix_row(
            transfer_queue, display_name, TransferStatus.PENDING
        )
        if transfer_queue is not None and queue_index >= 0:
            transfer_queue.set_in_progress(queue_index)

        thread = QThread(self._view)
        worker = QuickFixWorker(transport, command)
        worker.moveToThread(thread)
        self._quick_fix_threads.append((thread, worker))

        def on_thread_finished() -> None:
            active_index = self._find_quick_fix_row(
                transfer_queue, display_name, TransferStatus.IN_PROGRESS
            )
            if worker.error_msg:
                logger.error(f"Quick Fix error: {worker.error_msg}")
                if transfer_queue is not None and active_index >= 0:
                    transfer_queue.set_failed(active_index, worker.error_msg[:80])
            elif worker.exit_code == 0:
                logger.success(f"Quick Fix complete: {os.path.basename(remote_path)}")
                if transfer_queue is not None and active_index >= 0:
                    transfer_queue.set_completed(active_index)
                self._history.add(
                    filename=os.path.basename(remote_path),
                    action="convert",
                    source=remote_path,
                    destination=remote_path,
                    server_name=self._settings.config.current_server_id,
                )
                self._quick_fix_needs_refresh = True
            else:
                message = f"ffmpeg exit code {worker.exit_code}"
                logger.error(f"Quick Fix failed: {message}")
                if transfer_queue is not None and active_index >= 0:
                    transfer_queue.set_failed(active_index, message)

            self._quick_fix_threads.remove((thread, worker))
            worker.deleteLater()
            thread.deleteLater()
            self._quick_fix_active = False
            QTimer.singleShot(0, self._process_next_quick_fix)

        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        thread.finished.connect(on_thread_finished)
        thread.start()

    @staticmethod
    def _find_quick_fix_row(transfer_queue, display_name: str, status) -> int:
        """Find a Quick Fix row again after earlier rows have been removed."""
        if transfer_queue is None:
            return -1
        return next(
            (
                index
                for index, item in enumerate(transfer_queue._items)
                if item.display_name == display_name and item.status == status
            ),
            -1,
        )

    def _fail_pending_quick_fixes(self, message: str) -> None:
        """Mark queued Quick Fix rows failed when SSH is no longer available."""
        main_window = self._view.window()
        transfer_queue = getattr(main_window, "transfer_queue", None)
        for _, _, display_name, _ in self._quick_fix_queue:
            index = self._find_quick_fix_row(
                transfer_queue, display_name, TransferStatus.PENDING
            )
            if transfer_queue is not None and index >= 0:
                transfer_queue.set_failed(index, message[:80])
        self._quick_fix_queue.clear()
        if self._quick_fix_needs_refresh:
            self._view.refresh()
            self._quick_fix_needs_refresh = False

    def _add_nfo_item(self, filename: str) -> None:
        """Add a saved NFO sidecar to the current tree when it is not listed."""
        tree = getattr(self._view, "tree_widget", None)
        if tree is None:
            return
        for index in range(tree.topLevelItemCount()):
            if tree.topLevelItem(index).text(0) == filename:
                return

        item = SortableTreeWidgetItem([filename, ""])
        item.setIcon(0, get_file_icon(False, filename))
        tree.addTopLevelItem(item)
