"""
ServerConfig — typed model for server configurations.

Replaces raw dict access (server_config.get("key", default)) with a
validated dataclass that provides IDE autocomplete and prevents typo bugs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.utils.constants import (
    CONN_TYPE_SSH,
    DEFAULT_ADB_BASE_DIR,
    DEFAULT_REMOTE_BASE_DIR,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
)


@dataclass
class ServerConfig:
    """Typed server configuration model."""

    # Identity
    name: str = ""

    # Connection type: "ssh", "adb", or "ios"
    connection_type: str = CONN_TYPE_SSH

    # SSH fields
    host: str = ""
    username: str = ""
    ssh_key_path: str = DEFAULT_SSH_KEY_PATH
    ssh_port: int = DEFAULT_SSH_PORT
    password: str = ""
    key_passphrase: str = ""

    # Device fields (ADB / iOS)
    device_id: str = ""
    wifi_ip: str = ""

    # Path
    remote_base_dir: str = DEFAULT_REMOTE_BASE_DIR

    # Per-server overrides
    download_directory: str = ""
    extension_filter: str = ""

    # Navigation state
    bookmarks: List[str] = field(default_factory=list)
    default_bookmark: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ServerConfig":
        """Create a ServerConfig from a raw dict (the legacy format)."""
        return cls(
            name=data.get("name", ""),
            connection_type=data.get("connection_type", CONN_TYPE_SSH),
            host=data.get("host", ""),
            username=data.get("username", ""),
            ssh_key_path=data.get("ssh_key_path", DEFAULT_SSH_KEY_PATH),
            ssh_port=int(data.get("ssh_port", DEFAULT_SSH_PORT)),
            password=data.get("password", ""),
            key_passphrase=data.get("key_passphrase", ""),
            device_id=data.get("device_id", ""),
            wifi_ip=data.get("wifi_ip", ""),
            remote_base_dir=data.get(
                "remote_base_dir",
                (
                    "/DCIM"
                    if data.get("connection_type") == "ios"
                    else (
                        DEFAULT_ADB_BASE_DIR
                        if data.get("connection_type") == "adb"
                        else DEFAULT_REMOTE_BASE_DIR
                    )
                ),
            ),
            download_directory=data.get("download_directory", ""),
            extension_filter=data.get("extension_filter", ""),
            bookmarks=list(data.get("bookmarks", [])),
            default_bookmark=data.get("default_bookmark", ""),
        )

    def to_dict(self) -> dict:
        """Convert back to dict for JSON serialization."""
        d: dict = {
            "name": self.name,
            "connection_type": self.connection_type,
            "remote_base_dir": self.remote_base_dir,
        }

        if self.connection_type == CONN_TYPE_SSH:
            d["host"] = self.host
            d["username"] = self.username
            d["ssh_key_path"] = self.ssh_key_path
            d["ssh_port"] = self.ssh_port
            if self.password:
                d["password"] = self.password
            if self.key_passphrase:
                d["key_passphrase"] = self.key_passphrase
        else:
            d["device_id"] = self.device_id
            if self.wifi_ip:
                d["wifi_ip"] = self.wifi_ip

        if self.download_directory:
            d["download_directory"] = self.download_directory
        if self.extension_filter:
            d["extension_filter"] = self.extension_filter
        if self.bookmarks:
            d["bookmarks"] = self.bookmarks
        if self.default_bookmark:
            d["default_bookmark"] = self.default_bookmark

        return d

    @property
    def is_ssh(self) -> bool:
        return self.connection_type == "ssh"

    @property
    def is_adb(self) -> bool:
        return self.connection_type == "adb"

    @property
    def is_ios(self) -> bool:
        return self.connection_type == "ios"

    @property
    def has_password_auth(self) -> bool:
        """True if this server uses password auth instead of SSH key."""
        return bool(self.password)

    def get_download_directory(self, fallback: str) -> str:
        """Return per-server download dir, or fallback to global."""
        return self.download_directory or fallback
