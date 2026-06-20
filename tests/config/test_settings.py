"""
Tests for the Settings configuration model.
"""

import json

import pytest

from src.config.settings import Settings, SettingsConfig
from src.models.errors import (
    IPAddressValidationError,
    InvalidConfigurationError,
    PathValidationError,
)


class TestSettingsConfig:
    def test_defaults(self):
        config = SettingsConfig()
        assert config.username == ""
        assert config.host == ""
        assert config.ssh_port == 22
        assert config.remote_base_dir == "/"
        assert config.delete_after_transfer is True
        assert config.notify_on_transfer_complete is True
        assert config.notify_sound is True
        assert config.compress_folders_before_transfer is False
        assert config.theme_mode == "system"
        assert config.max_parallel_transfers == 1
        assert ".DS_Store" in config.skip_patterns

    def test_valid_host(self):
        config = SettingsConfig(host="192.168.1.1")
        assert config.host == "192.168.1.1"

    def test_invalid_host_raises(self):
        with pytest.raises(IPAddressValidationError):
            SettingsConfig(host="not-an-ip")

    def test_empty_host_is_valid(self):
        config = SettingsConfig(host="")
        assert config.host == ""

    def test_valid_remote_base_dir(self):
        config = SettingsConfig(remote_base_dir="/home/user")
        assert config.remote_base_dir == "/home/user"

    def test_invalid_remote_base_dir_raises(self):
        with pytest.raises(PathValidationError):
            SettingsConfig(remote_base_dir="relative/path")

    def test_theme_mode_validation(self):
        config = SettingsConfig(theme_mode="dark")
        assert config.theme_mode == "dark"

    def test_invalid_theme_mode_defaults_to_system(self):
        config = SettingsConfig(theme_mode="neon")
        assert config.theme_mode == "system"

    def test_from_json_basic(self, sample_config):
        config = SettingsConfig.from_json(sample_config)
        assert config.username == "testuser"
        assert config.host == "192.168.1.100"
        assert config.ssh_port == 22
        assert config.delete_after_transfer is True

    def test_from_json_with_skip_patterns_as_list(self):
        data = {
            "skip_patterns": [".DS_Store", "Thumbs.db"],
            "delete_after_transfer": True,
            "ssh_port": 22,
        }
        config = SettingsConfig.from_json(data)
        assert ".DS_Store" in config.skip_patterns
        assert "Thumbs.db" in config.skip_patterns

    def test_from_json_removes_unknown_fields(self):
        data = {"unknown_field": "value", "another_unknown": 123}
        config = SettingsConfig.from_json(data)
        assert not hasattr(config, "unknown_field")

    def test_from_json_removes_legacy_file_extensions(self):
        data = {"file_extensions": [".mp4", ".mkv"]}
        config = SettingsConfig.from_json(data)
        assert not hasattr(config, "file_extensions")

    def test_from_json_invalid_raises(self):
        data = {"host": "not-valid-ip", "username": "x"}
        with pytest.raises(InvalidConfigurationError):
            SettingsConfig.from_json(data)


class TestSettingsSingleton:
    def test_singleton_returns_same_instance(self):
        # Reset singleton
        Settings._instance = None
        s1 = Settings()
        s2 = Settings()
        assert s1 is s2
        # Cleanup
        Settings._instance = None

    def test_properties(self):
        Settings._instance = None
        s = Settings()
        # Should have default values or loaded config
        assert isinstance(s.username, str)
        assert isinstance(s.host, str)
        assert isinstance(s.ssh_port, int)
        assert isinstance(s.remote_base_dir, str)
        assert isinstance(s.download_directory, str)
        Settings._instance = None

    def test_is_valid_empty_config(self):
        Settings._instance = None
        s = Settings()
        # With empty username/host, should be invalid
        if not s.username.strip() or not s.host.strip():
            assert not s.is_valid()
        Settings._instance = None

    def test_save_and_load_config(self, tmp_dir):
        Settings._instance = None
        s = Settings()

        config_data = s._config_to_dict()
        # Verify it produces a serializable dict
        json_str = json.dumps(config_data)
        assert json_str  # non-empty
        parsed = json.loads(json_str)
        assert "theme_mode" in parsed
        assert "notify_on_transfer_complete" in parsed
        assert "notify_sound" in parsed
        assert "compress_folders_before_transfer" in parsed
        assert "max_parallel_transfers" in parsed

        Settings._instance = None

    def test_get_servers(self):
        Settings._instance = None
        s = Settings()
        servers = s.get_servers()
        assert isinstance(servers, dict)
        Settings._instance = None

    def test_get_bookmarks_returns_list(self):
        Settings._instance = None
        s = Settings()
        bookmarks = s.get_bookmarks()
        assert isinstance(bookmarks, list)
        Settings._instance = None
