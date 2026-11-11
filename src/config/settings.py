import ipaddress
import os
import sys
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator

from src.models.errors import (
    ConfigurationLoadError,
    ConfigurationSaveError,
    InvalidConfigurationError,
    IPAddressValidationError,
    PathValidationError,
    SSHKeyValidationError,
)
from src.repositories.settings_repository import SettingsRepository
from src.services.keychain_service import (
    delete_password,
    has_stored_password,
    retrieve_password,
    store_password,
)
from src.utils.constants import (
    APP_DATA_DIR,
    CONFIG_JSON,
    DEFAULT_REMOTE_BASE_DIR,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
)
from src.utils.logging_signal import logger


class SettingsConfig(BaseModel):
    """Application configuration model."""

    # Multi-server support
    servers: dict[str, dict] = Field(default_factory=dict)
    current_server_id: str = ""
    default_server_id: str = ""
    destination_profiles: list[dict] = Field(default_factory=list)
    active_destination_profile_id: str = ""

    # Connection Settings
    username: str = ""
    host: str = ""
    ssh_key_path: str = os.path.expanduser(DEFAULT_SSH_KEY_PATH)
    ssh_port: int = DEFAULT_SSH_PORT

    # Remote Path
    remote_base_dir: str = DEFAULT_REMOTE_BASE_DIR

    # Transfer Behavior
    delete_after_transfer: bool = True
    download_directory: str = os.path.expanduser("~/Downloads")
    reveal_in_finder_after_download: bool = False
    notify_on_transfer_complete: bool = True
    notify_sound: bool = True
    compress_folders_before_transfer: bool = False
    use_rsync: bool = True
    hide_nfo_files: bool = False
    show_detail_panel: bool = False
    prevent_sleep_during_transfer: bool = True
    skip_patterns: set[str] = Field(
        default_factory=lambda: {".DS_Store", "Thumbs.db", ".Trashes", "._*"}
    )

    # Metadata
    last_modified: str = ""
    bookmarks: list[str] = Field(default_factory=list)
    theme_mode: str = "system"
    max_parallel_transfers: int = 1

    # IMDb metadata lookup
    # OMDb (primary): https://www.omdbapi.com/apikey.aspx
    # TMDB (fallback): https://www.themoviedb.org/settings/api
    omdb_api_key: str = ""
    tmdb_api_key: str = ""

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate host: accepts IP addresses and hostnames."""
        if v and v.strip():
            host = v.strip()
            # Accept valid IP addresses
            try:
                ipaddress.ip_address(host)
                return v
            except ValueError:
                pass
            # Otherwise accept valid hostnames (letters, digits, hyphens, dots)
            import re

            if not re.match(
                r"^(?=.{1,253}$)[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$", host
            ):
                raise IPAddressValidationError(
                    f"Invalid host: {v}",
                    details="Please enter a valid IP address or hostname",
                )
        return v

    @field_validator("ssh_key_path")
    @classmethod
    def validate_ssh_key(cls, v: str) -> str:
        """Validate SSH key path if not empty."""
        if v and v.strip():
            expanded_path = os.path.expanduser(v.strip())
            if not os.path.exists(expanded_path):
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
            if not v.strip().startswith("/"):
                raise PathValidationError(
                    f"Remote base directory must be an absolute path: {v}",
                    details="Path should start with /",
                )
        return v

    @field_validator("theme_mode")
    @classmethod
    def validate_theme_mode(cls, v: str) -> str:
        """Validate appearance preference."""
        if v not in ("system", "light", "dark"):
            return "system"
        return v

    @classmethod
    def from_json(cls, data: dict) -> "SettingsConfig":
        """Create SettingsConfig from JSON data."""
        data = data.copy()

        if "file_extensions" in data:
            del data["file_extensions"]  # Legacy field, no longer used
        if "skip_patterns" in data and isinstance(data["skip_patterns"], list):
            data["skip_patterns"] = set(data["skip_patterns"])

        # Defaults
        data.setdefault("delete_after_transfer", True)
        data.setdefault("ssh_port", 22)

        # Remove unknown fields that pydantic would reject
        known_fields = cls.model_fields.keys()
        data = {k: v for k, v in data.items() if k in known_fields}

        try:
            return cls(**data)
        except Exception as e:
            raise InvalidConfigurationError(
                "Failed to parse configuration", details=str(e)
            )


class Settings:
    _instance: Optional["Settings"] = None
    config: SettingsConfig

    def __new__(cls) -> "Settings":
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            local_config_path = APP_DATA_DIR / CONFIG_JSON
            if local_config_path.exists() and local_config_path.is_file():
                config_repository = SettingsRepository(local_config_path)
            else:
                if getattr(sys, "_MEIPASS", None):
                    base_path = Path(sys._MEIPASS)  # type: ignore
                    config_path = base_path / f"src/config/{CONFIG_JSON}"
                else:
                    config_path = Path(__file__).parent / CONFIG_JSON
                config_repository = SettingsRepository(config_path)
            cls._instance._repository = SettingsRepository(local_config_path)
            config_data = config_repository.load()
            cls._instance.config = SettingsConfig.from_json(config_data)
            cls._instance._migrate_legacy_secrets()
        return cls._instance

    @staticmethod
    def _server_secret_account(server_id: str, field: str) -> str:
        scope = server_id or "global"
        return f"server:{scope}:{field}"

    @staticmethod
    def _global_secret_account(field: str) -> str:
        return f"global:{field}"

    def _migrate_legacy_secrets(self) -> None:
        """Move legacy plaintext credentials into the platform credential store."""
        changed = False
        server_fields = ("password", "key_passphrase", "jellyfin_api_key")
        for server_id, server in self.config.servers.items():
            for field in server_fields:
                value = server.get(field)
                if value and store_password(
                    self._server_secret_account(server_id, field), str(value)
                ):
                    server.pop(field, None)
                    changed = True

        for field in ("omdb_api_key", "tmdb_api_key"):
            value = getattr(self.config, field)
            if value and store_password(self._global_secret_account(field), value):
                setattr(self.config, field, "")
                changed = True

        if changed:
            try:
                self.save_config(self._config_to_dict())
                logger.info("Settings: Migrated saved credentials to secure storage")
            except ConfigurationSaveError as e:
                logger.warn(f"Settings: Could not save credential migration: {e}")

    def get_server_secret(self, server_id: str, field: str) -> Optional[str]:
        """Read a server credential, including legacy plaintext values."""
        account = self._server_secret_account(server_id, field)
        stored = retrieve_password(account)
        if stored is not None:
            return stored
        server = self.get_server(server_id) or {}
        legacy = server.get(field)
        if legacy:
            return str(legacy)
        if server_id:
            global_value = retrieve_password(
                self._server_secret_account("", field)
            )
            if global_value is not None:
                return global_value
        return None

    def set_server_secret(self, server_id: str, field: str, value: str) -> None:
        """Store a server credential without writing it into config.json."""
        account = self._server_secret_account(server_id, field)
        if value:
            if not store_password(account, value):
                raise ConfigurationSaveError(
                    "Cannot store credential securely",
                    details="The platform credential store is unavailable.",
                )
        elif has_stored_password(account) and not delete_password(account):
            raise ConfigurationSaveError(
                "Cannot remove saved credential",
                details="The platform credential store could not delete the credential.",
            )

    def get_global_secret(self, field: str) -> str:
        """Read a global API token, including legacy plaintext values."""
        stored = retrieve_password(self._global_secret_account(field))
        return stored if stored is not None else str(getattr(self.config, field, ""))

    def set_global_secret(self, field: str, value: str) -> None:
        """Store a global API token without writing it into config.json."""
        account = self._global_secret_account(field)
        if value:
            if not store_password(account, value):
                raise ConfigurationSaveError(
                    "Cannot store API key securely",
                    details="The platform credential store is unavailable.",
                )
        elif has_stored_password(account) and not delete_password(account):
            raise ConfigurationSaveError(
                "Cannot remove saved API key",
                details="The platform credential store could not delete the key.",
            )

    @staticmethod
    def _load_config(config_path: Path) -> dict:
        """Load configuration from JSON file."""
        return SettingsRepository(config_path).load()

    def read_config_file(self, path: Union[str, Path]) -> dict:
        """Read an external configuration document through the repository."""
        config_path = Path(path)
        if not config_path.is_file():
            raise ConfigurationLoadError(
                "Configuration file does not exist", details=f"Path: {config_path}"
            )
        return SettingsRepository(config_path).load()

    def export_config(self, path: Union[str, Path]) -> None:
        """Export the active settings through the repository's atomic writer."""
        SettingsRepository(Path(path)).save(self._config_to_dict())

    def reload_config(self, config_data: dict) -> None:
        """
        Reload configuration in-place without resetting the singleton.

        This ensures all existing references to the Settings instance
        see the updated config without needing to re-acquire the singleton.
        """
        self.config = SettingsConfig.from_json(config_data)
        self._migrate_legacy_secrets()

    # Properties
    @property
    def username(self) -> str:
        return self.config.username

    @property
    def host(self) -> str:
        return self.config.host

    @property
    def ssh_key_path(self) -> str:
        return self.config.ssh_key_path

    @property
    def ssh_port(self) -> int:
        return self.config.ssh_port

    @property
    def remote_base_dir(self) -> str:
        return self.config.remote_base_dir

    @property
    def delete_after_transfer(self) -> bool:
        return self.config.delete_after_transfer

    def get_delete_after_transfer_for_server(
        self, server_id: Optional[str] = None
    ) -> bool:
        """Get delete-after-transfer preference for a server, falling back to global."""
        sid = server_id or self.config.current_server_id
        server = self.get_server(sid)
        if server and server.get("delete_after_transfer") is not None:
            return bool(server["delete_after_transfer"])
        return self.config.delete_after_transfer

    def get_activity_history_enabled_for_server(
        self, server_id: Optional[str] = None
    ) -> bool:
        """Get activity-history preference for a server, falling back to enabled."""
        sid = server_id or self.config.current_server_id
        server = self.get_server(sid)
        if server and server.get("activity_history_enabled") is not None:
            return bool(server["activity_history_enabled"])
        return True

    @property
    def download_directory(self) -> str:
        return self.config.download_directory

    @property
    def skip_patterns(self) -> set[str]:
        return self.config.skip_patterns

    @property
    def skip_files(self) -> set[str]:
        """Alias for skip_patterns (used by file explorer)."""
        return self.config.skip_patterns

    @property
    def last_modified(self) -> str:
        return self.config.last_modified

    @property
    def omdb_api_key(self) -> str:
        return self.get_global_secret("omdb_api_key")

    @property
    def tmdb_api_key(self) -> str:
        return self.get_global_secret("tmdb_api_key")

    def save_config(self, config_data: dict) -> None:
        """Save configuration to JSON file."""
        repository = getattr(self, "_repository", None)
        if repository is None:
            repository = SettingsRepository(APP_DATA_DIR / CONFIG_JSON)
            self._repository = repository
        repository.save(config_data)

    def is_valid(self) -> bool:
        """Check if critical settings are configured."""
        return all(
            [
                self.username.strip(),
                self.host.strip(),
                self.remote_base_dir.strip(),
            ]
        )

    def get_servers(self) -> dict[str, dict]:
        return self.config.servers.copy()

    def get_server(self, server_id: str) -> Optional[dict]:
        return self.config.servers.get(server_id)

    def get_server_config(self, server_id: str = ""):
        """Get a typed ServerConfig for the given server (or current server).

        Returns None if the server doesn't exist.
        """
        from src.models.server_config import ServerConfig

        sid = server_id or self.config.current_server_id
        raw = self.config.servers.get(sid)
        if raw is None:
            return None
        server = ServerConfig.from_dict(raw)
        server.password = self.get_server_secret(sid, "password") or ""
        server.key_passphrase = self.get_server_secret(sid, "key_passphrase") or ""
        server.jellyfin_api_key = self.get_server_secret(sid, "jellyfin_api_key") or ""
        return server

    def add_server(self, server_id: str, server_config: dict) -> None:
        safe_config = server_config.copy()
        for field in ("password", "key_passphrase", "jellyfin_api_key"):
            if field in safe_config:
                self.set_server_secret(server_id, field, str(safe_config.pop(field)))
        self.config.servers[server_id] = safe_config
        self.save_config(self._config_to_dict())

    def delete_server(self, server_id: str) -> None:
        if server_id in self.config.servers:
            for field in ("password", "key_passphrase", "jellyfin_api_key"):
                account = self._server_secret_account(server_id, field)
                if has_stored_password(account):
                    delete_password(account)
            del self.config.servers[server_id]
            if self.config.current_server_id == server_id:
                self.config.current_server_id = ""
            if self.config.default_server_id == server_id:
                self.config.default_server_id = ""
            removed_profile_ids = {
                str(profile.get("profile_id", ""))
                for profile in self.config.destination_profiles
                if profile.get("server_id") == server_id
            }
            self.config.destination_profiles = [
                profile
                for profile in self.config.destination_profiles
                if profile.get("server_id") != server_id
            ]
            if self.config.active_destination_profile_id in removed_profile_ids:
                self.config.active_destination_profile_id = ""
            self.save_config(self._config_to_dict())

    def set_default_server(self, server_id: str) -> None:
        self.config.default_server_id = server_id
        self.save_config(self._config_to_dict())

    def get_destination_profiles(self) -> list[dict]:
        """Return a copy of saved destination profile records."""
        return [profile.copy() for profile in self.config.destination_profiles]

    def save_destination_profile(self, profile: dict) -> None:
        """Create or replace one destination profile in user settings."""
        profile_id = str(profile.get("profile_id", "")).strip()
        if not profile_id:
            raise ValueError("A destination profile ID is required")
        profiles = [
            item
            for item in self.config.destination_profiles
            if item.get("profile_id") != profile_id
        ]
        profiles.append(profile.copy())
        self.config.destination_profiles = profiles
        self.save_config(self._config_to_dict())

    def delete_destination_profile(self, profile_id: str) -> None:
        """Delete a profile and clear it when it is currently active."""
        self.config.destination_profiles = [
            profile
            for profile in self.config.destination_profiles
            if profile.get("profile_id") != profile_id
        ]
        if self.config.active_destination_profile_id == profile_id:
            self.config.active_destination_profile_id = ""
        self.save_config(self._config_to_dict())

    def set_active_destination_profile(self, profile_id: str) -> None:
        """Persist the profile selected for the next session."""
        self.config.active_destination_profile_id = profile_id
        self.save_config(self._config_to_dict())

    def load_server(self, server_id: str) -> bool:
        """Load a server configuration as the current active server."""
        server_config = self.config.servers.get(server_id)
        if not server_config:
            logger.error(f"Settings: Server not found: {server_id}")
            return False

        self.config.username = server_config.get("username", "")
        self.config.host = server_config.get("host", "")
        self.config.ssh_key_path = server_config.get(
            "ssh_key_path", os.path.expanduser(DEFAULT_SSH_KEY_PATH)
        )
        self.config.ssh_port = server_config.get("ssh_port", DEFAULT_SSH_PORT)
        self.config.remote_base_dir = server_config.get(
            "remote_base_dir", DEFAULT_REMOTE_BASE_DIR
        )
        self.config.current_server_id = server_id
        return True

    def get_bookmarks(self) -> list[str]:
        """Return bookmarks for the active server, falling back to legacy globals."""
        server_config = self.get_server(self.config.current_server_id)
        if server_config is None:
            return list(self.config.bookmarks)

        bookmarks = server_config.get("bookmarks")
        if bookmarks is None:
            bookmarks = list(self.config.bookmarks)
            server_config["bookmarks"] = bookmarks
        return list(bookmarks)

    def set_bookmarks(self, bookmarks: list[str]) -> None:
        """Persist bookmarks on the active server configuration."""
        server_config = self.get_server(self.config.current_server_id)
        if server_config is None:
            self.config.bookmarks = bookmarks
        else:
            server_config["bookmarks"] = bookmarks
        self.save_config(self._config_to_dict())

    def get_default_bookmark(self) -> str:
        """Return the default bookmark for the active server."""
        server_config = self.get_server(self.config.current_server_id)
        if server_config is None:
            return ""
        return server_config.get("default_bookmark", "")

    def set_default_bookmark(self, bookmark: str) -> None:
        """Persist the default bookmark on the active server configuration."""
        server_config = self.get_server(self.config.current_server_id)
        if server_config is None:
            return
        server_config["default_bookmark"] = bookmark
        self.save_config(self._config_to_dict())

    def _config_to_dict(self) -> dict:
        """Convert current config to dictionary for saving."""
        return {
            "servers": self.config.servers,
            "current_server_id": self.config.current_server_id,
            "default_server_id": self.config.default_server_id,
            "destination_profiles": self.config.destination_profiles,
            "active_destination_profile_id": (
                self.config.active_destination_profile_id
            ),
            "username": self.config.username,
            "host": self.config.host,
            "ssh_key_path": self.config.ssh_key_path,
            "ssh_port": self.config.ssh_port,
            "remote_base_dir": self.config.remote_base_dir,
            "delete_after_transfer": self.config.delete_after_transfer,
            "download_directory": self.config.download_directory,
            "reveal_in_finder_after_download": self.config.reveal_in_finder_after_download,
            "notify_on_transfer_complete": self.config.notify_on_transfer_complete,
            "notify_sound": self.config.notify_sound,
            "compress_folders_before_transfer": self.config.compress_folders_before_transfer,
            "use_rsync": self.config.use_rsync,
            "hide_nfo_files": self.config.hide_nfo_files,
            "show_detail_panel": self.config.show_detail_panel,
            "prevent_sleep_during_transfer": self.config.prevent_sleep_during_transfer,
            "skip_patterns": list(self.config.skip_patterns),
            "last_modified": self.config.last_modified,
            "bookmarks": self.config.bookmarks,
            "theme_mode": self.config.theme_mode,
            "max_parallel_transfers": self.config.max_parallel_transfers,
            "omdb_api_key": self.config.omdb_api_key,
            "tmdb_api_key": self.config.tmdb_api_key,
        }
