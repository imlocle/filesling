import ipaddress
import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from src.models.errors import (
    ConfigurationLoadError,
    ConfigurationSaveError,
    InvalidConfigurationError,
    IPAddressValidationError,
    PathValidationError,
    SSHKeyValidationError,
)
from src.utils.constants import CONFIG_JSON, SOFTWARE_NAME
from src.utils.logging_signal import logger


class SettingsConfig(BaseModel):
    """
    Application configuration model.

    Sections:
    1. Multi-server support
    2. Connection settings (SSH/SFTP)
    3. Remote path settings
    4. Transfer behavior
    """

    # Multi-server support
    servers: dict[str, dict] = Field(default_factory=dict)
    current_server_id: str = ""
    default_server_id: str = ""

    # Connection Settings
    pi_user: str = ""
    pi_ip: str = ""
    ssh_key_path: str = os.path.expanduser("~/.ssh/id_rsa")
    ssh_port: int = 22

    # Remote Path
    remote_base_dir: str = "/mnt/external"

    # Transfer Behavior
    delete_after_transfer: bool = True
    file_extensions: set[str] = Field(
        default_factory=lambda: {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".webm",
            ".flv",
            ".srt",
            ".nfo",
        }
    )
    skip_patterns: set[str] = Field(
        default_factory=lambda: {".DS_Store", "Thumbs.db", ".Trashes", "._*"}
    )

    # Metadata
    last_modified: str = ""

    # Legacy fields (kept for backward compat with old config files, ignored otherwise)
    local_watch_dir: str = ""
    stability_duration: float = 2.0
    auto_start_monitor: bool = False
    pi_root_dir: str = ""
    pi_movies: str = ""
    pi_tv: str = ""
    watch_dir: str = ""
    file_exts: set[str] = set()
    skip_files: set[str] = set()

    @field_validator("pi_ip")
    @classmethod
    def validate_ip_address(cls, v: str) -> str:
        """Validate IP address format if not empty."""
        if v and v.strip():
            try:
                ipaddress.ip_address(v.strip())
            except ValueError:
                raise IPAddressValidationError(
                    f"Invalid IP address format: {v}",
                    details="Please enter a valid IPv4 or IPv6 address",
                )
        return v

    @field_validator("ssh_key_path")
    @classmethod
    def validate_ssh_key(cls, v: str) -> str:
        """Validate SSH key path if not empty."""
        if v and v.strip():
            expanded_path = os.path.expanduser(v.strip())
            if not os.path.exists(expanded_path):
                # Don't raise error, just log warning (key might not exist yet)
                logger.warn(f"SSH key not found at: {expanded_path}")
            elif not os.path.isfile(expanded_path):
                raise SSHKeyValidationError(
                    f"SSH key path is not a file: {expanded_path}",
                    details="Please provide a path to a valid SSH private key file",
                )
        return v

    @field_validator("remote_base_dir")
    @classmethod
    def validate_remote_base_dir(cls, v: str) -> str:
        """Validate remote base directory format."""
        if v and v.strip():
            # Ensure it starts with / for absolute path
            if not v.strip().startswith("/"):
                raise PathValidationError(
                    f"Remote base directory must be an absolute path: {v}",
                    details="Path should start with /",
                )
        return v

    def model_post_init(self, __context) -> None:
        """
        Migrate legacy settings to new format after initialization.

        This ensures backward compatibility with old config files.
        """
        # Migrate watch_dir to local_watch_dir
        if self.watch_dir and not self.local_watch_dir:
            self.local_watch_dir = self.watch_dir

        # Migrate pi_root_dir to remote_base_dir
        if self.pi_root_dir and self.pi_root_dir != "/" and not self.remote_base_dir:
            self.remote_base_dir = self.pi_root_dir

        # Migrate file_exts to file_extensions
        if self.file_exts and not self.file_extensions:
            self.file_extensions = self.file_exts

        # Migrate skip_files to skip_patterns
        if self.skip_files and not self.skip_patterns:
            self.skip_patterns = self.skip_files

    @classmethod
    def from_json(cls, data: dict) -> "SettingsConfig":
        """
        Create SettingsConfig from JSON data.

        Args:
            data: Dictionary from JSON config file

        Returns:
            SettingsConfig instance

        Raises:
            InvalidConfigurationError: If validation fails
        """
        # Convert lists from JSON to sets for file_extensions and skip_patterns
        data = data.copy()

        # Handle new field names
        if "file_extensions" in data and isinstance(data["file_extensions"], list):
            data["file_extensions"] = set(data["file_extensions"])
        if "skip_patterns" in data and isinstance(data["skip_patterns"], list):
            data["skip_patterns"] = set(data["skip_patterns"])

        # Handle legacy field names for backward compatibility
        if "file_exts" in data and isinstance(data["file_exts"], list):
            data["file_exts"] = set(data["file_exts"])
        if "skip_files" in data and isinstance(data["skip_files"], list):
            data["skip_files"] = set(data["skip_files"])

        # Ensure auto_start_monitor has a default
        data["auto_start_monitor"] = data.get("auto_start_monitor", False)

        # Ensure delete_after_transfer has a default
        data["delete_after_transfer"] = data.get("delete_after_transfer", True)

        # Ensure stability_duration has a default
        data["stability_duration"] = data.get("stability_duration", 2.0)

        # Ensure ssh_port has a default
        data["ssh_port"] = data.get("ssh_port", 22)

        try:
            return cls(**data)
        except Exception as e:
            raise InvalidConfigurationError(
                "Failed to parse configuration", details=str(e)
            )


class Settings:
    _instance: "Settings | None" = None
    config: SettingsConfig

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            # First, try loading from the user's local config directory
            local_config_path = Path.home() / f".{SOFTWARE_NAME}" / CONFIG_JSON
            if local_config_path.exists() and local_config_path.is_file():
                config_data = cls._load_config(local_config_path)
                logger.success(f"Config: Loaded: {local_config_path}")
            else:
                # Determine config file path for loading
                if getattr(sys, "_MEIPASS", None):  # type: ignore[attr-defined]
                    base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
                    config_path = base_path / f"src/config/{CONFIG_JSON}"
                else:
                    config_path = Path(__file__).parent / CONFIG_JSON
                # Load and validate config
                config_data = cls._load_config(config_path)
            cls._instance.config = SettingsConfig.from_json(config_data)
        return cls._instance

    @staticmethod
    def _load_config(config_path: Path) -> dict:
        """
        Load configuration from JSON file.

        Args:
            config_path: Path to config file

        Returns:
            Configuration dictionary

        Raises:
            ConfigurationLoadError: If loading fails critically
        """
        try:
            if config_path.exists() and config_path.is_file():
                with open(config_path, "r") as f:
                    data = json.load(f)
                    logger.info(f"Config: Loaded from {config_path}")
                    return data
            else:
                logger.warn(f"Config: File not found: {config_path}, using defaults")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Config: Invalid JSON in {config_path}: {e}")
            raise ConfigurationLoadError(
                f"Invalid JSON in configuration file",
                details=f"File: {config_path}, Error: {str(e)}",
            )
        except PermissionError as e:
            logger.error(f"Config: Permission denied: {config_path}")
            raise ConfigurationLoadError(
                f"Cannot read configuration file",
                details=f"Permission denied: {config_path}",
            )
        except Exception as e:
            logger.error(f"Config: Error loading {config_path}: {e}")
            # Return empty dict for non-critical errors
            return {}

    # Properties
    @property
    def remote_base_dir(self):
        return self.config.remote_base_dir

    @property
    def file_extensions(self):
        return self.config.file_extensions

    @property
    def skip_patterns(self):
        return self.config.skip_patterns

    @property
    def delete_after_transfer(self):
        return self.config.delete_after_transfer

    @property
    def ssh_port(self):
        return self.config.ssh_port

    @property
    def pi_user(self):
        return self.config.pi_user

    @property
    def pi_ip(self):
        return self.config.pi_ip

    @property
    def ssh_key_path(self):
        return self.config.ssh_key_path

    @property
    def skip_files(self):
        """Used by file explorer for filtering."""
        return self.config.skip_patterns or self.config.skip_files

    @property
    def local_watch_dir(self):
        """Legacy — kept for settings_window compat."""
        return self.config.local_watch_dir

    @property
    def last_modified(self):
        return self.config.last_modified

    def save_config(self, config_data: dict) -> None:
        """
        Save configuration to JSON file.

        Args:
            config_data: Configuration dictionary to save

        Raises:
            ConfigurationSaveError: If save fails
        """
        # Determine save path in user directory
        save_dir = Path.home() / f".{SOFTWARE_NAME}"

        try:
            save_dir.mkdir(exist_ok=True)
        except Exception as e:
            raise ConfigurationSaveError(
                f"Cannot create config directory: {save_dir}", details=str(e)
            )

        config_path = save_dir / CONFIG_JSON

        # Convert sets back to lists for JSON serialization
        save_data = config_data.copy()

        # Handle new field names
        if "file_extensions" in save_data and isinstance(
            save_data["file_extensions"], set
        ):
            save_data["file_extensions"] = list(save_data["file_extensions"])
        if "skip_patterns" in save_data and isinstance(save_data["skip_patterns"], set):
            save_data["skip_patterns"] = list(save_data["skip_patterns"])

        # Handle legacy field names
        if "file_exts" in save_data and isinstance(save_data["file_exts"], set):
            save_data["file_exts"] = list(save_data["file_exts"])
        if "skip_files" in save_data and isinstance(save_data["skip_files"], set):
            save_data["skip_files"] = list(save_data["skip_files"])

        try:
            with open(config_path, "w") as f:
                json.dump(save_data, f, indent=4)
            logger.success(f"Config: Saved to {config_path}")
        except PermissionError as e:
            raise ConfigurationSaveError(
                f"Permission denied writing config", details=f"Path: {config_path}"
            )
        except Exception as e:
            raise ConfigurationSaveError(
                f"Failed to save configuration",
                details=f"Path: {config_path}, Error: {str(e)}",
            )

    def is_valid(self) -> bool:
        """
        Check if critical settings are configured.

        Returns:
            True if all required settings are present
        """
        return all(
            [
                self.pi_user.strip(),
                self.pi_ip.strip(),
                self.remote_base_dir.strip(),
            ]
        )

    def get_servers(self) -> dict[str, dict]:
        """
        Get all saved servers.

        Returns:
            Dictionary of server_id -> server config
        """
        return self.config.servers.copy()

    def get_server(self, server_id: str) -> dict | None:
        """
        Get a specific server configuration.

        Args:
            server_id: Server identifier

        Returns:
            Server configuration dict or None if not found
        """
        return self.config.servers.get(server_id)

    def add_server(self, server_id: str, server_config: dict) -> None:
        """
        Add or update a server configuration.

        Args:
            server_id: Unique server identifier
            server_config: Server configuration dictionary
        """
        self.config.servers[server_id] = server_config

        # Save to disk
        config_data = self._config_to_dict()
        self.save_config(config_data)

    def delete_server(self, server_id: str) -> None:
        """
        Delete a server configuration.

        Args:
            server_id: Server identifier to delete
        """
        if server_id in self.config.servers:
            del self.config.servers[server_id]

            # If this was the current server, clear it
            if self.config.current_server_id == server_id:
                self.config.current_server_id = ""

            # If this was the default server, clear it
            if self.config.default_server_id == server_id:
                self.config.default_server_id = ""

            # Save to disk
            config_data = self._config_to_dict()
            self.save_config(config_data)

    def set_default_server(self, server_id: str) -> None:
        """
        Set a server as the default for auto-connect on launch.

        Args:
            server_id: Server identifier to set as default
        """
        self.config.default_server_id = server_id
        config_data = self._config_to_dict()
        self.save_config(config_data)

    def load_server(self, server_id: str) -> bool:
        """
        Load a server configuration as the current active server.

        Args:
            server_id: Server identifier to load

        Returns:
            True if server was loaded successfully, False otherwise
        """
        server_config = self.config.servers.get(server_id)
        if not server_config:
            logger.error(f"Settings: Server not found: {server_id}")
            return False

        # Update current connection settings
        self.config.pi_user = server_config.get("pi_user", "")
        self.config.pi_ip = server_config.get("pi_ip", "")
        self.config.ssh_key_path = server_config.get(
            "ssh_key_path", os.path.expanduser("~/.ssh/id_rsa")
        )
        self.config.ssh_port = server_config.get("ssh_port", 22)
        self.config.remote_base_dir = server_config.get(
            "remote_base_dir", "/mnt/external"
        )
        self.config.current_server_id = server_id

        logger.info(f"Settings: Loaded server: {server_config.get('name', server_id)}")
        return True

    def _config_to_dict(self) -> dict:
        """
        Convert current config to dictionary for saving.

        Returns:
            Configuration dictionary
        """
        return {
            "servers": self.config.servers,
            "current_server_id": self.config.current_server_id,
            "default_server_id": self.config.default_server_id,
            "pi_user": self.config.pi_user,
            "pi_ip": self.config.pi_ip,
            "ssh_key_path": self.config.ssh_key_path,
            "ssh_port": self.config.ssh_port,
            "remote_base_dir": self.config.remote_base_dir,
            "delete_after_transfer": self.config.delete_after_transfer,
            "file_extensions": list(self.config.file_extensions),
            "skip_patterns": list(self.config.skip_patterns),
            "last_modified": self.config.last_modified,
        }
