"""
Shared fixtures for FileSling tests.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_config():
    """A valid sample configuration dict."""
    return {
        "servers": {
            "test-server": {
                "name": "Test Server",
                "connection_type": "ssh",
                "username": "testuser",
                "host": "192.168.1.100",
                "ssh_key_path": "~/.ssh/id_rsa",
                "ssh_port": 22,
                "remote_base_dir": "/home/testuser",
                "bookmarks": ["/home/testuser/files"],
                "default_bookmark": "/home/testuser/files",
            },
            "test-phone": {
                "name": "Test Phone",
                "connection_type": "adb",
                "device_id": "ABC123",
                "remote_base_dir": "/storage/emulated/0",
            },
        },
        "current_server_id": "test-server",
        "default_server_id": "test-server",
        "username": "testuser",
        "host": "192.168.1.100",
        "ssh_key_path": "~/.ssh/id_rsa",
        "ssh_port": 22,
        "remote_base_dir": "/home/testuser",
        "delete_after_transfer": True,
        "download_directory": "~/Downloads",
        "reveal_in_finder_after_download": False,
        "notify_on_transfer_complete": True,
        "notify_sound": True,
        "compress_folders_before_transfer": False,
        "skip_patterns": [".DS_Store", "._*"],
        "skip_exit_confirm": False,
        "bookmarks": [],
        "theme_mode": "system",
        "max_parallel_transfers": 1,
        "last_modified": "",
    }


@pytest.fixture
def sample_files(tmp_dir):
    """Create sample files in a temp directory for transfer testing."""
    files = {}
    for name in ["video.mp4", "song.mp3", "photo.jpg", "archive.zip", "readme.txt"]:
        path = tmp_dir / name
        path.write_text(f"content of {name}")
        files[name] = path

    # Create a subdirectory with files
    sub = tmp_dir / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content")
    files["subdir"] = sub

    return files
