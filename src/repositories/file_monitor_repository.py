"""
File monitoring repository for detecting and processing media file changes.

This module uses watchdog to monitor a directory for new media files and
automatically transfers them to a Raspberry Pi. It includes file stability
checking to prevent race conditions where files are transferred before
they're fully written to disk.

Classification is based purely on folder structure:
- Files in Movies/ directory are treated as movies
- Files in TV_shows/ directory are treated as TV shows
"""

import os
import time
from queue import Queue
from threading import Lock, Thread, Event
from typing import Dict, Set, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.models.errors import FileMonitorError, FileStabilityError
from src.services.file_deletion_service import FileDeletionService
from src.services.movie_service import MovieService
from src.services.tv_service import TvService
from src.utils.constants import MOVIES_DIR, TV_SHOWS_DIR
from src.utils.logging_signal import logger


class FileStabilityTracker:
    """
    Tracks file stability to prevent transferring files that are still being written.

    A file is considered stable when its size hasn't changed for a specified duration.
    This prevents race conditions where watchdog detects a file before it's fully copied.

    Uses a background polling thread to continuously check tracked files.
    Stable files are enqueued for processing by the main thread.
    """

    @staticmethod
    def _is_hidden_file(file_path: str) -> bool:
        """Check if a file is hidden (basename starts with a dot)."""
        return os.path.basename(file_path).startswith(".")

    def __init__(self, stability_duration: float = 2.0, check_interval: float = 0.5):
        """
        Initialize the stability tracker.

        Args:
            stability_duration: Seconds to wait for file size to stabilize (default: 2.0)
            check_interval: Seconds between stability checks (default: 0.5)
        """
        self.stability_duration = stability_duration
        self.check_interval = check_interval
        self._file_info: Dict[str, tuple[float, int]] = {}  # path -> (timestamp, size)
        self._lock = Lock()
        self._stop_event = Event()
        self._polling_thread: Thread | None = None
        self._stable_files_queue: Queue[str] | None = None

    def start_polling(self, stable_files_queue: Queue[str]) -> None:
        """
        Start the background polling thread.

        Args:
            stable_files_queue: Queue to enqueue stable file paths for main thread processing
        """
        # Guard against multiple polling threads
        if self._polling_thread and self._polling_thread.is_alive():
            logger.warn("Monitor: Stability: Already running")
            self.stop_polling()

        self._stable_files_queue = stable_files_queue
        self._stop_event.clear()
        self._polling_thread = Thread(target=self._poll_files, daemon=True)
        self._polling_thread.start()
        logger.info("Monitor: Stability: Started")

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._polling_thread:
            self._polling_thread.join(timeout=2.0)
            # Check if thread is still alive after timeout
            if self._polling_thread.is_alive():
                logger.warn("Monitor: Stability: Failed to stop (timeout)")
            self._polling_thread = None
        logger.info("Monitor: Stability: Stopped")

    def _poll_files(self) -> None:
        """Background thread that continuously checks tracked files for stability."""
        while not self._stop_event.is_set():
            with self._lock:
                files_to_check = list(self._file_info.keys())

            for file_path in files_to_check:
                try:
                    if self.check_stability(file_path):
                        # File is stable, enqueue for main thread processing
                        if self._stable_files_queue:
                            self._stable_files_queue.put(file_path)
                            logger.info(
                                f"Monitor: {os.path.basename(file_path)}: Enqueued"
                            )
                except Exception as e:
                    logger.error(
                        f"Monitor: {os.path.basename(file_path)}: Stability check failed"
                    )

            # Sleep for check_interval or until stop event
            self._stop_event.wait(self.check_interval)

    def check_stability(self, file_path: str) -> bool:
        """
        Check if a file is stable (not being written to).

        Args:
            file_path: Path to file to check

        Returns:
            True if file is stable, False if still being written

        Raises:
            FileStabilityError: If file cannot be accessed
        """
        try:
            # Skip hidden files entirely
            if self._is_hidden_file(file_path):
                return False

            if not os.path.exists(file_path):
                # File was deleted, remove from tracking
                with self._lock:
                    self._file_info.pop(file_path, None)
                return False

            current_size = os.path.getsize(file_path)
            current_time = time.time()

            with self._lock:
                if file_path not in self._file_info:
                    # First time seeing this file, record its size
                    self._file_info[file_path] = (current_time, current_size)
                    logger.info(
                        f"Monitor: {os.path.basename(file_path)}: Tracking stability"
                    )
                    return False

                last_time, last_size = self._file_info[file_path]

                if current_size != last_size:
                    # Size changed, file still being written
                    self._file_info[file_path] = (current_time, current_size)
                    logger.info(
                        f"Monitor: {os.path.basename(file_path)}: Still growing"
                    )
                    return False

                # Size hasn't changed, check if enough time has passed
                elapsed = current_time - last_time
                if elapsed >= self.stability_duration:
                    # File is stable, remove from tracking
                    self._file_info.pop(file_path, None)
                    logger.success(f"Monitor: {os.path.basename(file_path)}: Stable")
                    logger.progress_signal.emit(100)  # Complete
                    return True

                # Not enough time has passed yet
                progress = int((elapsed / self.stability_duration) * 100)
                # logger.info(
                #     f"Monitor: {os.path.basename(file_path)}: Waiting for stability"
                # )
                logger.progress_signal.emit(progress)  # Show progress
                return False

        except OSError as e:
            raise FileStabilityError(
                f"Cannot check file stability", path=file_path, details=str(e)
            )

    def clear_tracking(self, file_path: str) -> None:
        """Remove a file from stability tracking."""
        with self._lock:
            self._file_info.pop(file_path, None)

    def clear_all(self) -> None:
        """Clear all tracked files."""
        with self._lock:
            self._file_info.clear()


class FileMonitorRepository(FileSystemEventHandler):
    """
    Monitors a directory for media files and automatically transfers them to Raspberry Pi.

    This class uses watchdog to detect file system events and processes media files
    (movies and TV shows) by transferring them to a remote server via SFTP.

    Classification is based on folder structure:
    - Files in Movies/ directory are treated as movies
    - Files in TV_shows/ directory are treated as TV shows
    - Files outside these directories are ignored

    Features:
    - File stability checking to prevent race conditions
    - Path-based classification (no heuristics)
    - Preserves directory structure for TV shows
    - Automatic cleanup after successful transfer
    """

    def __init__(
        self,
        watch_dir: str,
        movie_service: MovieService,
        tv_service: TvService,
        deletion_service: FileDeletionService,
        file_exts: Set[str],
        stability_duration: float = 2.0,
        transfer_callback: Callable[[str], None] | None = None,
        stable_files_queue: Queue[str] | None = None,
    ) -> None:
        """
        Initialize the file monitor.

        Args:
            watch_dir: Directory to monitor for new files
            movie_service: Service for transferring movies
            tv_service: Service for transferring TV shows
            deletion_service: Service for deleting local files after transfer
            file_exts: Set of allowed file extensions (e.g., {'.mp4', '.mkv'})
            stability_duration: Seconds to wait for file stability (default: 2.0)
            transfer_callback: Optional callback to call after each transfer completes
            stable_files_queue: Queue for thread-safe file processing (required for thread safety)
        """
        super().__init__()
        self.watch_dir = watch_dir
        self.movie_service = movie_service
        self.tv_service = tv_service
        self.deletion_service = deletion_service
        self.file_exts = file_exts
        self.observer = Observer()
        self.stability_tracker = FileStabilityTracker(stability_duration)
        self.transfer_callback = transfer_callback
        self.stable_files_queue = stable_files_queue or Queue()

        # Track processed items to avoid duplicate processing
        self._processed_items: Set[str] = set()
        self._processed_lock = Lock()

        # Track retry attempts to prevent infinite loops
        self._retry_counts: Dict[str, int] = {}
        self._max_retries = 3

    def create_directories(self) -> None:
        """
        Create the watch directory structure if it doesn't exist.

        Creates:
        - Main watch directory
        - Movies subdirectory
        - TV_shows subdirectory
        """
        movies_dir = os.path.join(self.watch_dir, MOVIES_DIR)
        tv_dir = os.path.join(self.watch_dir, TV_SHOWS_DIR)

        for directory in [self.watch_dir, movies_dir, tv_dir]:
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                logger.error(
                    f"Monitor: {os.path.basename(directory)}: Failed to create directory"
                )
                raise FileMonitorError(
                    f"Failed to create watch directory", path=directory, details=str(e)
                )

    def start_monitoring(self) -> None:
        """
        Start monitoring the watch directory for file system events.

        Raises:
            FileMonitorError: If monitoring cannot be started
        """
        try:
            # Guard against multiple starts
            if self.observer.is_alive():
                logger.warn("Monitor: Monitoring: Already running")
                return

            # Start the stability polling thread with queue
            self.stability_tracker.start_polling(self.stable_files_queue)

            # Start the file system observer
            self.observer.schedule(self, self.watch_dir, recursive=True)
            self.observer.start()
            logger.start("Monitor: Monitoring: Started")
        except Exception as e:
            raise FileMonitorError(
                f"Failed to start file monitoring", path=self.watch_dir, details=str(e)
            )

    def stop_monitoring(self) -> None:
        """
        Stop monitoring and clean up resources.

        This method blocks until the observer thread has finished.
        """
        try:
            # Stop the stability polling thread
            self.stability_tracker.stop_polling()

            # Stop the file system observer
            self.observer.stop()
            self.observer.join()
            self.stability_tracker.clear_all()
            logger.stop("Monitor: Monitoring: Stopped")
        except Exception as e:
            logger.error("Monitor: Monitoring: Failed to stop")

    def on_created(self, event: FileSystemEvent) -> None:
        """
        Handle file/folder creation events.

        Args:
            event: Watchdog file system event
        """
        # Ensure src_path is a string
        src_path = (
            event.src_path
            if isinstance(event.src_path, str)
            else event.src_path.decode("utf-8")
        )

        # Skip hidden files and folders entirely
        if FileStabilityTracker._is_hidden_file(src_path):
            return

        if event.is_directory:
            self._schedule_folder_processing(src_path)
        else:
            self._schedule_file_processing(src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        Handle file modification events.

        Only processes file modifications (not directories) to detect when
        files finish being written.

        Args:
            event: Watchdog file system event
        """
        if not event.is_directory:
            # Ensure src_path is a string
            src_path = (
                event.src_path
                if isinstance(event.src_path, str)
                else event.src_path.decode("utf-8")
            )

            # Skip hidden files entirely
            if FileStabilityTracker._is_hidden_file(src_path):
                return

            self._schedule_file_processing(src_path)

    def _schedule_file_processing(self, file_path: str) -> None:
        """
        Schedule a file for processing after stability check.

        This method adds the file to the stability tracker. The polling thread
        will continuously check the file and call handle_file() when it's stable.

        Args:
            file_path: Path to file to process
        """
        # Skip if already processed
        with self._processed_lock:
            if file_path in self._processed_items:
                return

        # Add to stability tracker (polling thread will check it)
        try:
            is_stable = self.stability_tracker.check_stability(file_path)
            # If file is already stable, enqueue immediately
            if is_stable:
                self.stable_files_queue.put(file_path)
                logger.info(f"Monitor: {os.path.basename(file_path)}: Enqueued")
        except FileStabilityError as e:
            logger.error("Monitor: Monitoring: Stability check failed")

    def _schedule_folder_processing(self, folder_path: str) -> None:
        """
        Schedule a folder for processing.

        Folders are enqueued for processing by the main thread.

        Args:
            folder_path: Path to folder to process
        """
        # Skip if already processed
        with self._processed_lock:
            if folder_path in self._processed_items:
                return

        # Enqueue folder for main thread processing
        self.stable_files_queue.put(folder_path)
        logger.info(f"Monitor: {os.path.basename(folder_path)}: Enqueued")

    def _mark_as_processed(self, path: str) -> None:
        """
        Mark a file or folder as processed to prevent duplicate processing.

        Args:
            path: Path to mark as processed
        """
        with self._processed_lock:
            self._processed_items.add(path)

    def _mark_folder_contents_processed(self, folder_path: str) -> None:
        """
        Mark all files inside a folder as processed and clear them from stability tracking.

        This prevents duplicate processing when both a folder event and individual
        file stability events are triggered for the same content (e.g., when a folder
        is dropped into the watch directory).

        Args:
            folder_path: Path to folder whose contents should be marked processed
        """
        if not os.path.exists(folder_path):
            return

        with self._processed_lock:
            for root, dirs, files in os.walk(folder_path):
                self._processed_items.add(root)
                for f in files:
                    file_path = os.path.join(root, f)
                    self._processed_items.add(file_path)
                    self.stability_tracker.clear_tracking(file_path)

    def handle_file(self, file_path: str) -> None:
        """
        Process a stable file for transfer.

        This method:
        1. Validates the file (not hidden, valid extension)
        2. Classifies the file based on path (Movies/ or TV_shows/)
        3. Transfers the parent folder
        4. Deletes local files after successful transfer

        Args:
            file_path: Path to file to process
        """
        # Check if already processed (fast-path to avoid duplicate transfers)
        with self._processed_lock:
            if file_path in self._processed_items:
                logger.info(
                    f"Monitor: {os.path.basename(file_path)}: Already processed"
                )
                return

        # Validate file exists
        if not os.path.exists(file_path):
            logger.warn(f"Monitor: {os.path.basename(file_path)}: File not found")
            self.stability_tracker.clear_tracking(file_path)
            return

        # Ignore hidden/system files
        name = os.path.basename(file_path)
        if name.startswith(".") or name.startswith("._"):
            logger.info(f"Monitor: {name}: Skipping (hidden file)")
            return

        # Check file extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.file_exts:
            logger.info(f"Monitor: {name}: Skipping (unsupported type: {ext})")
            return

        # Determine destination type based on path structure
        path_parts = file_path.split(os.sep)
        if MOVIES_DIR in path_parts:
            dest_type = "movie"
            logger.info(f"Monitor: {name}: Classified as movie")
        elif TV_SHOWS_DIR in path_parts:
            dest_type = "tv"
            logger.info(f"Monitor: {name}: Classified as TV show")
        else:
            # Files outside Movies/ or TV_shows/ are ignored
            logger.warn(f"Monitor: {name}: Skipping (outside Movies/TV_shows)")
            return

        try:
            folder = os.path.dirname(file_path)

            if dest_type == "movie":
                # Transfer entire movie folder
                logger.upload(
                    f"Monitor: {os.path.basename(folder)}: Transferring movie"
                )
                if self.movie_service.transfer_movie_folder(folder):
                    self._mark_as_processed(file_path)
                    self._mark_as_processed(folder)
                    self._mark_folder_contents_processed(folder)
                    self.deletion_service.delete_folder(folder)
                    logger.success(
                        f"Monitor: {os.path.basename(folder)}: Movie transfer complete"
                    )
                    # Clear retry count on success
                    self._retry_counts.pop(file_path, None)
                    # Notify callback
                    if self.transfer_callback:
                        self.transfer_callback(file_path)
                else:
                    # Transfer failed - check retry count
                    retry_count = self._retry_counts.get(file_path, 0)
                    if retry_count < self._max_retries:
                        self._retry_counts[file_path] = retry_count + 1
                        logger.error(
                            f"Monitor: {os.path.basename(folder)}: Movie transfer failed (retry {retry_count + 1}/{self._max_retries})"
                        )
                        self.stable_files_queue.put(file_path)
                    else:
                        logger.error(
                            f"Monitor: {os.path.basename(folder)}: Movie transfer failed permanently"
                        )
                        self._retry_counts.pop(file_path, None)

            elif dest_type == "tv":
                # Transfer TV show folder (preserves structure)
                logger.upload(
                    f"Monitor: {os.path.basename(folder)}: Transferring TV show"
                )
                transfer_result = self.tv_service.transfer_tv_folder(folder)
                if transfer_result:
                    self._mark_as_processed(file_path)
                    # Only delete media files, keep folder structure
                    if ext in self.file_exts:
                        self.deletion_service.delete_file(file_path)
                    logger.success(f"Monitor: {name}: TV show transfer complete")
                    # Clear retry count on success
                    self._retry_counts.pop(file_path, None)
                    # Notify callback
                    if self.transfer_callback:
                        self.transfer_callback(file_path)
                else:
                    # Transfer failed - check retry count
                    retry_count = self._retry_counts.get(file_path, 0)
                    if retry_count < self._max_retries:
                        self._retry_counts[file_path] = retry_count + 1
                        logger.error(
                            f"Monitor: {os.path.basename(folder)}: TV show transfer failed (retry {retry_count + 1}/{self._max_retries})"
                        )
                        self.stable_files_queue.put(file_path)
                    else:
                        logger.error(
                            f"Monitor: {os.path.basename(folder)}: TV show transfer failed permanently"
                        )
                        self._retry_counts.pop(file_path, None)

        except Exception as e:
            logger.error(f"Monitor: {os.path.basename(file_path)}: Transfer error")
            # Check retry count for exceptions too
            retry_count = self._retry_counts.get(file_path, 0)
            if retry_count < self._max_retries:
                self._retry_counts[file_path] = retry_count + 1
                logger.error(
                    f"Monitor: {os.path.basename(file_path)}: Will retry (attempt {retry_count + 1}/{self._max_retries})"
                )
                self.stable_files_queue.put(file_path)
            else:
                logger.error(
                    f"Monitor: {os.path.basename(file_path)}: Transfer failed permanently"
                )
                self._retry_counts.pop(file_path, None)
            # Clear from processed so it can be retried
            with self._processed_lock:
                self._processed_items.discard(file_path)

    def handle_folder(self, folder_path: str) -> None:
        """
        Process a folder for transfer.

        This method:
        1. Validates the folder (not hidden, not root directories)
        2. Classifies the folder based on path (Movies/ or TV_shows/)
        3. Transfers the folder
        4. Deletes local files after successful transfer

        Args:
            folder_path: Path to folder to process
        """
        # Check if already processed (fast-path to avoid duplicate transfers)
        with self._processed_lock:
            if folder_path in self._processed_items:
                logger.info(
                    f"Monitor: {os.path.basename(folder_path)}: Already processed, skipping"
                )
                return

        # Validate folder exists
        if not os.path.exists(folder_path):
            logger.warn(f"Monitor: {os.path.basename(folder_path)}: Folder not found")
            return

        # Ignore hidden folders and root directories
        name = os.path.basename(folder_path)
        if name.startswith(".") or name in [MOVIES_DIR, TV_SHOWS_DIR]:
            logger.info(f"Monitor: {name}: Skipping (system folder)")
            return

        # Classify folder based on path
        path_parts = folder_path.split(os.sep)
        if MOVIES_DIR in path_parts:
            dest_type = "movie"
            logger.info(f"Monitor: {name}: Classified as movie")
        elif TV_SHOWS_DIR in path_parts:
            dest_type = "tv"
            logger.info(f"Monitor: {name}: Classified as TV show")
        else:
            # Folders outside Movies/ or TV_shows/ are ignored
            logger.warn(f"Monitor: {name}: Skipping (outside Movies/TV_shows)")
            return

        try:
            if dest_type == "movie":
                # Transfer entire movie folder
                logger.upload(f"Monitor: {name}: Transferring movie")
                if self.movie_service.transfer_movie_folder(folder_path):
                    self._mark_as_processed(folder_path)
                    self._mark_folder_contents_processed(folder_path)
                    self.deletion_service.delete_folder(folder_path)
                    logger.success(f"Monitor: {name}: Movie transfer complete")
                    # Clear retry count on success
                    self._retry_counts.pop(folder_path, None)
                    # Notify callback
                    if self.transfer_callback:
                        self.transfer_callback(folder_path)
                else:
                    # Transfer failed - check retry count
                    retry_count = self._retry_counts.get(folder_path, 0)
                    if retry_count < self._max_retries:
                        self._retry_counts[folder_path] = retry_count + 1
                        logger.error(
                            f"Monitor: {name}: Movie transfer failed (retry {retry_count + 1}/{self._max_retries})"
                        )
                        self.stable_files_queue.put(folder_path)
                    else:
                        logger.error(
                            f"Monitor: {name}: Movie transfer failed permanently"
                        )
                        self._retry_counts.pop(folder_path, None)

            elif dest_type == "tv":
                # Transfer TV show folder (preserves structure)
                logger.upload(f"Monitor: {name}: Transferring TV show")
                if self.tv_service.transfer_tv_folder(folder_path):
                    self._mark_as_processed(folder_path)
                    self._mark_folder_contents_processed(folder_path)
                    # Delete only video files in the folder, keep structure
                    for root, _, files in os.walk(folder_path):
                        for f in files:
                            if f.startswith("."):
                                continue
                            ext = os.path.splitext(f)[1].lower()
                            if ext in self.file_exts:
                                file_to_delete = os.path.join(root, f)
                                try:
                                    self.deletion_service.delete_file(file_to_delete)
                                except Exception as e:
                                    logger.warn(f"Monitor: {f}: Could not delete")
                    logger.success(f"Monitor: {name}: TV show transfer complete")
                    # Clear retry count on success
                    self._retry_counts.pop(folder_path, None)
                    # Notify callback
                    if self.transfer_callback:
                        self.transfer_callback(folder_path)
                else:
                    # Transfer failed - check retry count
                    retry_count = self._retry_counts.get(folder_path, 0)
                    if retry_count < self._max_retries:
                        self._retry_counts[folder_path] = retry_count + 1
                        logger.error(
                            f"Monitor: {name}: TV show transfer failed (retry {retry_count + 1}/{self._max_retries})"
                        )
                        self.stable_files_queue.put(folder_path)
                    else:
                        logger.error(
                            f"Monitor: {name}: TV show transfer failed permanently"
                        )
                        self._retry_counts.pop(folder_path, None)

        except Exception as e:
            logger.error(f"Monitor: {os.path.basename(folder_path)}: Transfer error")
            # Check retry count for exceptions too
            retry_count = self._retry_counts.get(folder_path, 0)
            if retry_count < self._max_retries:
                self._retry_counts[folder_path] = retry_count + 1
                logger.error(
                    f"Monitor: {os.path.basename(folder_path)}: Will retry (attempt {retry_count + 1}/{self._max_retries})"
                )
                self.stable_files_queue.put(folder_path)
            else:
                logger.error(
                    f"Monitor: {os.path.basename(folder_path)}: Transfer failed permanently"
                )
                self._retry_counts.pop(folder_path, None)
            # Clear from processed so it can be retried
            with self._processed_lock:
                self._processed_items.discard(folder_path)
