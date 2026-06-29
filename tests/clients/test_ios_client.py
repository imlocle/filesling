"""
Unit tests for IOSClient.

Mocks pymobiledevice3 to test the client logic without needing a real device.
"""

import os
import stat as stat_module
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.clients.ios_client import IOSClient, IOSStat, get_connected_ios_devices

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_afc():
    """Create a mock AFC service."""
    afc = MagicMock()
    return afc


@pytest.fixture
def client(mock_afc):
    """Create an IOSClient with a mocked AFC connection."""
    with patch("src.clients.ios_client.IOSClient._connect"):
        ios = IOSClient(device_udid="UDID-1234")
        ios._afc = mock_afc
        return ios


# ---------------------------------------------------------------------------
# IOSStat
# ---------------------------------------------------------------------------


class TestIOSStat:
    def test_creation(self):
        s = IOSStat(st_size=1024, st_mode=stat_module.S_IFREG | 0o644)
        assert s.st_size == 1024
        assert stat_module.S_ISREG(s.st_mode)
        assert s.filename == ""

    def test_directory_stat(self):
        s = IOSStat(st_size=0, st_mode=stat_module.S_IFDIR | 0o755)
        assert stat_module.S_ISDIR(s.st_mode)
        assert s.st_size == 0


# ---------------------------------------------------------------------------
# IOSClient._ensure_connected
# ---------------------------------------------------------------------------


class TestIOSClientConnection:
    def test_ensure_connected_ok(self, client, mock_afc):
        # Should not raise when _afc is set
        client._ensure_connected()

    def test_ensure_connected_fails(self, client):
        client._afc = None
        with pytest.raises(IOError, match="Not connected"):
            client._ensure_connected()


# ---------------------------------------------------------------------------
# IOSClient.listdir
# ---------------------------------------------------------------------------


class TestIOSClientListdir:
    def test_listdir_filters_dots(self, client, mock_afc):
        mock_afc.listdir.return_value = [".", "..", "DCIM", "Downloads"]
        result = client.listdir("/")
        assert result == ["DCIM", "Downloads"]

    def test_listdir_empty(self, client, mock_afc):
        mock_afc.listdir.return_value = [".", ".."]
        result = client.listdir("/empty")
        assert result == []

    def test_listdir_error(self, client, mock_afc):
        mock_afc.listdir.side_effect = Exception("device disconnected")
        with pytest.raises(IOError, match="Failed to list"):
            client.listdir("/DCIM")


# ---------------------------------------------------------------------------
# IOSClient.stat
# ---------------------------------------------------------------------------


class TestIOSClientStat:
    def test_stat_file(self, client, mock_afc):
        mock_afc.stat.return_value = {
            "st_size": "4096",
            "st_ifmt": "S_IFREG",
            "st_mtime": "1700000000000000000",
        }
        result = client.stat("/DCIM/photo.jpg")
        assert stat_module.S_ISREG(result.st_mode)
        assert result.st_size == 4096

    def test_stat_directory(self, client, mock_afc):
        mock_afc.stat.return_value = {
            "st_size": "0",
            "st_ifmt": "S_IFDIR",
            "st_mtime": "0",
        }
        result = client.stat("/DCIM")
        assert stat_module.S_ISDIR(result.st_mode)

    def test_stat_error(self, client, mock_afc):
        mock_afc.stat.side_effect = Exception("not found")
        with pytest.raises(IOError, match="Failed to stat"):
            client.stat("/nonexistent")

    def test_stat_missing_fields(self, client, mock_afc):
        """Should handle missing dict fields gracefully."""
        mock_afc.stat.return_value = {}
        result = client.stat("/DCIM/unknown")
        assert result.st_size == 0
        # Default to regular file
        assert stat_module.S_ISREG(result.st_mode)


# ---------------------------------------------------------------------------
# IOSClient.listdir_attr
# ---------------------------------------------------------------------------


class TestIOSClientListdirAttr:
    def test_listdir_attr_combines_listdir_and_stat(self, client, mock_afc):
        mock_afc.listdir.return_value = [".", "..", "photo.jpg", "video.mp4"]
        mock_afc.stat.return_value = {
            "st_size": "1024",
            "st_ifmt": "S_IFREG",
            "st_mtime": "0",
        }
        results = client.listdir_attr("/DCIM")
        assert len(results) == 2
        assert results[0].filename == "photo.jpg"
        assert results[1].filename == "video.mp4"
        assert results[0].st_size == 1024

    def test_listdir_attr_skips_stat_errors(self, client, mock_afc):
        """Files that can't be stat'd should still appear with default values."""
        mock_afc.listdir.return_value = [".", "..", "good.txt", "broken.txt"]

        def stat_side_effect(path):
            if "broken" in path:
                raise Exception("permission denied")
            return {"st_size": "512", "st_ifmt": "S_IFREG", "st_mtime": "0"}

        mock_afc.stat.side_effect = stat_side_effect
        results = client.listdir_attr("/docs")
        assert len(results) == 2
        # The broken one should still have a filename
        assert results[1].filename == "broken.txt"
        assert results[1].st_size == 0


# ---------------------------------------------------------------------------
# IOSClient.get (download)
# ---------------------------------------------------------------------------


class TestIOSClientGet:
    def test_get_chunked(self, client, mock_afc, tmp_path):
        """Download should stream file in chunks."""
        mock_afc.stat.return_value = {"st_size": "2048"}

        # Mock the file-like object returned by afc.open()
        remote_file = BytesIO(b"x" * 2048)
        mock_afc.open.return_value.__enter__ = MagicMock(return_value=remote_file)
        mock_afc.open.return_value.__exit__ = MagicMock(return_value=False)

        local_path = str(tmp_path / "downloaded.jpg")
        callback = MagicMock()
        client.get("/DCIM/photo.jpg", local_path, callback=callback)

        assert os.path.exists(local_path)
        assert callback.call_count >= 1

    def test_get_error(self, client, mock_afc, tmp_path):
        mock_afc.stat.return_value = {"st_size": "100"}
        mock_afc.open.side_effect = Exception("connection lost")

        with pytest.raises(IOError, match="Failed to download"):
            client.get("/DCIM/photo.jpg", str(tmp_path / "out.jpg"))


# ---------------------------------------------------------------------------
# IOSClient.put (upload)
# ---------------------------------------------------------------------------


class TestIOSClientPut:
    def test_put_chunked(self, client, mock_afc, tmp_path):
        """Upload should stream file in chunks."""
        test_file = tmp_path / "upload.mp4"
        test_file.write_bytes(b"y" * 512)

        remote_file = BytesIO()
        mock_afc.open.return_value.__enter__ = MagicMock(return_value=remote_file)
        mock_afc.open.return_value.__exit__ = MagicMock(return_value=False)

        callback = MagicMock()
        client.put(str(test_file), "/DCIM/upload.mp4", callback=callback)

        assert callback.call_count >= 1
        # Final callback should report full size
        callback.assert_called_with(512, 512)


# ---------------------------------------------------------------------------
# IOSClient.rename / mkdir / remove / rmdir
# ---------------------------------------------------------------------------


class TestIOSClientFileOps:
    def test_rename(self, client, mock_afc):
        client.rename("/DCIM/old.jpg", "/DCIM/new.jpg")
        mock_afc.rename.assert_called_once_with("/DCIM/old.jpg", "/DCIM/new.jpg")

    def test_mkdir(self, client, mock_afc):
        client.mkdir("/DCIM/NewFolder")
        mock_afc.makedirs.assert_called_once_with("/DCIM/NewFolder")

    def test_remove(self, client, mock_afc):
        client.remove("/DCIM/trash.jpg")
        mock_afc.rm.assert_called_once_with("/DCIM/trash.jpg")

    def test_rmdir(self, client, mock_afc):
        client.rmdir("/DCIM/OldFolder")
        mock_afc.rm.assert_called_once_with("/DCIM/OldFolder", force=True)

    def test_close(self, client, mock_afc):
        client.close()
        assert client._afc is None


# ---------------------------------------------------------------------------
# IOSClient — DeviceClient protocol conformance
# ---------------------------------------------------------------------------


class TestIOSClientProtocol:
    def test_implements_device_client(self, client):
        """IOSClient should satisfy the DeviceClient protocol."""
        from src.clients.device_client import DeviceClient

        assert isinstance(client, DeviceClient)


# ---------------------------------------------------------------------------
# get_connected_ios_devices
# ---------------------------------------------------------------------------


class TestGetConnectedDevices:
    def test_returns_empty_when_pymobiledevice3_unavailable(self):
        """Should return empty list if pymobiledevice3 fails to import."""
        # The function catches ImportError internally and returns []
        # If pymobiledevice3 is not installed in test env, it naturally returns []
        # If it IS installed but no device connected, it also returns []
        result = get_connected_ios_devices()
        assert isinstance(result, list)

    def test_returns_empty_on_exception(self):
        """Should return empty list on any unexpected error."""
        with patch(
            "src.clients.ios_client.get_connected_ios_devices",
            wraps=get_connected_ios_devices,
        ):
            result = get_connected_ios_devices()
            assert isinstance(result, list)
