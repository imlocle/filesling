"""
Tests for the file deletion service.
"""

from unittest.mock import patch

import pytest

from src.models.errors import FileDeletionError
from src.services.file_deletion_service import FileDeletionService


class TestFileDeletionService:
    @pytest.fixture
    def service(self):
        return FileDeletionService()

    def test_delete_nonexistent_file(self, service):
        result = service.delete_file("/nonexistent/path/file.txt")
        assert result is False

    def test_delete_nonexistent_folder(self, service):
        result = service.delete_folder("/nonexistent/path/folder")
        assert result is False

    def test_delete_file_that_is_directory(self, service, tmp_dir):
        d = tmp_dir / "adir"
        d.mkdir()
        result = service.delete_file(str(d))
        assert result is False

    def test_delete_folder_that_is_file(self, service, tmp_dir):
        f = tmp_dir / "afile.txt"
        f.write_text("content")
        result = service.delete_folder(str(f))
        assert result is False

    @patch("src.services.file_deletion_service.send2trash")
    def test_delete_file_success(self, mock_trash, service, tmp_dir):
        f = tmp_dir / "deleteme.txt"
        f.write_text("bye")
        result = service.delete_file(str(f))
        assert result is True
        mock_trash.assert_called_once_with(str(f))

    @patch("src.services.file_deletion_service.send2trash")
    def test_delete_folder_success(self, mock_trash, service, tmp_dir):
        d = tmp_dir / "deletedir"
        d.mkdir()
        result = service.delete_folder(str(d))
        assert result is True
        mock_trash.assert_called_once_with(str(d))

    @patch("src.services.file_deletion_service.send2trash")
    def test_delete_file_raises_on_error(self, mock_trash, service, tmp_dir):
        f = tmp_dir / "locked.txt"
        f.write_text("locked")
        mock_trash.side_effect = PermissionError("denied")

        with pytest.raises(FileDeletionError) as exc_info:
            service.delete_file(str(f))
        assert exc_info.value.path == str(f)

    @patch("src.services.file_deletion_service.send2trash")
    def test_delete_folder_raises_on_error(self, mock_trash, service, tmp_dir):
        d = tmp_dir / "lockeddir"
        d.mkdir()
        mock_trash.side_effect = OSError("busy")

        with pytest.raises(FileDeletionError) as exc_info:
            service.delete_folder(str(d))
        assert exc_info.value.path == str(d)
