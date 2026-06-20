"""
Video convert manager — handles queuing and execution of remote ffmpeg conversions.

Manages a sequential queue of video conversion jobs, each running on its own
SSH connection to avoid blocking the explorer's SFTP session.

Inherits QObject so Qt can properly auto-detect cross-thread signal connections
(worker thread → main thread) without needing explicit QueuedConnection.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QMessageBox, QWidget

from src.config.settings import Settings
from src.utils.logging_signal import logger
from src.widgets.file_explorer_widget import _ConvertWorker
from src.widgets.transfer_queue_widget import TransferStatus


class VideoConvertManager(QObject):
    """
    Manages a queue of video conversion jobs.

    Each conversion runs ffmpeg on the remote server via a dedicated SSH session.
    Jobs are processed sequentially; the queue updates the transfer panel.
    """

    def __init__(self, parent_widget: QWidget, settings: Settings) -> None:
        super().__init__(parent_widget)  # QObject parent = main thread affinity
        self._parent = parent_widget
        self._settings = settings
        self._queue: list = []
        self._running = False
        self._current_index: int = -1
        self._thread: Optional[QThread] = None
        self._worker: Optional[_ConvertWorker] = None

        # Listen for queue index shifts (when user clears completed items)
        main_window = parent_widget.window()
        if hasattr(main_window, "transfer_queue"):
            main_window.transfer_queue.indices_changed.connect(
                self._on_queue_indices_changed
            )

    def request_conversion(
        self, remote_path: str, sftp: object, codec: str = "h264"
    ) -> None:
        """Validate and queue a video for conversion."""
        from src.clients.adb_client import ADBClient
        from src.clients.ios_client import IOSClient
        from src.services.ffmpeg_service import check_ffmpeg_installed
        from src.views.dialogs.convert_settings_dialog import get_convert_settings

        if isinstance(sftp, (ADBClient, IOSClient)):
            QMessageBox.warning(
                self._parent,
                "Not Available",
                "Video conversion is only available for SSH servers.",
            )
            return

        try:
            channel = sftp.get_channel()
            if not channel or not channel.get_transport():
                raise RuntimeError("No transport")
        except Exception:
            QMessageBox.warning(
                self._parent,
                "Connection Error",
                "Cannot access SSH connection for remote commands.",
            )
            return

        if not check_ffmpeg_installed(sftp):
            QMessageBox.warning(
                self._parent,
                "ffmpeg Not Found",
                "ffmpeg is not installed on the remote server.\n\n"
                "Install it with:\n"
                "  sudo apt install ffmpeg",
            )
            return

        settings = get_convert_settings()

        # If a specific codec was requested (from submenu), override
        if codec == "h265":
            settings.codec = "h265"
        elif codec == "h264":
            settings.codec = "h264"

        codec_label = {
            "h264": "H.264",
            "h265": "H.265",
            "vp9": "VP9",
        }.get(settings.codec, settings.codec)

        filename = os.path.basename(remote_path)
        reply = QMessageBox.question(
            self._parent,
            "Convert Video",
            f"Convert '{filename}' to {codec_label}?\n\n"
            f"Preset: {settings.preset}, CRF: {settings.crf}\n"
            f"Audio: {settings.audio_codec}\n\n"
            "This runs ffmpeg on the server. The original file will be "
            "replaced when conversion completes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Add to activity panel
        main_window = self._parent.window()
        queue_index = -1
        if hasattr(main_window, "transfer_queue"):
            queue = main_window.transfer_queue
            queue_index = queue.add_transfer(
                f"🔄 {filename} → {codec_label}", 0, os.path.dirname(remote_path)
            )

        self._queue.append((remote_path, queue_index, settings))
        logger.info(f"ffmpeg: Queued {filename} for {codec_label} conversion")

        if not self._running:
            self._process_next()

    def _process_next(self) -> None:
        """Process the next video in the queue."""
        if not self._queue:
            self._running = False
            return

        self._running = True
        remote_path, queue_index, settings = self._queue.pop(0)

        main_window = self._parent.window()
        if hasattr(main_window, "transfer_queue") and queue_index >= 0:
            main_window.transfer_queue.set_in_progress(queue_index)
        self._current_index = queue_index

        self._thread = QThread(self._parent)
        self._worker = _ConvertWorker(
            host=self._settings.host,
            username=self._settings.username,
            key_path=self._settings.ssh_key_path,
            port=self._settings.ssh_port,
            remote_path=remote_path,
            video_codec=settings.ffmpeg_video_codec,
            preset=settings.preset,
            crf=settings.crf,
            audio_args=settings.ffmpeg_audio_args,
            container=settings.container,
        )
        self._worker.moveToThread(self._thread)

        # No explicit QueuedConnection needed — Qt auto-detects because:
        # - self (receiver) is a QObject living on the main thread
        # - self._worker (sender) is a QObject on the worker thread
        # Qt uses AutoConnection which becomes QueuedConnection across threads.
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._on_error)
        self._worker.error.connect(self._thread.quit)
        self._worker.progress.connect(self._on_progress)

        self._thread.start()

    def _on_progress(self, pct: int) -> None:
        """Update progress bar. Runs on main thread (auto-queued by Qt)."""
        main_window = self._parent.window()
        if not hasattr(main_window, "transfer_queue"):
            return
        queue = main_window.transfer_queue
        idx = self._current_index
        if not (0 <= idx < len(queue._items)):
            return

        if pct < 0:
            # Indeterminate pulse
            queue._items[idx].total_bytes = 0
            queue._items[idx].transferred_bytes = 0
        else:
            queue._items[idx].total_bytes = 100
            queue._items[idx].transferred_bytes = pct

        # Force immediate widget refresh
        if 0 <= idx < len(queue._item_widgets):
            queue._item_widgets[idx].update_display()

    def _on_finished(self) -> None:
        """Conversion complete. Runs on main thread."""
        main_window = self._parent.window()
        if hasattr(main_window, "transfer_queue"):
            main_window.transfer_queue.set_completed(self._current_index)

        if self._worker:
            remote_path = self._worker.remote_path
            from src.services.activity_history_service import ActivityHistoryService

            history = ActivityHistoryService()
            history.add(
                filename=os.path.basename(remote_path),
                action="convert",
                source=remote_path,
                destination=remote_path.replace(
                    os.path.splitext(remote_path)[1], ".mp4"
                ),
                server_name=self._settings.config.current_server_id,
            )

        if hasattr(self._parent, "refresh"):
            self._parent.refresh()

        self._cleanup()
        self._process_next()

    def _on_error(self, error_msg: str) -> None:
        """Conversion failed. Runs on main thread."""
        main_window = self._parent.window()
        if hasattr(main_window, "transfer_queue"):
            main_window.transfer_queue.set_failed(self._current_index, error_msg[:80])

        logger.error(f"ffmpeg: {error_msg}")
        self._cleanup()
        self._process_next()

    def _cleanup(self) -> None:
        if self._thread:
            if self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def _on_queue_indices_changed(self) -> None:
        """Re-sync _current_index after items were removed from the queue."""
        if self._current_index < 0 or not self._running:
            return
        main_window = self._parent.window()
        if not hasattr(main_window, "transfer_queue"):
            return
        queue = main_window.transfer_queue
        # Find our in-progress conversion item by checking display name prefix
        for i, item in enumerate(queue._items):
            if (
                item.status == TransferStatus.IN_PROGRESS
                and item.display_name.startswith("🔄")
            ):
                self._current_index = i
                return
        # Not found — item was somehow removed; reset
        self._current_index = -1
