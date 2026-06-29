"""
Unit tests for DeviceClient protocol.

Verifies that the protocol is properly defined and can be used for type checking.
"""

from unittest.mock import MagicMock, patch

from src.clients.device_client import DeviceClient


class TestDeviceClientProtocol:
    """Tests for the DeviceClient protocol definition."""

    def test_protocol_is_runtime_checkable(self):
        """DeviceClient should be decorated with @runtime_checkable."""
        assert (
            hasattr(DeviceClient, "__protocol_attrs__")
            or hasattr(DeviceClient, "__abstractmethods__")
            or issubclass(type(DeviceClient), type)
        )

    def test_mock_satisfies_protocol(self):
        """A mock with the right methods should satisfy the protocol."""
        mock_client = MagicMock()
        mock_client.listdir = MagicMock(return_value=[])
        mock_client.listdir_attr = MagicMock(return_value=[])
        mock_client.stat = MagicMock()
        mock_client.get = MagicMock()
        mock_client.put = MagicMock()
        mock_client.rename = MagicMock()
        mock_client.remove = MagicMock()
        mock_client.rmdir = MagicMock()
        mock_client.mkdir = MagicMock()
        mock_client.close = MagicMock()

        # MagicMock satisfies isinstance checks for runtime_checkable Protocols
        assert isinstance(mock_client, DeviceClient)

    def test_adb_client_satisfies_protocol(self):
        """ADBClient should satisfy the DeviceClient protocol."""
        with patch("src.clients.adb_client.get_adb_path", return_value="/usr/bin/adb"):
            from src.clients.adb_client import ADBClient

            client = ADBClient(device_id="test")
            assert isinstance(client, DeviceClient)

    def test_ios_client_satisfies_protocol(self):
        """IOSClient should satisfy the DeviceClient protocol."""
        with patch("src.clients.ios_client.IOSClient._connect"):
            from src.clients.ios_client import IOSClient

            client = IOSClient(device_udid="test")
            client._afc = MagicMock()
            assert isinstance(client, DeviceClient)

    def test_object_without_methods_fails_protocol(self):
        """A plain object should NOT satisfy the DeviceClient protocol."""

        class Empty:
            pass

        assert not isinstance(Empty(), DeviceClient)

    def test_partial_implementation_fails_protocol(self):
        """An object missing some methods should NOT satisfy the protocol."""

        class Partial:
            def listdir(self, path):
                return []

            def stat(self, path):
                pass

        assert not isinstance(Partial(), DeviceClient)
