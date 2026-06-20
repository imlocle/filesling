import json
import os
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.utils.constants import (
    ERROR_LOG_FILE,
    LOGS_DIR_NAME,
    MAX_ERROR_LOG_ENTRIES,
    SOFTWARE_NAME,
)

# Logs directory — stored alongside config in the user's home (~/.FileSling/logs)
_LOGS_DIR = str(Path.home() / f".{SOFTWARE_NAME}" / LOGS_DIR_NAME)


def _ensure_logs_dir() -> None:
    """Create logs directory if it doesn't exist."""
    os.makedirs(_LOGS_DIR, exist_ok=True)


def _write_error_log(msg: str) -> None:
    """Append an error entry to the JSON log file."""
    try:
        _ensure_logs_dir()
        log_file = os.path.join(_LOGS_DIR, ERROR_LOG_FILE)

        # Load existing entries
        entries = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    entries = json.load(f)
            except (json.JSONDecodeError, IOError):
                entries = []

        # Append new entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": msg,
            "traceback": (
                traceback.format_exc()
                if traceback.format_exc().strip() != "NoneType: None"
                else None
            ),
        }
        entries.append(entry)

        # Keep last N entries to prevent unbounded growth
        entries = entries[-MAX_ERROR_LOG_ENTRIES:]

        with open(log_file, "w") as f:
            json.dump(entries, f, indent=2)

    except Exception:
        pass  # Don't crash the app if logging fails


class Logger(QObject):
    """
    Enhanced logger with timestamps and HTML formatting.

    Emits formatted log messages with:
    - Timestamps
    - Color-coded severity levels
    - Icons for visual identification
    - HTML formatting for rich text display

    Errors are also persisted to ~/.FileSling/logs/errors.json.
    """

    log_signal = Signal(str)  # For text logs (HTML formatted)
    progress_signal = Signal(int)  # For progress 0–100

    def _format_message(self, icon: str, msg: str, color: str) -> str:
        """Format message with timestamp, icon, and color."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return (
            f'<span style="color: #858585;">[{timestamp}]</span> '
            f'<span style="color: {color};">{icon}</span> '
            f'<span style="color: #cccccc;">{msg}</span>'
        )

    def info(self, msg: str) -> None:
        """Log informational message."""
        formatted = self._format_message("ℹ️", msg, "#4ec9b0")
        self.log_signal.emit(formatted)

    def success(self, msg: str) -> None:
        """Log success message."""
        formatted = self._format_message("✅", msg, "#4ec9b0")
        self.log_signal.emit(formatted)

    def error(self, msg: str) -> None:
        """Log error message and persist to ~/.FileSling/logs/errors.json."""
        formatted = self._format_message("❌", msg, "#f48771")
        self.log_signal.emit(formatted)
        _write_error_log(msg)

    def warn(self, msg: str) -> None:
        """Log warning message."""
        formatted = self._format_message("⚠️", msg, "#ce9178")
        self.log_signal.emit(formatted)

    def start(self, msg: str) -> None:
        """Log start event."""
        formatted = self._format_message("▶️", msg, "#4ec9b0")
        self.log_signal.emit(formatted)

    def stop(self, msg: str) -> None:
        """Log stop event."""
        formatted = self._format_message("⏹️", msg, "#858585")
        self.log_signal.emit(formatted)

    def search(self, msg: str) -> None:
        """Log search/scan event."""
        formatted = self._format_message("🔍", msg, "#007acc")
        self.log_signal.emit(formatted)

    def upload(self, msg: str) -> None:
        """Log upload event."""
        formatted = self._format_message("⬆️", msg, "#007acc")
        self.log_signal.emit(formatted)

    def download(self, msg: str) -> None:
        """Log download event."""
        formatted = self._format_message("⬇️", msg, "#007acc")
        self.log_signal.emit(formatted)

    def trash(self, msg: str) -> None:
        """Log deletion event."""
        formatted = self._format_message("🗑️", msg, "#ce9178")
        self.log_signal.emit(formatted)

    def log(self, msg: str) -> None:
        """Emit raw message without formatting."""
        self.log_signal.emit(msg)


logger = Logger()
