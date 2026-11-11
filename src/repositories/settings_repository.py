"""Repository for the user's JSON settings file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.models.errors import ConfigurationLoadError, ConfigurationSaveError
from src.utils.constants import APP_DATA_DIR, CONFIG_JSON
from src.utils.json_file import read_json_file, write_json_file_atomic


class SettingsRepository:
    """Read bundled or user settings and persist the user's configuration."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or APP_DATA_DIR / CONFIG_JSON

    def load(self) -> dict:
        """Load settings, returning an empty mapping when the file is absent."""
        try:
            data = read_json_file(self.path, default={})
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as error:
            raise ConfigurationLoadError(
                "Invalid JSON in configuration file",
                details=f"File: {self.path}, Error: {error}",
            ) from error
        except PermissionError as error:
            raise ConfigurationLoadError(
                "Cannot read configuration file",
                details=f"Permission denied: {self.path}",
            ) from error
        except OSError:
            return {}

    def save(self, config: dict) -> None:
        """Atomically persist settings with private permissions on Unix systems."""
        serializable = config.copy()
        patterns = serializable.get("skip_patterns")
        if isinstance(patterns, set):
            serializable["skip_patterns"] = list(patterns)

        try:
            write_json_file_atomic(
                self.path,
                serializable,
                indent=4,
                directory_mode=0o700,
                file_mode=0o600,
            )
        except PermissionError as error:
            raise ConfigurationSaveError(
                "Permission denied writing config", details=f"Path: {self.path}"
            ) from error
        except Exception as error:
            raise ConfigurationSaveError(
                "Failed to save configuration",
                details=f"Path: {self.path}, Error: {error}",
            ) from error
