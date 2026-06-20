"""
Tests for the macOS Keychain service.
"""

from unittest.mock import MagicMock, patch

from src.services.keychain_service import (
    delete_password,
    has_stored_password,
    retrieve_password,
    store_password,
)


class TestStorePassword:
    @patch("src.services.keychain_service.subprocess.Popen")
    @patch("src.services.keychain_service.subprocess.run")
    def test_store_success(self, mock_run, mock_popen):
        mock_run.return_value = MagicMock(returncode=0)
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        result = store_password("user@host", "secret123")
        assert result is True
        assert mock_run.call_count == 1  # delete
        assert mock_popen.call_count == 1  # add (via Popen)

    @patch("src.services.keychain_service.subprocess.run")
    def test_store_failure(self, mock_run):
        # First call (delete) succeeds, second (add) fails
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="error"),
        ]
        result = store_password("user@host", "secret123")
        assert result is False

    @patch("src.services.keychain_service.subprocess.run")
    def test_store_handles_exception(self, mock_run):
        mock_run.side_effect = OSError("command not found")
        result = store_password("user@host", "secret123")
        assert result is False


class TestRetrievePassword:
    @patch("src.services.keychain_service.subprocess.run")
    def test_retrieve_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="secret123\n")
        result = retrieve_password("user@host")
        assert result == "secret123"

    @patch("src.services.keychain_service.subprocess.run")
    def test_retrieve_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44)
        result = retrieve_password("user@host")
        assert result is None

    @patch("src.services.keychain_service.subprocess.run")
    def test_retrieve_handles_exception(self, mock_run):
        mock_run.side_effect = OSError("command not found")
        result = retrieve_password("user@host")
        assert result is None


class TestDeletePassword:
    @patch("src.services.keychain_service.subprocess.run")
    def test_delete_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = delete_password("user@host")
        assert result is True

    @patch("src.services.keychain_service.subprocess.run")
    def test_delete_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44)
        result = delete_password("user@host")
        assert result is False

    @patch("src.services.keychain_service.subprocess.run")
    def test_delete_handles_exception(self, mock_run):
        mock_run.side_effect = OSError("command not found")
        result = delete_password("user@host")
        assert result is False


class TestHasStoredPassword:
    @patch("src.services.keychain_service.subprocess.run")
    def test_has_password(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="secret\n")
        assert has_stored_password("user@host") is True

    @patch("src.services.keychain_service.subprocess.run")
    def test_no_password(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44)
        assert has_stored_password("user@host") is False
