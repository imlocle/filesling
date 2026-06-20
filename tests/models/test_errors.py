"""
Tests for the custom exception hierarchy.
"""

from src.models.errors import (
    AuthenticationError,
    ConfigurationLoadError,
    ConfigurationSaveError,
    ConnectionLostError,
    FileAccessError,
    FileDeletionError,
    FileSlingError,
    FileUploadError,
    InvalidConfigurationError,
    IPAddressValidationError,
    PathValidationError,
    RemoteDirectoryError,
    SFTPConnectionError,
    SSHConnectionError,
    SSHKeyValidationError,
    TransferVerificationError,
)


class TestFileSlingError:
    def test_basic_message(self):
        err = FileSlingError("something went wrong")
        assert err.message == "something went wrong"
        assert err.details is None
        assert str(err) == "something went wrong"

    def test_with_details(self):
        err = FileSlingError("failed", details="check the logs")
        assert err.message == "failed"
        assert err.details == "check the logs"
        assert "check the logs" in str(err)

    def test_is_exception(self):
        err = FileSlingError("test")
        assert isinstance(err, Exception)


class TestConnectionErrors:
    def test_ssh_connection_error(self):
        err = SSHConnectionError("timeout", details="host unreachable")
        assert err.message == "timeout"
        assert err.details == "host unreachable"
        assert isinstance(err, FileSlingError)

    def test_sftp_connection_error(self):
        err = SFTPConnectionError("session failed")
        assert isinstance(err, FileSlingError)

    def test_connection_lost_error(self):
        err = ConnectionLostError("socket closed")
        assert err.message == "socket closed"

    def test_authentication_error(self):
        err = AuthenticationError("bad key", details="permission denied")
        assert "bad key" in str(err)


class TestTransferErrors:
    def test_file_upload_error(self):
        err = FileUploadError("upload failed", file_path="/tmp/test.mp4")
        assert err.file_path == "/tmp/test.mp4"
        assert "upload failed" in str(err)
        assert "/tmp/test.mp4" in str(err)

    def test_remote_directory_error(self):
        err = RemoteDirectoryError("mkdir failed", file_path="/remote/dir")
        assert err.file_path == "/remote/dir"

    def test_transfer_verification_error(self):
        err = TransferVerificationError(
            "size mismatch",
            file_path="/tmp/file.bin",
            details="local: 100, remote: 50",
        )
        assert err.file_path == "/tmp/file.bin"
        assert "size mismatch" in str(err)

    def test_no_file_path(self):
        err = FileUploadError("generic failure")
        assert err.file_path is None
        assert "/tmp" not in str(err)


class TestConfigurationErrors:
    def test_invalid_configuration(self):
        err = InvalidConfigurationError("bad field", field="host")
        assert err.field == "host"
        assert err.message == "bad field"

    def test_load_error(self):
        err = ConfigurationLoadError("cannot read", details="permission denied")
        assert isinstance(err, FileSlingError)

    def test_save_error(self):
        err = ConfigurationSaveError("cannot write")
        assert err.message == "cannot write"


class TestFileSystemErrors:
    def test_file_access_error(self):
        err = FileAccessError("denied", path="/etc/shadow")
        assert err.path == "/etc/shadow"
        assert "denied" in str(err)
        assert "/etc/shadow" in str(err)

    def test_file_deletion_error(self):
        err = FileDeletionError("in use", path="/tmp/locked.file")
        assert err.path == "/tmp/locked.file"


class TestValidationErrors:
    def test_ip_validation(self):
        err = IPAddressValidationError("not an IP")
        assert err.message == "not an IP"

    def test_path_validation(self):
        err = PathValidationError("must be absolute")
        assert isinstance(err, FileSlingError)

    def test_ssh_key_validation(self):
        err = SSHKeyValidationError("key not found", details="/bad/path")
        assert err.details == "/bad/path"
