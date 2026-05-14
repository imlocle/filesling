import json
import os
import traceback
from datetime import datetime

from PySide6.QtCore import QObject, Signal

# Logs directory path (relative to project root)
_LOGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
)


def _ensure_logs_dir():
    """Create logs directory if it doesn't exist."""
    os.makedirs(_LOGS_DIR, exist_ok=True)


def _write_error_log(msg: str):
    """Append an error entry to the JSON log file."""
    try:
        _ensure_logs_dir()
        log_file = os.path.join(_LOGS_DIR, "errors.json")

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

        # Keep last 500 entries to prevent unbounded growth
        entries = entries[-500:]

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

    Errors are also persisted to logs/errors.json.
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

    def info(self, msg: str):
        """Log informational message."""
        formatted = self._format_message("ℹ️", msg, "#4ec9b0")
        self.log_signal.emit(formatted)

    def success(self, msg: str):
        """Log success message."""
        formatted = self._format_message("✅", msg, "#4ec9b0")
        self.log_signal.emit(formatted)

    def error(self, msg: str):
        """Log error message and persist to logs/errors.json."""
        formatted = self._format_message("❌", msg, "#f48771")
        self.log_signal.emit(formatted)
        _write_error_log(msg)

    def warn(self, msg: str):
        """Log warning message."""
        formatted = self._format_message("⚠️", msg, "#ce9178")
        self.log_signal.emit(formatted)

    def start(self, msg: str):
        """Log start event."""
        formatted = self._format_message("▶️", msg, "#4ec9b0")
        self.log_signal.emit(formatted)

    def stop(self, msg: str):
        """Log stop event."""
        formatted = self._format_message("⏹️", msg, "#858585")
        self.log_signal.emit(formatted)

    def search(self, msg: str):
        """Log search/scan event."""
        formatted = self._format_message("🔍", msg, "#007acc")
        self.log_signal.emit(formatted)

    def upload(self, msg: str):
        """Log upload event."""
        formatted = self._format_message("⬆️", msg, "#007acc")
        self.log_signal.emit(formatted)

    def download(self, msg: str):
        """Log download event."""
        formatted = self._format_message("⬇️", msg, "#007acc")
        self.log_signal.emit(formatted)

    def trash(self, msg: str):
        """Log deletion event."""
        formatted = self._format_message("🗑️", msg, "#ce9178")
        self.log_signal.emit(formatted)

    def log(self, msg: str):
        """Emit raw message without formatting."""
        self.log_signal.emit(msg)


logger = Logger()
