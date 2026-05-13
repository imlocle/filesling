"""
Custom exception hierarchy for Shuttle application.
"""

from typing import Optional

# ============================================================================
# Base Exception
# ============================================================================


class PiSyncError(Exception):
    """Base exception for all PiSync errors."""

    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


# ============================================================================
# Connection Errors
# ============================================================================


class ConnectionError(PiSyncError):
    """Base exception for connection-related errors."""


class SSHConnectionError(ConnectionError):
    """Failed to establish SSH connection."""


class SFTPConnectionError(ConnectionError):
    """Failed to establish SFTP connection."""


class ConnectionLostError(ConnectionError):
    """Active connection was lost unexpectedly."""


class AuthenticationError(ConnectionError):
    """SSH authentication failed."""


# ============================================================================
# Transfer Errors
# ============================================================================


class TransferError(PiSyncError):
    """Base exception for transfer operations."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        details: Optional[str] = None,
    ):
        self.file_path = file_path
        super().__init__(message, details)

    def __str__(self) -> str:
        base = super().__str__()
        if self.file_path:
            return f"{base}\nFile: {self.file_path}"
        return base


class RemoteDirectoryError(TransferError):
    """Failed to create or access remote directory."""


class FileUploadError(TransferError):
    """Failed to upload file to remote server."""


class TransferVerificationError(TransferError):
    """File transfer completed but verification failed."""


# ============================================================================
# Configuration Errors
# ============================================================================


class ConfigurationError(PiSyncError):
    """Base exception for configuration-related errors."""


class InvalidConfigurationError(ConfigurationError):
    """Configuration validation failed."""

    def __init__(
        self, message: str, field: Optional[str] = None, details: Optional[str] = None
    ):
        self.field = field
        super().__init__(message, details)


class ConfigurationLoadError(ConfigurationError):
    """Failed to load configuration file."""


class ConfigurationSaveError(ConfigurationError):
    """Failed to save configuration file."""


# ============================================================================
# File System Errors
# ============================================================================


class FileSystemError(PiSyncError):
    """Base exception for file system operations."""

    def __init__(
        self, message: str, path: Optional[str] = None, details: Optional[str] = None
    ):
        self.path = path
        super().__init__(message, details)

    def __str__(self) -> str:
        base = super().__str__()
        if self.path:
            return f"{base}\nPath: {self.path}"
        return base


class FileAccessError(FileSystemError):
    """Permission denied or file access error."""


class FileDeletionError(FileSystemError):
    """Failed to delete file or directory."""


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(PiSyncError):
    """Base exception for validation errors."""


class IPAddressValidationError(ValidationError):
    """Invalid IP address format."""


class PathValidationError(ValidationError):
    """Invalid path format or structure."""


class SSHKeyValidationError(ValidationError):
    """SSH key file invalid or inaccessible."""
