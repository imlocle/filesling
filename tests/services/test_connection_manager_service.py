"""
Tests for the connection manager service.
"""

from unittest.mock import MagicMock

import pytest

from src.services.connection_manager_service import ConnectionManagerService


class TestConnectionManagerService:
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.host = "192.168.1.100"
        settings.username = "testuser"
        settings.ssh_key_path = "/tmp/fake_key"
        settings.ssh_port = 22
        settings.config.current_server_id = "test-server"
        settings.get_server.return_value = {
            "connection_type": "ssh",
            "username": "testuser",
            "host": "192.168.1.100",
        }
        return settings

    @pytest.fixture
    def service(self, mock_settings):
        return ConnectionManagerService(mock_settings)

    def test_initial_state(self, service):
        assert service.ssh_client is None
        assert service.sftp_client is None
        assert service.is_connected() is False

    def test_check_alive_when_disconnected(self, service):
        assert service.check_alive() is False

    def test_measure_latency_when_disconnected(self, service):
        assert service.measure_latency() == -1.0

    def test_disconnect_when_not_connected(self, service):
        # Should not raise
        service.disconnect()
        assert service.is_connected() is False

    def test_is_connected_with_clients(self, service):
        service.ssh_client = MagicMock()
        service.sftp_client = MagicMock()
        assert service.is_connected() is True

    def test_check_alive_with_active_transport(self, service):
        mock_ssh = MagicMock()
        mock_transport = MagicMock()
        mock_transport.is_active.return_value = True
        mock_ssh.get_transport.return_value = mock_transport
        service.ssh_client = mock_ssh
        service.sftp_client = MagicMock()

        assert service.check_alive() is True
        mock_transport.send_ignore.assert_called_once()

    def test_check_alive_with_dead_transport(self, service):
        mock_ssh = MagicMock()
        mock_transport = MagicMock()
        mock_transport.is_active.return_value = False
        mock_ssh.get_transport.return_value = mock_transport
        service.ssh_client = mock_ssh
        service.sftp_client = MagicMock()

        assert service.check_alive() is False

    def test_check_alive_with_exception(self, service):
        mock_ssh = MagicMock()
        mock_ssh.get_transport.side_effect = Exception("broken")
        service.ssh_client = mock_ssh
        service.sftp_client = MagicMock()

        assert service.check_alive() is False

    def test_measure_latency_success(self, service):
        mock_sftp = MagicMock()
        mock_sftp.stat.return_value = MagicMock()
        service.sftp_client = mock_sftp

        latency = service.measure_latency()
        assert latency >= 0
        mock_sftp.stat.assert_called_once_with(".")

    def test_disconnect_closes_clients(self, service):
        mock_sftp = MagicMock()
        mock_ssh = MagicMock()
        service.ssh_client = mock_ssh
        service.sftp_client = mock_sftp

        service.disconnect()

        mock_sftp.close.assert_called_once()
        mock_ssh.close.assert_called_once()
        assert service.ssh_client is None
        assert service.sftp_client is None

    def test_disconnect_handles_close_errors(self, service):
        mock_sftp = MagicMock()
        mock_sftp.close.side_effect = Exception("already closed")
        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = Exception("already closed")
        service.ssh_client = mock_ssh
        service.sftp_client = mock_sftp

        # Should not raise
        service.disconnect()
        assert service.ssh_client is None
        assert service.sftp_client is None

    def test_open_sftp_session_without_ssh(self, service):
        result = service.open_sftp_session()
        assert result is None

    def test_open_sftp_session_with_ssh(self, service):
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        service.ssh_client = mock_ssh

        result = service.open_sftp_session()
        assert result is mock_sftp
