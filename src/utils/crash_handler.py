"""
Crash handler — catches unhandled exceptions and shows a user-friendly dialog.

- Writes crash details to ~/.Shuttle/crash.log
- Shows a dialog with error info and a "Copy to Clipboard" button
- On next launch, detects if the previous session crashed
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

from src.utils.constants import GITHUB_REPO_URL, SOFTWARE_NAME, VERSION

CRASH_LOG_PATH = Path.home() / f".{SOFTWARE_NAME}" / "crash.log"


def write_crash_log(exc_type, exc_value, exc_tb) -> str:
    """Write crash details to file and return the formatted report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    report = (
        f"Shuttle Crash Report\n"
        f"{'=' * 50}\n"
        f"Version: {VERSION}\n"
        f"Time: {timestamp}\n"
        f"Python: {sys.version}\n"
        f"Platform: {sys.platform}\n"
        f"{'=' * 50}\n\n"
        f"{tb_text}"
    )

    try:
        CRASH_LOG_PATH.parent.mkdir(exist_ok=True)
        with open(CRASH_LOG_PATH, "w") as f:
            f.write(report)
    except Exception:
        pass  # Can't write log — still show the dialog

    return report


def show_crash_dialog(report: str) -> None:
    """Show a crash dialog with the error details."""
    try:
        from PySide6.QtWidgets import (
            QApplication,
            QDialog,
            QHBoxLayout,
            QLabel,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
        )

        # Ensure QApplication exists
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)

        dialog = QDialog()
        dialog.setWindowTitle(f"{SOFTWARE_NAME} — Unexpected Error")
        dialog.setMinimumSize(500, 350)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("Shuttle encountered an unexpected error and needs to close.")
        header.setStyleSheet("font-size: 14px; font-weight: 600;")
        header.setWordWrap(True)
        layout.addWidget(header)

        subtitle = QLabel(
            "The error details are below. You can copy them to report the issue."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #888;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Error text
        text_box = QPlainTextEdit()
        text_box.setPlainText(report)
        text_box.setReadOnly(True)
        text_box.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(text_box)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        report_btn = QPushButton("🐛 Report on GitHub")
        report_btn.clicked.connect(lambda: _open_github_issue(report))
        btn_layout.addWidget(report_btn)

        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(report))
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.exec()

    except Exception:
        # If even the dialog fails, print to stderr
        print(report, file=sys.stderr)


def _open_github_issue(report: str) -> None:
    """Open a pre-filled GitHub issue in the user's browser."""
    import urllib.parse
    import webbrowser

    # Truncate report for URL length limits (~2000 chars safe for URLs)
    short_report = report[:1500]
    if len(report) > 1500:
        short_report += "\n\n... (truncated — full report copied to clipboard)"

    title = "Crash Report"
    # Extract the actual error line for the title
    lines = report.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line and not line.startswith("File") and not line.startswith("Traceback"):
            title = f"Crash: {line[:80]}"
            break

    body = (
        "## Crash Report\n\n"
        "**What I was doing when it crashed:**\n"
        "(Please describe briefly)\n\n"
        "**Crash details:**\n"
        f"```\n{short_report}\n```\n"
    )

    params = urllib.parse.urlencode({"title": title, "body": body})
    url = f"{GITHUB_REPO_URL}/issues/new?{params}"
    webbrowser.open(url)


def install_crash_handler() -> None:
    """Install the global exception handler."""

    def handler(exc_type, exc_value, exc_tb):
        # Don't catch KeyboardInterrupt
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        report = write_crash_log(exc_type, exc_value, exc_tb)
        show_crash_dialog(report)
        sys.exit(1)

    sys.excepthook = handler


def check_previous_crash() -> bool:
    """Check if the previous session crashed. Returns True if crash log exists."""
    return CRASH_LOG_PATH.exists()


def get_previous_crash_report() -> str:
    """Read the previous crash report."""
    try:
        return CRASH_LOG_PATH.read_text()
    except Exception:
        return ""


def clear_crash_log() -> None:
    """Remove the crash log after it's been acknowledged."""
    try:
        CRASH_LOG_PATH.unlink(missing_ok=True)
    except Exception:
        pass
