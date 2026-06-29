"""
Unit tests for ServerConfig dataclass.

Tests construction, from_dict/to_dict serialization, properties, and edge cases.
"""

from src.models.server_config import ServerConfig
from src.utils.constants import (
    CONN_TYPE_SSH,
    DEFAULT_ADB_BASE_DIR,
    DEFAULT_REMOTE_BASE_DIR,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
)

# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------


class TestServerConfigDefaults:
    def test_default_values(self):
        config = ServerConfig()
        assert config.name == ""
        assert config.connection_type == CONN_TYPE_SSH
        assert config.host == ""
        assert config.username == ""
        assert config.ssh_key_path == DEFAULT_SSH_KEY_PATH
        assert config.ssh_port == DEFAULT_SSH_PORT
        assert config.password == ""
        assert config.key_passphrase == ""
        assert config.device_id == ""
        assert config.wifi_ip == ""
        assert config.remote_base_dir == DEFAULT_REMOTE_BASE_DIR
        assert config.download_directory == ""
        assert config.extension_filter == ""
        assert config.bookmarks == []
        assert config.default_bookmark == ""

    def test_custom_values(self):
        config = ServerConfig(
            name="PiFlix",
            connection_type="ssh",
            host="192.168.1.100",
            username="pi",
            ssh_port=2222,
            remote_base_dir="/mnt/external",
            bookmarks=["/mnt/external/Movies", "/mnt/external/TV Shows"],
            default_bookmark="/mnt/external/Movies",
        )
        assert config.name == "PiFlix"
        assert config.host == "192.168.1.100"
        assert config.username == "pi"
        assert config.ssh_port == 2222
        assert config.remote_base_dir == "/mnt/external"
        assert len(config.bookmarks) == 2
        assert config.default_bookmark == "/mnt/external/Movies"


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------


class TestServerConfigFromDict:
    def test_ssh_server(self):
        data = {
            "name": "Home Pi",
            "connection_type": "ssh",
            "host": "192.168.50.247",
            "username": "pi",
            "ssh_key_path": "~/.ssh/pi_key",
            "ssh_port": 22,
            "remote_base_dir": "/mnt/external",
            "bookmarks": ["/mnt/external/Movies"],
            "default_bookmark": "/mnt/external/Movies",
        }
        config = ServerConfig.from_dict(data)
        assert config.name == "Home Pi"
        assert config.connection_type == "ssh"
        assert config.host == "192.168.50.247"
        assert config.username == "pi"
        assert config.ssh_key_path == "~/.ssh/pi_key"
        assert config.ssh_port == 22
        assert config.remote_base_dir == "/mnt/external"
        assert config.bookmarks == ["/mnt/external/Movies"]

    def test_adb_device(self):
        data = {
            "name": "Pixel Phone",
            "connection_type": "adb",
            "device_id": "ABC123",
            "wifi_ip": "192.168.1.50",
        }
        config = ServerConfig.from_dict(data)
        assert config.name == "Pixel Phone"
        assert config.connection_type == "adb"
        assert config.device_id == "ABC123"
        assert config.wifi_ip == "192.168.1.50"
        assert config.remote_base_dir == DEFAULT_ADB_BASE_DIR

    def test_ios_device(self):
        data = {
            "name": "iPhone",
            "connection_type": "ios",
            "device_id": "UDID-XYZ",
        }
        config = ServerConfig.from_dict(data)
        assert config.name == "iPhone"
        assert config.connection_type == "ios"
        assert config.device_id == "UDID-XYZ"
        assert config.remote_base_dir == "/DCIM"

    def test_password_auth(self):
        data = {
            "name": "Password Server",
            "connection_type": "ssh",
            "host": "10.0.0.5",
            "username": "admin",
            "password": "secret123",
        }
        config = ServerConfig.from_dict(data)
        assert config.password == "secret123"
        assert config.has_password_auth is True

    def test_key_passphrase(self):
        data = {
            "name": "Secured Key",
            "connection_type": "ssh",
            "host": "10.0.0.5",
            "username": "admin",
            "key_passphrase": "my-passphrase",
        }
        config = ServerConfig.from_dict(data)
        assert config.key_passphrase == "my-passphrase"

    def test_empty_dict(self):
        """Empty dict should produce valid defaults."""
        config = ServerConfig.from_dict({})
        assert config.name == ""
        assert config.connection_type == CONN_TYPE_SSH
        assert config.host == ""
        assert config.ssh_key_path == DEFAULT_SSH_KEY_PATH
        assert config.ssh_port == DEFAULT_SSH_PORT
        assert config.remote_base_dir == DEFAULT_REMOTE_BASE_DIR
        assert config.bookmarks == []

    def test_missing_fields_use_defaults(self):
        data = {"name": "Minimal", "host": "10.0.0.1"}
        config = ServerConfig.from_dict(data)
        assert config.name == "Minimal"
        assert config.host == "10.0.0.1"
        assert config.ssh_port == DEFAULT_SSH_PORT
        assert config.username == ""

    def test_ssh_port_string_conversion(self):
        """ssh_port stored as string in JSON should be converted to int."""
        data = {"ssh_port": "2222"}
        config = ServerConfig.from_dict(data)
        assert config.ssh_port == 2222
        assert isinstance(config.ssh_port, int)

    def test_bookmarks_is_independent_copy(self):
        """Bookmarks should be a copy, not a reference to the original list."""
        original_bookmarks = ["/path/a", "/path/b"]
        data = {"bookmarks": original_bookmarks}
        config = ServerConfig.from_dict(data)
        original_bookmarks.append("/path/c")
        assert len(config.bookmarks) == 2

    def test_per_server_download_directory(self):
        data = {
            "name": "Custom Download",
            "download_directory": "/Users/me/ServerFiles",
        }
        config = ServerConfig.from_dict(data)
        assert config.download_directory == "/Users/me/ServerFiles"

    def test_extension_filter(self):
        data = {
            "name": "Filtered",
            "extension_filter": ".mp4,.mkv,.avi",
        }
        config = ServerConfig.from_dict(data)
        assert config.extension_filter == ".mp4,.mkv,.avi"


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestServerConfigToDict:
    def test_ssh_to_dict(self):
        config = ServerConfig(
            name="PiFlix",
            connection_type="ssh",
            host="192.168.1.100",
            username="pi",
            ssh_key_path="~/.ssh/id_rsa",
            ssh_port=22,
            remote_base_dir="/mnt/external",
            bookmarks=["/mnt/external/Movies"],
            default_bookmark="/mnt/external/Movies",
        )
        d = config.to_dict()
        assert d["name"] == "PiFlix"
        assert d["connection_type"] == "ssh"
        assert d["host"] == "192.168.1.100"
        assert d["username"] == "pi"
        assert d["ssh_key_path"] == "~/.ssh/id_rsa"
        assert d["ssh_port"] == 22
        assert d["remote_base_dir"] == "/mnt/external"
        assert d["bookmarks"] == ["/mnt/external/Movies"]
        assert d["default_bookmark"] == "/mnt/external/Movies"

    def test_adb_to_dict(self):
        config = ServerConfig(
            name="Phone",
            connection_type="adb",
            device_id="DEF456",
            wifi_ip="192.168.1.50",
            remote_base_dir="/storage/emulated/0",
        )
        d = config.to_dict()
        assert d["connection_type"] == "adb"
        assert d["device_id"] == "DEF456"
        assert d["wifi_ip"] == "192.168.1.50"
        # SSH fields should NOT be present
        assert "host" not in d
        assert "username" not in d
        assert "ssh_key_path" not in d

    def test_ios_to_dict(self):
        config = ServerConfig(
            name="iPhone",
            connection_type="ios",
            device_id="UDID-123",
            remote_base_dir="/DCIM",
        )
        d = config.to_dict()
        assert d["connection_type"] == "ios"
        assert d["device_id"] == "UDID-123"
        assert "host" not in d

    def test_password_included_when_set(self):
        config = ServerConfig(
            connection_type="ssh",
            host="10.0.0.5",
            username="admin",
            password="secret",
        )
        d = config.to_dict()
        assert d["password"] == "secret"

    def test_password_excluded_when_empty(self):
        config = ServerConfig(
            connection_type="ssh",
            host="10.0.0.5",
            username="admin",
            password="",
        )
        d = config.to_dict()
        assert "password" not in d

    def test_optional_fields_excluded_when_empty(self):
        """Empty optional fields should not appear in the dict."""
        config = ServerConfig(
            name="Minimal",
            connection_type="ssh",
            host="10.0.0.1",
            username="user",
        )
        d = config.to_dict()
        assert "download_directory" not in d
        assert "extension_filter" not in d
        assert "bookmarks" not in d
        assert "default_bookmark" not in d
        assert "password" not in d
        assert "key_passphrase" not in d

    def test_wifi_ip_excluded_when_empty(self):
        config = ServerConfig(
            connection_type="adb",
            device_id="ABC",
            wifi_ip="",
        )
        d = config.to_dict()
        assert "wifi_ip" not in d


# ---------------------------------------------------------------------------
# Roundtrip serialization
# ---------------------------------------------------------------------------


class TestServerConfigRoundtrip:
    def test_ssh_roundtrip(self):
        original = ServerConfig(
            name="Full SSH",
            connection_type="ssh",
            host="192.168.1.100",
            username="pi",
            ssh_key_path="~/.ssh/pi_key",
            ssh_port=2222,
            password="pass123",
            key_passphrase="phrase",
            remote_base_dir="/mnt/data",
            download_directory="/Users/me/Downloads",
            extension_filter=".mp4,.mkv",
            bookmarks=["/mnt/data/Movies", "/mnt/data/TV"],
            default_bookmark="/mnt/data/Movies",
        )
        restored = ServerConfig.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.connection_type == original.connection_type
        assert restored.host == original.host
        assert restored.username == original.username
        assert restored.ssh_key_path == original.ssh_key_path
        assert restored.ssh_port == original.ssh_port
        assert restored.password == original.password
        assert restored.key_passphrase == original.key_passphrase
        assert restored.remote_base_dir == original.remote_base_dir
        assert restored.download_directory == original.download_directory
        assert restored.extension_filter == original.extension_filter
        assert restored.bookmarks == original.bookmarks
        assert restored.default_bookmark == original.default_bookmark

    def test_adb_roundtrip(self):
        original = ServerConfig(
            name="Pixel",
            connection_type="adb",
            device_id="ABC123",
            wifi_ip="192.168.1.50",
            remote_base_dir="/storage/emulated/0",
        )
        restored = ServerConfig.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.connection_type == original.connection_type
        assert restored.device_id == original.device_id
        assert restored.wifi_ip == original.wifi_ip
        assert restored.remote_base_dir == original.remote_base_dir


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestServerConfigProperties:
    def test_is_ssh(self):
        config = ServerConfig(connection_type="ssh")
        assert config.is_ssh is True
        assert config.is_adb is False
        assert config.is_ios is False

    def test_is_adb(self):
        config = ServerConfig(connection_type="adb")
        assert config.is_ssh is False
        assert config.is_adb is True
        assert config.is_ios is False

    def test_is_ios(self):
        config = ServerConfig(connection_type="ios")
        assert config.is_ssh is False
        assert config.is_adb is False
        assert config.is_ios is True

    def test_has_password_auth_true(self):
        config = ServerConfig(password="secret")
        assert config.has_password_auth is True

    def test_has_password_auth_false(self):
        config = ServerConfig(password="")
        assert config.has_password_auth is False

    def test_get_download_directory_per_server(self):
        config = ServerConfig(download_directory="/custom/path")
        assert config.get_download_directory("/fallback") == "/custom/path"

    def test_get_download_directory_fallback(self):
        config = ServerConfig(download_directory="")
        assert config.get_download_directory("/fallback") == "/fallback"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestServerConfigEdgeCases:
    def test_bookmarks_default_factory_isolation(self):
        """Each instance should have its own bookmarks list."""
        config1 = ServerConfig()
        config2 = ServerConfig()
        config1.bookmarks.append("/path/a")
        assert config2.bookmarks == []

    def test_from_dict_with_extra_keys(self):
        """Extra keys in the dict should be silently ignored."""
        data = {
            "name": "Test",
            "connection_type": "ssh",
            "host": "10.0.0.1",
            "unknown_key": "should_be_ignored",
            "another_extra": 42,
        }
        config = ServerConfig.from_dict(data)
        assert config.name == "Test"
        assert config.host == "10.0.0.1"
        # No error raised

    def test_from_dict_with_none_values(self):
        """None values in dict may cause TypeError for int fields."""
        # This documents a known edge case: if ssh_port is explicitly None
        # in the JSON (not missing, but null), from_dict will crash.
        # Normal usage never produces this since JSON config always has
        # integer ports, but it's worth documenting.
        data = {
            "name": None,
            "host": None,
            "ssh_port": 22,  # Must be a valid int-coercible value
        }
        config = ServerConfig.from_dict(data)
        # None passes through for string fields (get returns None, not "")
        assert config.name is None
        assert config.host is None
        assert config.ssh_port == 22

    def test_adb_default_base_dir(self):
        """ADB connections should default to /storage/emulated/0."""
        data = {"connection_type": "adb"}
        config = ServerConfig.from_dict(data)
        assert config.remote_base_dir == DEFAULT_ADB_BASE_DIR

    def test_ios_default_base_dir(self):
        """iOS connections should default to /DCIM."""
        data = {"connection_type": "ios"}
        config = ServerConfig.from_dict(data)
        assert config.remote_base_dir == "/DCIM"

    def test_ssh_default_base_dir(self):
        """SSH connections should default to DEFAULT_REMOTE_BASE_DIR."""
        data = {"connection_type": "ssh"}
        config = ServerConfig.from_dict(data)
        assert config.remote_base_dir == DEFAULT_REMOTE_BASE_DIR
