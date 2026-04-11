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
            logger.warn(
                "Monitor: Polling thread already running, stopping existing thread first"
            )
            self.stop_polling()

        self._stable_files_queue = stable_files_queue
        self._stop_event.clear()
        self._polling_thread = Thread(target=self._poll_files, daemon=True)
        self._polling_thread.start()
        logger.info("Monitor: Started stability polling thread")

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._polling_thread:
            self._polling_thread.join(timeout=2.0)
            # Check if thread is still alive after timeout
            if self._polling_thread.is_alive():
                logger.warn(
                    "Monitor: Polling thread did not stop within timeout; may continue briefly"
                )
            self._polling_thread = None
        logger.info("Monitor: Stopped stability polling thread")

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
                                f"Monitor: Enqueued stable file: {os.path.basename(file_path)}"
                            )
                except Exception as e:
                    logger.error(
                        f"Monitor: Error checking stability for {file_path}: {e}"
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
                        f"Monitor: Tracking file stability: {os.path.basename(file_path)}"
                    )
                    return False

                last_time, last_size = self._file_info[file_path]

                if current_size != last_size:
                    # Size changed, file still being written
                    self._file_info[file_path] = (current_time, current_size)
                    logger.info(
                        f"Monitor: File still growing: {os.path.basename(file_path)} "
                        f"({last_size} -> {current_size} bytes)"
                    )
                    return False

                # Size hasn't changed, check if enough time has passed
                elapsed = current_time - last_time
                if elapsed >= self.stability_duration:
                    # File is stable, remove from tracking
                    self._file_info.pop(file_path, None)
                    logger.success(
                        f"Monitor: File stable: {os.path.basename(file_path)} "
                        f"({current_size} bytes)"
                    )
                    logger.progress_signal.emit(100)  # Complete
                    return True

                # Not enough time has passed yet
                progress = int((elapsed / self.stability_duration) * 100)
                logger.info(
                    f"Monitor: Waiting for stability: {os.path.basename(file_path)} "
                    f"({elapsed:.1f}/{self.stability_duration}s)"
                )
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
                logger.info(f"Monitor: Directory ready: {directory}")
            except Exception as e:
                logger.error(f"Monitor: Failed to create directory {directory}: {e}")
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
                logger.warn("Monitor: Observer already running, skipping start")
                return

            # Start the stability polling thread with queue
            self.stability_tracker.start_polling(self.stable_files_queue)

            # Start the file system observer
            self.observer.schedule(self, self.watch_dir, recursive=True)
            self.observer.start()
            logger.start(f"Monitor: Started watching: {self.watch_dir}")
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
            logger.stop("Monitor: Stopped")
        except Exception as e:
            logger.error(f"Monitor: Error stopping: {e}")

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
                logger.info(
                    f"Monitor: File already stable, enqueuing: {os.path.basename(file_path)}"
                )
        except FileStabilityError as e:
            logger.error(f"Monitor: Stability check failed: {e}")

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
        logger.info(f"Monitor: Enqueued folder: {os.path.basename(folder_path)}")

    def _mark_as_processed(self, path: str) -> None:
        """
        Mark a file or folder as processed to prevent duplicate processing.

        Args:
            path: Path to mark as processed
        """
        with self._processed_lock:
            self._processed_items.add(path)

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
                    f"Monitor: File already processed, skipping: {os.path.basename(file_path)}"
                )
                return

        # Validate file exists
        if not os.path.exists(file_path):
            logger.warn(f"Monitor: File no longer exists: {file_path}")
            self.stability_tracker.clear_tracking(file_path)
            return

        # Ignore hidden/system files
        name = os.path.basename(file_path)
        if name.startswith(".") or name.startswith("._"):
            logger.info(f"Monitor: Skipping hidden file: {name}")
            return

        # Check file extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.file_exts:
            logger.info(f"Monitor: Skipping unsupported file type: {name} ({ext})")
            return

        # Determine destination type based on path structure
        path_parts = file_path.split(os.sep)
        if MOVIES_DIR in path_parts:
            dest_type = "movie"
            logger.info(f"Monitor: Classified as movie (path-based): {name}")
        elif TV_SHOWS_DIR in path_parts:
            dest_type = "tv"
            logger.info(f"Monitor: Classified as TV show (path-based): {name}")
        else:
            # Files outside Movies/ or TV_shows/ are ignored
            logger.warn(f"Monitor: Skipping file outside Movies/TV_shows: {name}")
            return

        try:
            folder = os.path.dirname(file_path)

            if dest_type == "movie":
                # Transfer entire movie folder
                logger.upload(
                    f"Monitor: Transferring movie folder: {os.path.basename(folder)}"
                )
                if self.movie_service.transfer_movie_folder(folder):
                    self._mark_as_processed(file_path)
                    self._mark_as_processed(folder)
                    self.deletion_service.delete_folder(folder)
                    logger.success(
                        f"Monitor: Movie transfer complete: {os.path.basename(folder)}"
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
                            f"Monitor: Movie transfer failed for: {folder} - "
                            f"retry {retry_count + 1}/{self._max_retries}"
                        )
                        self.stable_files_queue.put(file_path)
                    else:
                        logger.error(
                            f"Monitor: Movie transfer failed permanently after {self._max_retries} attempts: {folder}"
                        )
                        self._retry_counts.pop(file_path, None)

            elif dest_type == "tv":
                # Transfer TV show folder (preserves structure)
                logger.upload(
                    f"Monitor: Transferring TV show folder: {os.path.basename(folder)}"
                )
                transfer_result = self.tv_service.transfer_tv_folder(folder)
                if transfer_result:
                    self._mark_as_processed(file_path)
                    # Only delete media files, keep folder structure
                    if ext in self.file_exts:
                        self.deletion_service.delete_file(file_path)
                    logger.success(f"Monitor: TV show transfer complete: {name}")
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
                            f"Monitor: TV show transfer failed for: {folder} - "
                            f"retry {retry_count + 1}/{self._max_retries}"
                        )
                        self.stable_files_queue.put(file_path)
                    else:
                        logger.error(
                            f"Monitor: TV show transfer failed permanently after {self._max_retries} attempts: {folder}"
                        )
                        self._retry_counts.pop(file_path, None)

        except Exception as e:
            logger.error(f"Monitor: Transfer error for {file_path}: {e}")
            # Check retry count for exceptions too
            retry_count = self._retry_counts.get(file_path, 0)
            if retry_count < self._max_retries:
                self._retry_counts[file_path] = retry_count + 1
                logger.error(
                    f"Monitor: Will retry - attempt {retry_count + 1}/{self._max_retries}"
                )
                self.stable_files_queue.put(file_path)
            else:
                logger.error(
                    f"Monitor: Transfer failed permanently after {self._max_retries} attempts"
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
                    f"Monitor: Folder already processed, skipping: {os.path.basename(folder_path)}"
                )
                return

        # Validate folder exists
        if not os.path.exists(folder_path):
            logger.warn(f"Monitor: Folder no longer exists: {folder_path}")
            return

        # Ignore hidden folders and root directories
        name = os.path.basename(folder_path)
        if name.startswith(".") or name in [MOVIES_DIR, TV_SHOWS_DIR]:
            logger.info(f"Monitor: Skipping system folder: {name}")
            return

        # Classify folder based on path
        path_parts = folder_path.split(os.sep)
        if MOVIES_DIR in path_parts:
            dest_type = "movie"
            logger.info(f"Monitor: Classified folder as movie (path-based): {name}")
        elif TV_SHOWS_DIR in path_parts:
            dest_type = "tv"
            logger.info(f"Monitor: Classified folder as TV show (path-based): {name}")
        else:
            # Folders outside Movies/ or TV_shows/ are ignored
            logger.warn(f"Monitor: Skipping folder outside Movies/TV_shows: {name}")
            return

        try:
            if dest_type == "movie":
                # Transfer entire movie folder
                logger.upload(f"Monitor: Transferring movie folder: {name}")
                if self.movie_service.transfer_movie_folder(folder_path):
                    self._mark_as_processed(folder_path)
                    self.deletion_service.delete_folder(folder_path)
                    logger.success(f"Monitor: Movie folder transfer complete: {name}")
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
                            f"Monitor: Movie folder transfer failed for: {folder_path} - "
                            f"retry {retry_count + 1}/{self._max_retries}"
                        )
                        self.stable_files_queue.put(folder_path)
                    else:
                        logger.error(
                            f"Monitor: Movie folder transfer failed permanently after {self._max_retries} attempts: {folder_path}"
                        )
                        self._retry_counts.pop(folder_path, None)

            elif dest_type == "tv":
                # Transfer TV show folder (preserves structure)
                logger.upload(f"Monitor: Transferring TV show folder: {name}")
                if self.tv_service.transfer_tv_folder(folder_path):
                    self._mark_as_processed(folder_path)
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
                                    logger.warn(f"Monitor: Could not delete {f}: {e}")
                    logger.success(f"Monitor: TV show folder transfer complete: {name}")
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
                            f"Monitor: TV show folder transfer failed for: {folder_path} - "
                            f"retry {retry_count + 1}/{self._max_retries}"
                        )
                        self.stable_files_queue.put(folder_path)
                    else:
                        logger.error(
                            f"Monitor: TV show folder transfer failed permanently after {self._max_retries} attempts: {folder_path}"
                        )
                        self._retry_counts.pop(folder_path, None)

        except Exception as e:
            logger.error(f"Monitor: Transfer error for folder {folder_path}: {e}")
            # Check retry count for exceptions too
            retry_count = self._retry_counts.get(folder_path, 0)
            if retry_count < self._max_retries:
                self._retry_counts[folder_path] = retry_count + 1
                logger.error(
                    f"Monitor: Will retry - attempt {retry_count + 1}/{self._max_retries}"
                )
                self.stable_files_queue.put(folder_path)
            else:
                logger.error(
                    f"Monitor: Transfer failed permanently after {self._max_retries} attempts"
                )
                self._retry_counts.pop(folder_path, None)
            # Clear from processed so it can be retried
            with self._processed_lock:
                self._processed_items.discard(folder_path)
