"""
Unit tests for DownloadWorker.

Tests download logic with mocked SFTP connections.
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from src.workers.download_worker import DownloadWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_sftp():
    return MagicMock()


@pytest.fixture
def worker(qapp, mock_sftp):
    return DownloadWorker(
        sftp=mock_sftp,
        remote_paths=["/remote/video.mp4"],
        local_destination="/tmp/downloads",
        total_bytes=1024,
    )


class TestDownloadWorkerInit:
    def test_initialization(self, worker, mock_sftp):
        assert worker.sftp is mock_sftp
        assert worker.remote_paths == ["/remote/video.mp4"]
        assert worker.local_destination == "/tmp/downloads"
        assert worker._total_bytes == 1024
        assert worker._cumulative_bytes == 0

    def test_multiple_paths(self, qapp, mock_sftp):
        w = DownloadWorker(
            sftp=mock_sftp,
            remote_paths=["/remote/a.mp4", "/remote/b.mp4"],
            local_destination="/tmp",
            total_bytes=2048,
        )
        assert len(w.remote_paths) == 2


class TestIsRemoteDirectory:
    def test_directory(self, worker, mock_sftp):
        stat_result = MagicMock()
        stat_result.st_mode = 0o40755  # S_IFDIR
        mock_sftp.stat.return_value = stat_result
        assert worker._is_remote_directory("/remote/folder") is True

    def test_file(self, worker, mock_sftp):
        stat_result = MagicMock()
        stat_result.st_mode = 0o100644  # S_IFREG
        mock_sftp.stat.return_value = stat_result
        assert worker._is_remote_directory("/remote/file.mp4") is False

    def test_stat_error_returns_false(self, worker, mock_sftp):
        mock_sftp.stat.side_effect = IOError("No such file")
        assert worker._is_remote_directory("/remote/nonexistent") is False


class TestDownloadFile:
    def test_successful_download(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        stat_result = MagicMock()
        stat_result.st_size = 100
        mock_sftp.stat.return_value = stat_result

        # Mock sftp.get to create the file
        def fake_get(remote, local, callback=None):
            with open(local, "wb") as f:
                f.write(b"x" * 100)
            if callback:
                callback(100, 100)

        mock_sftp.get.side_effect = fake_get

        worker._download_file("/remote/test.txt", str(tmp_path))

        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").stat().st_size == 100
        assert worker._cumulative_bytes == 100

    def test_incomplete_download_removes_file(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        stat_result = MagicMock()
        stat_result.st_size = 1000
        mock_sftp.stat.return_value = stat_result

        # Create a partial file
        def fake_get(remote, local, callback=None):
            with open(local, "wb") as f:
                f.write(b"x" * 500)  # Only 500 of 1000 bytes

        mock_sftp.get.side_effect = fake_get

        with pytest.raises(IOError, match="Download incomplete"):
            worker._download_file("/remote/big.mp4", str(tmp_path))

        # Partial file should be cleaned up
        assert not (tmp_path / "big.mp4").exists()

    def test_connection_lost_raises(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        stat_result = MagicMock()
        stat_result.st_size = 100
        mock_sftp.stat.return_value = stat_result
        mock_sftp.get.side_effect = IOError("Socket is closed")

        from src.models.errors import ConnectionLostError

        with pytest.raises(ConnectionLostError):
            worker._download_file("/remote/test.mp4", str(tmp_path))


class TestDownloadFolder:
    def test_creates_local_folder(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        mock_sftp.listdir.return_value = []

        # stat returns dir
        stat_result = MagicMock()
        stat_result.st_mode = 0o40755
        mock_sftp.stat.return_value = stat_result

        worker._download_folder("/remote/folder", str(tmp_path))

        assert (tmp_path / "folder").is_dir()

    def test_skips_hidden_files(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        mock_sftp.listdir.return_value = [".DS_Store", "._metadata", "video.mp4"]

        # stat returns file for video.mp4
        file_stat = MagicMock()
        file_stat.st_mode = 0o100644
        file_stat.st_size = 50
        mock_sftp.stat.return_value = file_stat

        def fake_get(remote, local, callback=None):
            with open(local, "wb") as f:
                f.write(b"x" * 50)

        mock_sftp.get.side_effect = fake_get

        worker._download_folder("/remote/folder", str(tmp_path))

        # Only video.mp4 should be downloaded, not hidden files
        folder_dir = tmp_path / "folder"
        assert folder_dir.is_dir()
        contents = list(folder_dir.iterdir())
        assert len(contents) == 1
        assert contents[0].name == "video.mp4"


class TestRun:
    def test_emits_finished_on_success(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        worker.remote_paths = ["/remote/small.txt"]

        # File, not directory
        file_stat = MagicMock()
        file_stat.st_mode = 0o100644
        file_stat.st_size = 10
        mock_sftp.stat.return_value = file_stat

        def fake_get(remote, local, callback=None):
            with open(local, "wb") as f:
                f.write(b"x" * 10)

        mock_sftp.get.side_effect = fake_get

        finished = MagicMock()
        error = MagicMock()
        worker.finished.connect(finished)
        worker.error.connect(error)

        worker.run()

        finished.assert_called_once()
        error.assert_not_called()

    def test_emits_error_on_failure(self, worker, mock_sftp, tmp_path):
        worker.local_destination = str(tmp_path)
        worker.remote_paths = ["/remote/broken.mp4"]

        file_stat = MagicMock()
        file_stat.st_mode = 0o100644
        file_stat.st_size = 100
        mock_sftp.stat.return_value = file_stat
        mock_sftp.get.side_effect = Exception("disk full")

        finished = MagicMock()
        error = MagicMock()
        worker.finished.connect(finished)
        worker.error.connect(error)

        worker.run()

        finished.assert_not_called()
        error.assert_called_once()
        assert "disk full" in error.call_args[0][0]
