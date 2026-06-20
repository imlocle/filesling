"""
Unit tests for ADBClient.

Mocks subprocess calls to test the client logic without needing a real device.
"""

import stat
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.clients.adb_client import (
    ADBClient,
    ADBSession,
    ADBStat,
    connect_wifi,
    get_adb_path,
    get_connected_devices,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_adb_path():
    """Mock get_adb_path so ADBClient can be instantiated."""
    with patch("src.clients.adb_client.get_adb_path", return_value="/usr/local/bin/adb"):
        yield


@pytest.fixture
def client(mock_adb_path):
    """Create an ADBClient with a mocked adb path."""
    return ADBClient(device_id="ABC123")


@pytest.fixture
def client_no_device(mock_adb_path):
    """Create an ADBClient without a specific device ID."""
    return ADBClient(device_id=None)


# ---------------------------------------------------------------------------
# ADBClient.__init__
# ---------------------------------------------------------------------------


class TestADBClientInit:
    def test_with_device_id(self, mock_adb_path):
        client = ADBClient(device_id="DEVICE1")
        assert client.device_id == "DEVICE1"
        assert client._adb_prefix == ["/usr/local/bin/adb", "-s", "DEVICE1"]

    def test_without_device_id(self, mock_adb_path):
        client = ADBClient(device_id=None)
        assert client.device_id is None
        assert client._adb_prefix == ["/usr/local/bin/adb"]


# ---------------------------------------------------------------------------
# ADBClient._run
# ---------------------------------------------------------------------------


class TestADBClientRun:
    def test_run_success(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="output\n", stderr="")
            result = client._run(["devices"])
            assert result == "output\n"
            mock_run.assert_called_once_with(
                ["/usr/local/bin/adb", "-s", "ABC123", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_run_error(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="device offline")
            with pytest.raises(IOError, match="adb error: device offline"):
                client._run(["shell", "ls"])

    def test_run_timeout(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="adb", timeout=10)
            with pytest.raises(IOError, match="timed out"):
                client._run(["shell", "ls"])

    def test_run_not_found(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(IOError, match="adb not found"):
                client._run(["devices"])


# ---------------------------------------------------------------------------
# ADBClient._normalize_remote_path
# ---------------------------------------------------------------------------


class TestNormalizePath:
    def test_strips_whitespace(self, client):
        assert client._normalize_remote_path("  /sdcard/  ") == "/sdcard/"

    def test_collapses_double_slashes(self, client):
        assert client._normalize_remote_path("/sdcard//Download") == "/sdcard/Download"

    def test_multiple_double_slashes(self, client):
        assert client._normalize_remote_path("//a//b//c") == "/a/b/c"

    def test_normal_path_unchanged(self, client):
        assert client._normalize_remote_path("/sdcard/Movies") == "/sdcard/Movies"


# ---------------------------------------------------------------------------
# ADBClient.listdir
# ---------------------------------------------------------------------------


class TestADBClientListdir:
    def test_listdir(self, client):
        with patch.object(client, "_shell", return_value="file1.mp4\nfile2.mkv\n"):
            result = client.listdir("/sdcard/Movies")
            assert result == ["file1.mp4", "file2.mkv"]

    def test_listdir_empty(self, client):
        with patch.object(client, "_shell", return_value=""):
            result = client.listdir("/sdcard/Empty")
            assert result == []

    def test_listdir_strips_blank_lines(self, client):
        with patch.object(client, "_shell", return_value="a.txt\n\nb.txt\n\n"):
            result = client.listdir("/sdcard")
            assert result == ["a.txt", "b.txt"]


# ---------------------------------------------------------------------------
# ADBClient.stat
# ---------------------------------------------------------------------------


class TestADBClientStat:
    def test_stat_directory(self, client):
        with patch.object(client, "_shell", return_value="dir"):
            result = client.stat("/sdcard/Movies")
            assert stat.S_ISDIR(result.st_mode)
            assert result.st_size == 0

    def test_stat_file_with_size(self, client):
        with patch.object(client, "_shell", return_value="1048576"):
            result = client.stat("/sdcard/movie.mp4")
            assert stat.S_ISREG(result.st_mode)
            assert result.st_size == 1048576

    def test_stat_file_unknown_size(self, client):
        with patch.object(client, "_shell", return_value="0"):
            result = client.stat("/sdcard/unknown.bin")
            assert stat.S_ISREG(result.st_mode)
            assert result.st_size == 0

    def test_stat_missing_file(self, client):
        with patch.object(client, "_shell", return_value="missing"):
            with pytest.raises(FileNotFoundError, match="does not exist"):
                client.stat("/sdcard/nonexistent.txt")

    def test_stat_normalizes_path(self, client):
        with patch.object(client, "_shell", return_value="dir") as mock_shell:
            client.stat("  /sdcard//Movies  ")
            # The command should use the normalized path
            call_args = mock_shell.call_args[0][0]
            assert "//" not in call_args


# ---------------------------------------------------------------------------
# ADBClient.rename / remove / rmdir / mkdir
# ---------------------------------------------------------------------------


class TestADBClientFileOps:
    def test_rename(self, client):
        with patch.object(client, "_shell") as mock_shell:
            client.rename("/sdcard/old.mp4", "/sdcard/new.mp4")
            cmd = mock_shell.call_args[0][0]
            assert "mv" in cmd
            assert "old.mp4" in cmd
            assert "new.mp4" in cmd

    def test_remove(self, client):
        with patch.object(client, "_shell") as mock_shell:
            client.remove("/sdcard/trash.txt")
            cmd = mock_shell.call_args[0][0]
            assert "rm -f" in cmd

    def test_rmdir_directory(self, client):
        with patch.object(client, "stat") as mock_stat:
            mock_stat.return_value = ADBStat(
                st_mode=stat.S_IFDIR | 0o755, st_size=0
            )
            with patch.object(client, "_shell") as mock_shell:
                client.rmdir("/sdcard/old_folder")
                cmd = mock_shell.call_args[0][0]
                assert "rm -rf" in cmd

    def test_rmdir_file_fallback(self, client):
        """rmdir on a file should use rm -f (not rm -rf)."""
        with patch.object(client, "stat") as mock_stat:
            mock_stat.return_value = ADBStat(
                st_mode=stat.S_IFREG | 0o644, st_size=100
            )
            with patch.object(client, "_shell") as mock_shell:
                client.rmdir("/sdcard/not_a_dir.txt")
                cmd = mock_shell.call_args[0][0]
                assert "rm -f" in cmd
                assert "rm -rf" not in cmd

    def test_rmdir_missing_file(self, client):
        """rmdir on a missing path should silently return."""
        with patch.object(client, "stat") as mock_stat:
            mock_stat.side_effect = FileNotFoundError("nope")
            # Should not raise
            client.rmdir("/sdcard/gone")

    def test_mkdir(self, client):
        with patch.object(client, "_shell") as mock_shell:
            client.mkdir("/sdcard/new_dir")
            cmd = mock_shell.call_args[0][0]
            assert "mkdir -p" in cmd


# ---------------------------------------------------------------------------
# ADBClient.put / get
# ---------------------------------------------------------------------------


class TestADBClientTransfers:
    def test_put(self, client, tmp_path):
        test_file = tmp_path / "upload.mp4"
        test_file.write_bytes(b"x" * 1024)

        with patch.object(client, "_run") as mock_run:
            callback = MagicMock()
            client.put(str(test_file), "/sdcard/upload.mp4", callback=callback)

            # Should call adb push
            args = mock_run.call_args[0][0]
            assert "push" in args
            assert str(test_file) in args

            # Callback fired at start (0) and end (total)
            assert callback.call_count == 2
            callback.assert_any_call(0, 1024)
            callback.assert_any_call(1024, 1024)

    def test_get(self, client, tmp_path):
        local_dest = str(tmp_path / "downloaded.mp4")

        with patch.object(client, "stat") as mock_stat:
            mock_stat.return_value = ADBStat(
                st_mode=stat.S_IFREG | 0o644, st_size=2048
            )
            with patch.object(client, "_run") as mock_run:
                callback = MagicMock()
                client.get("/sdcard/video.mp4", local_dest, callback=callback)

                args = mock_run.call_args[0][0]
                assert "pull" in args

                assert callback.call_count == 2
                callback.assert_any_call(0, 2048)
                callback.assert_any_call(2048, 2048)

    def test_put_no_callback(self, client, tmp_path):
        test_file = tmp_path / "file.txt"
        test_file.write_bytes(b"data")

        with patch.object(client, "_run"):
            # Should not raise
            client.put(str(test_file), "/sdcard/file.txt", callback=None)


# ---------------------------------------------------------------------------
# ADBClient compatibility stubs
# ---------------------------------------------------------------------------


class TestADBClientCompat:
    def test_get_channel_returns_self(self, client):
        assert client.get_channel() is client

    def test_get_transport_returns_self(self, client):
        assert client.get_transport() is client

    def test_open_session_returns_adb_session(self, client):
        session = client.open_session()
        assert isinstance(session, ADBSession)

    def test_close_is_noop(self, client):
        # Should not raise
        client.close()


# ---------------------------------------------------------------------------
# ADBSession
# ---------------------------------------------------------------------------


class TestADBSession:
    def test_exec_command(self, client):
        session = ADBSession(client)
        with patch.object(client, "_shell", return_value="hello\n"):
            session.exec_command("echo hello")
            assert session.recv(1024) == b"hello\n"

    def test_exec_command_failure(self, client):
        """When _shell raises, exec_command propagates the error."""
        session = ADBSession(client)
        with patch.object(client, "_shell", side_effect=IOError("device offline")):
            with pytest.raises(IOError, match="device offline"):
                session.exec_command("ls")

    def test_close(self, client):
        session = ADBSession(client)
        # Should not raise
        session.close()


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    def test_get_adb_path_found(self):
        with patch("shutil.which", return_value="/usr/local/bin/adb"):
            result = get_adb_path()
            assert result == "/usr/local/bin/adb"

    def test_get_adb_path_not_found(self):
        with patch("shutil.which", return_value=None):
            with patch("os.path.exists", return_value=False):
                with pytest.raises(IOError):
                    get_adb_path()

    def test_get_connected_devices(self):
        adb_output = (
            "List of devices attached\n"
            "ABC123\tdevice\n"
            "DEF456\tdevice\n"
            "\n"
        )
        with patch("src.clients.adb_client.get_adb_path", return_value="/usr/local/bin/adb"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=adb_output, stderr=""
                )
                devices = get_connected_devices()
                assert len(devices) == 2
                assert devices[0]["id"] == "ABC123"
                assert devices[1]["id"] == "DEF456"

    def test_get_connected_devices_empty(self):
        adb_output = "List of devices attached\n\n"
        with patch("src.clients.adb_client.get_adb_path", return_value="/usr/local/bin/adb"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=adb_output, stderr=""
                )
                devices = get_connected_devices()
                assert devices == []

    def test_connect_wifi_success(self):
        with patch("src.clients.adb_client.get_adb_path", return_value="/usr/local/bin/adb"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="connected to 192.168.1.50:5555", stderr=""
                )
                result = connect_wifi("192.168.1.50")
                assert result is True

    def test_connect_wifi_failure(self):
        with patch("src.clients.adb_client.get_adb_path", return_value="/usr/local/bin/adb"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="failed to connect", stderr=""
                )
                result = connect_wifi("192.168.1.99")
                assert result is False
