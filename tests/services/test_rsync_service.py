"""
Tests for the rsync transfer service.
"""

from unittest.mock import MagicMock, patch

from src.services.rsync_service import (
    RsyncConfig,
    RsyncTransfer,
    _build_ssh_option,
    _remote_spec,
    is_rsync_available,
)


class TestIsRsyncAvailable:
    @patch("src.services.rsync_service.shutil.which")
    def test_available(self, mock_which):
        mock_which.return_value = "/usr/bin/rsync"
        assert is_rsync_available() is True

    @patch("src.services.rsync_service.shutil.which")
    def test_not_available(self, mock_which):
        mock_which.return_value = None
        assert is_rsync_available() is False


class TestBuildSshOption:
    def test_basic(self):
        config = RsyncConfig(
            host="192.168.1.100",
            username="user",
            ssh_key_path="~/.ssh/id_rsa",
            ssh_port=22,
        )
        result = _build_ssh_option(config)
        assert "ssh" in result
        assert "-p" in result
        assert "22" in result
        assert "id_rsa" in result
        assert "BatchMode=yes" in result

    def test_custom_port(self):
        config = RsyncConfig(
            host="10.0.0.1",
            username="admin",
            ssh_key_path="/path/to/key",
            ssh_port=2222,
        )
        result = _build_ssh_option(config)
        assert "2222" in result


class TestRemoteSpec:
    def test_basic(self):
        config = RsyncConfig(
            host="192.168.1.100",
            username="user",
            ssh_key_path="~/.ssh/id_rsa",
        )
        result = _remote_spec(config, "/mnt/external/Movies")
        assert result == "user@192.168.1.100:'/mnt/external/Movies'"

    def test_special_characters(self):
        config = RsyncConfig(
            host="192.168.1.100",
            username="user",
            ssh_key_path="~/.ssh/id_rsa",
        )
        result = _remote_spec(config, "/mnt/external/TV Shows/Show (2010)/Season 1")
        assert "(2010)" in result
        assert result.startswith("user@192.168.1.100:'")
        assert result.endswith("'")

    def test_path_with_single_quotes(self):
        config = RsyncConfig(
            host="host",
            username="u",
            ssh_key_path="/key",
        )
        result = _remote_spec(config, "/path/it's here")
        # Single quotes inside are escaped
        assert "'\\''" in result


class TestRsyncTransfer:
    def test_build_command(self):
        config = RsyncConfig(
            host="192.168.1.100",
            username="user",
            ssh_key_path="~/.ssh/id_rsa",
            ssh_port=22,
        )
        transfer = RsyncTransfer(
            config=config,
            local_paths=["/tmp/video.mp4", "/tmp/photo.jpg"],
            remote_dir="/mnt/external/uploads",
        )
        cmd = transfer._build_command()

        assert cmd[0] == "rsync"
        assert "-a" in cmd
        assert "--partial" in cmd
        assert "--progress" in cmd
        assert "/tmp/video.mp4" in cmd
        assert "/tmp/photo.jpg" in cmd
        # Destination should have trailing slash and be quoted
        assert "user@192.168.1.100:'/mnt/external/uploads/'" in cmd

    def test_build_command_adds_trailing_slash(self):
        config = RsyncConfig(host="host", username="u", ssh_key_path="/key")
        transfer = RsyncTransfer(
            config=config,
            local_paths=["/file.txt"],
            remote_dir="/dest",
        )
        cmd = transfer._build_command()
        dest = cmd[-1]
        assert dest.endswith("/dest/'")

    def test_build_command_preserves_existing_slash(self):
        config = RsyncConfig(host="host", username="u", ssh_key_path="/key")
        transfer = RsyncTransfer(
            config=config,
            local_paths=["/file.txt"],
            remote_dir="/dest/",
        )
        cmd = transfer._build_command()
        dest = cmd[-1]
        assert dest.endswith("/dest/'")
        assert "/dest//'" not in dest

    @patch("src.services.rsync_service.subprocess.Popen")
    def test_run_success(self, mock_popen):
        # Simulate rsync outputting progress then exiting 0
        mock_proc = MagicMock()
        mock_proc.stdout = iter(
            [
                "          100  10%    1.00MB/s    0:00:01\r",
                "          500  50%    2.00MB/s    0:00:01\r",
                "        1,000 100%    3.00MB/s    0:00:00\r",
            ]
        )
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = ""
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        config = RsyncConfig(host="host", username="u", ssh_key_path="/key")
        transfer = RsyncTransfer(
            config=config,
            local_paths=["/file.txt"],
            remote_dir="/dest",
        )

        progress_values = []
        transfer.run(progress_cb=lambda p: progress_values.append(p))

        assert 100 in progress_values
        assert progress_values[-1] == 100

    @patch("src.services.rsync_service.subprocess.Popen")
    def test_run_failure(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = "Permission denied"
        mock_proc.wait.return_value = None
        mock_proc.returncode = 1
        mock_proc.poll.return_value = 1
        mock_popen.return_value = mock_proc

        config = RsyncConfig(host="host", username="u", ssh_key_path="/key")
        transfer = RsyncTransfer(
            config=config,
            local_paths=["/file.txt"],
            remote_dir="/dest",
        )

        import pytest

        with pytest.raises(RuntimeError, match="rsync failed"):
            transfer.run()

    def test_cancel(self):
        config = RsyncConfig(host="host", username="u", ssh_key_path="/key")
        transfer = RsyncTransfer(
            config=config,
            local_paths=["/file.txt"],
            remote_dir="/dest",
        )
        # Mock a running process
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        transfer._process = mock_proc

        transfer.cancel()

        assert transfer._cancelled is True
        mock_proc.terminate.assert_called_once()


class TestBuildRsyncConfigInController:
    """Test the _build_rsync_config method on ManualTransferController."""

    def test_returns_config_for_ssh_key_auth(self):
        from src.controllers.transfer_controller import ManualTransferController

        controller = ManualTransferController.__new__(ManualTransferController)
        mock_settings = MagicMock()
        mock_settings.host = "192.168.1.100"
        mock_settings.username = "user"
        mock_settings.ssh_key_path = "~/.ssh/id_rsa"
        mock_settings.ssh_port = 22
        mock_settings.config.use_rsync = True
        controller.settings = mock_settings

        result = controller._build_rsync_config("ssh", {"name": "Server"})
        assert result is not None
        assert result.host == "192.168.1.100"
        assert result.username == "user"

    def test_returns_none_for_adb(self):
        from src.controllers.transfer_controller import ManualTransferController

        controller = ManualTransferController.__new__(ManualTransferController)
        mock_settings = MagicMock()
        mock_settings.config.use_rsync = True
        controller.settings = mock_settings

        result = controller._build_rsync_config("adb", {})
        assert result is None

    def test_returns_none_for_password_auth(self):
        from src.controllers.transfer_controller import ManualTransferController

        controller = ManualTransferController.__new__(ManualTransferController)
        mock_settings = MagicMock()
        mock_settings.config.use_rsync = True
        controller.settings = mock_settings

        result = controller._build_rsync_config("ssh", {"password": "secret"})
        assert result is None

    def test_returns_none_when_setting_off(self):
        from src.controllers.transfer_controller import ManualTransferController

        controller = ManualTransferController.__new__(ManualTransferController)
        mock_settings = MagicMock()
        mock_settings.config.use_rsync = False
        controller.settings = mock_settings

        result = controller._build_rsync_config("ssh", {"name": "Server"})
        assert result is None
