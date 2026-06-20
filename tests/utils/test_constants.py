"""
Tests for application constants.
"""

from src.utils.constants import (
    CONN_TYPE_ADB,
    CONN_TYPE_KEY,
    CONN_TYPE_SSH,
    DEFAULT_ADB_BASE_DIR,
    DEFAULT_REMOTE_BASE_DIR,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
    DUP_ACTION_CANCEL,
    DUP_ACTION_OVERWRITE,
    DUP_ACTION_SKIP,
    GITHUB_REPO_URL,
    SOFTWARE_NAME,
    VERSION,
)


class TestConstants:
    def test_software_name(self):
        assert SOFTWARE_NAME == "FileSling"

    def test_version_format(self):
        parts = VERSION.split(".")
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit()

    def test_connection_types(self):
        assert CONN_TYPE_SSH == "ssh"
        assert CONN_TYPE_ADB == "adb"
        assert CONN_TYPE_KEY == "connection_type"

    def test_defaults(self):
        assert DEFAULT_SSH_PORT == 22
        assert DEFAULT_SSH_KEY_PATH == "~/.ssh/id_rsa"
        assert DEFAULT_REMOTE_BASE_DIR == "/"
        assert DEFAULT_ADB_BASE_DIR == "/"

    def test_duplicate_actions(self):
        assert DUP_ACTION_OVERWRITE == "overwrite"
        assert DUP_ACTION_SKIP == "skip"
        assert DUP_ACTION_CANCEL == "cancel"

    def test_github_url(self):
        assert "github.com" in GITHUB_REPO_URL
        assert "filesling" in GITHUB_REPO_URL
