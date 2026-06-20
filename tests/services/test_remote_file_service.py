"""
Unit tests for remote_file_service.

Tests connection-lost detection and safe wrappers for SFTP operations.
"""

from unittest.mock import MagicMock

import pytest

from src.models.errors import ConnectionLostError
from src.services.remote_file_service import (
    is_connection_lost_error,
    safe_listdir_attr,
    safe_mkdir,
    safe_remove,
    safe_rename,
    safe_rmdir,
    safe_stat,
)


# ---------------------------------------------------------------------------
# is_connection_lost_error
# ---------------------------------------------------------------------------


class TestIsConnectionLostError:
    def test_socket_is_closed(self):
        err = IOError("Socket is closed")
        assert is_connection_lost_error(err) is True

    def test_not_open(self):
        err = IOError("Channel is not open")
        assert is_connection_lost_error(err) is True

    def test_eof_transport(self):
        err = IOError("EOF during transport negotiation")
        assert is_connection_lost_error(err) is True

    def test_regular_io_error(self):
        err = IOError("No such file or directory")
        assert is_connection_lost_error(err) is False

    def test_permission_denied(self):
        err = IOError("Permission denied")
        assert is_connection_lost_error(err) is False

    def test_case_insensitive(self):
        err = IOError("SOCKET IS CLOSED")
        assert is_connection_lost_error(err) is True

    def test_not_open_variation(self):
        err = IOError("Connection not open anymore")
        assert is_connection_lost_error(err) is True


# ---------------------------------------------------------------------------
# safe_stat
# ---------------------------------------------------------------------------


class TestSafeStat:
    def test_success(self):
        sftp = MagicMock()
        stat_result = MagicMock(st_size=1024, st_mode=0o100644)
        sftp.stat.return_value = stat_result

        result = safe_stat(sftp, "/remote/file.mp4")
        assert result == stat_result
        sftp.stat.assert_called_once_with("/remote/file.mp4")

    def test_connection_lost_raises(self):
        sftp = MagicMock()
        sftp.stat.side_effect = IOError("Socket is closed")

        with pytest.raises(ConnectionLostError, match="Connection lost during stat"):
            safe_stat(sftp, "/remote/file.mp4")

    def test_regular_ioerror_propagates(self):
        sftp = MagicMock()
        sftp.stat.side_effect = IOError("No such file")

        with pytest.raises(IOError, match="No such file"):
            safe_stat(sftp, "/remote/nonexistent.mp4")


# ---------------------------------------------------------------------------
# safe_listdir_attr
# ---------------------------------------------------------------------------


class TestSafeListdirAttr:
    def test_success(self):
        sftp = MagicMock()
        items = [MagicMock(filename="a.mp4"), MagicMock(filename="b.mkv")]
        sftp.listdir_attr.return_value = items

        result = safe_listdir_attr(sftp, "/remote/Movies")
        assert result == items

    def test_connection_lost_raises(self):
        sftp = MagicMock()
        sftp.listdir_attr.side_effect = IOError("Socket is closed")

        with pytest.raises(ConnectionLostError, match="directory listing"):
            safe_listdir_attr(sftp, "/remote/Movies")

    def test_regular_ioerror_propagates(self):
        sftp = MagicMock()
        sftp.listdir_attr.side_effect = IOError("Permission denied")

        with pytest.raises(IOError, match="Permission denied"):
            safe_listdir_attr(sftp, "/remote/private")


# ---------------------------------------------------------------------------
# safe_rename
# ---------------------------------------------------------------------------


class TestSafeRename:
    def test_success(self):
        sftp = MagicMock()
        safe_rename(sftp, "/remote/old.mp4", "/remote/new.mp4")
        sftp.rename.assert_called_once_with("/remote/old.mp4", "/remote/new.mp4")

    def test_connection_lost_raises(self):
        sftp = MagicMock()
        sftp.rename.side_effect = IOError("Socket is closed")

        with pytest.raises(ConnectionLostError, match="rename"):
            safe_rename(sftp, "/remote/old.mp4", "/remote/new.mp4")

    def test_regular_ioerror_propagates(self):
        sftp = MagicMock()
        sftp.rename.side_effect = IOError("File exists")

        with pytest.raises(IOError, match="File exists"):
            safe_rename(sftp, "/remote/a.mp4", "/remote/b.mp4")


# ---------------------------------------------------------------------------
# safe_remove
# ---------------------------------------------------------------------------


class TestSafeRemove:
    def test_success(self):
        sftp = MagicMock()
        safe_remove(sftp, "/remote/trash.mp4")
        sftp.remove.assert_called_once_with("/remote/trash.mp4")

    def test_connection_lost_raises(self):
        sftp = MagicMock()
        sftp.remove.side_effect = IOError("Channel is not open")

        with pytest.raises(ConnectionLostError, match="file removal"):
            safe_remove(sftp, "/remote/trash.mp4")

    def test_regular_ioerror_propagates(self):
        sftp = MagicMock()
        sftp.remove.side_effect = IOError("Permission denied")

        with pytest.raises(IOError, match="Permission denied"):
            safe_remove(sftp, "/remote/protected.mp4")


# ---------------------------------------------------------------------------
# safe_rmdir
# ---------------------------------------------------------------------------


class TestSafeRmdir:
    def test_success(self):
        sftp = MagicMock()
        safe_rmdir(sftp, "/remote/empty_dir")
        sftp.rmdir.assert_called_once_with("/remote/empty_dir")

    def test_connection_lost_raises(self):
        sftp = MagicMock()
        sftp.rmdir.side_effect = IOError("Socket is closed")

        with pytest.raises(ConnectionLostError, match="directory removal"):
            safe_rmdir(sftp, "/remote/dir")

    def test_regular_ioerror_propagates(self):
        sftp = MagicMock()
        sftp.rmdir.side_effect = IOError("Directory not empty")

        with pytest.raises(IOError, match="Directory not empty"):
            safe_rmdir(sftp, "/remote/nonempty")


# ---------------------------------------------------------------------------
# safe_mkdir
# ---------------------------------------------------------------------------


class TestSafeMkdir:
    def test_success(self):
        sftp = MagicMock()
        safe_mkdir(sftp, "/remote/new_dir")
        sftp.mkdir.assert_called_once_with("/remote/new_dir")

    def test_connection_lost_raises(self):
        sftp = MagicMock()
        sftp.mkdir.side_effect = IOError("Socket is closed")

        with pytest.raises(ConnectionLostError, match="directory creation"):
            safe_mkdir(sftp, "/remote/new_dir")

    def test_regular_ioerror_propagates(self):
        sftp = MagicMock()
        sftp.mkdir.side_effect = IOError("File exists")

        with pytest.raises(IOError, match="File exists"):
            safe_mkdir(sftp, "/remote/existing")
