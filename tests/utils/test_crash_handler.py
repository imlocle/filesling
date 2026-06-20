"""
Unit tests for utils/crash_handler.py.

Tests crash log writing, detection, and cleanup without showing dialogs.
"""

from pathlib import Path
from unittest.mock import patch

from src.utils.crash_handler import (
    check_previous_crash,
    clear_crash_log,
    get_previous_crash_report,
    write_crash_log,
)


class TestWriteCrashLog:
    def test_writes_report(self, tmp_path):
        """Should write a formatted crash report to disk."""
        log_path = tmp_path / "crash.log"
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            try:
                raise ValueError("test error")
            except ValueError:
                import sys

                exc_type, exc_value, exc_tb = sys.exc_info()
                report = write_crash_log(exc_type, exc_value, exc_tb)

        assert "FileSling Crash Report" in report
        assert "ValueError" in report
        assert "test error" in report
        assert log_path.exists()
        assert "test error" in log_path.read_text()

    def test_report_contains_metadata(self, tmp_path):
        """Report should contain version, python, and platform info."""
        log_path = tmp_path / "crash.log"
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                import sys

                exc_type, exc_value, exc_tb = sys.exc_info()
                report = write_crash_log(exc_type, exc_value, exc_tb)

        assert "Version:" in report
        assert "Python:" in report
        assert "Platform:" in report

    def test_handles_write_failure(self, tmp_path):
        """Should not raise even if writing to disk fails."""
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", Path("/nonexistent/dir/crash.log")):
            try:
                raise RuntimeError("fail")
            except RuntimeError:
                import sys

                exc_type, exc_value, exc_tb = sys.exc_info()
                # Should not raise
                report = write_crash_log(exc_type, exc_value, exc_tb)
                assert "RuntimeError" in report


class TestCheckPreviousCrash:
    def test_returns_true_when_log_exists(self, tmp_path):
        log_path = tmp_path / "crash.log"
        log_path.write_text("crash data")
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            assert check_previous_crash() is True

    def test_returns_false_when_no_log(self, tmp_path):
        log_path = tmp_path / "crash.log"
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            assert check_previous_crash() is False


class TestGetPreviousCrashReport:
    def test_reads_report(self, tmp_path):
        log_path = tmp_path / "crash.log"
        log_path.write_text("crash details here")
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            assert get_previous_crash_report() == "crash details here"

    def test_returns_empty_on_missing_file(self, tmp_path):
        log_path = tmp_path / "nonexistent.log"
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            assert get_previous_crash_report() == ""


class TestClearCrashLog:
    def test_removes_log(self, tmp_path):
        log_path = tmp_path / "crash.log"
        log_path.write_text("old crash")
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            clear_crash_log()
        assert not log_path.exists()

    def test_no_error_on_missing_file(self, tmp_path):
        log_path = tmp_path / "nonexistent.log"
        with patch("src.utils.crash_handler.CRASH_LOG_PATH", log_path):
            # Should not raise
            clear_crash_log()
