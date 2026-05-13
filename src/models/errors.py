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
    pass


class SSHConnectionError(ConnectionError):
    """Failed to establish SSH connection."""
    pass


class SFTPConnectionError(ConnectionError):
    """Failed to establish SFTP connection."""
    pass


class ConnectionLostError(ConnectionError):
    """Active connection was lost unexpectedly."""
    pass


class AuthenticationError(ConnectionError):
    """SSH authentication failed."""
    pass


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
    pass


class FileUploadError(TransferError):
    """Failed to upload file to remote server."""
    pass


class TransferVerificationError(TransferError):
    """File transfer completed but verification failed."""
    pass


# ============================================================================
# Configuration Errors
# ============================================================================


class ConfigurationError(PiSyncError):
    """Base exception for configuration-related errors."""
    pass


class InvalidConfigurationError(ConfigurationError):
    """Configuration validation failed."""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[str] = None):
        self.field = field
        super().__init__(message, details)


class ConfigurationLoadError(ConfigurationError):
    """Failed to load configuration file."""
    pass


class ConfigurationSaveError(ConfigurationError):
    """Failed to save configuration file."""
    pass


# ============================================================================
# File System Errors
# ============================================================================


class FileSystemError(PiSyncError):
    """Base exception for file system operations."""

    def __init__(self, message: str, path: Optional[str] = None, details: Optional[str] = None):
        self.path = path
        super().__init__(message, details)

    def __str__(self) -> str:
        base = super().__str__()
        if self.path:
            return f"{base}\nPath: {self.path}"
        return base


class FileAccessError(FileSystemError):
    """Permission denied or file access error."""
    pass


class FileDeletionError(FileSystemError):
    """Failed to delete file or directory."""
    pass


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(PiSyncError):
    """Base exception for validation errors."""
    pass


class IPAddressValidationError(ValidationError):
    """Invalid IP address format."""
    pass


class PathValidationError(ValidationError):
    """Invalid path format or structure."""
    pass


class SSHKeyValidationError(ValidationError):
    """SSH key file invalid or inaccessible."""
    pass
