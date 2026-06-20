"""
Unit tests for FileOperationsController.

Tests delete, move, and create_folder logic with mocked views and SFTP.
"""

from __future__ import annotations

import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

from src.controllers.file_operations_controller import FileOperationsController
from src.models.errors import ConnectionLostError, FileDeletionError

from PySide6.QtWidgets import QMessageBox


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_view():
    """Create a mock MainWindow with a remote_explorer attached."""
    view = MagicMock()
    view.remote_explorer = MagicMock()
    view.remote_explorer.sftp = MagicMock()  # Simulate remote connection
    view.remote_explorer.current_path = "/mnt/external/Movies"
    view.remote_explorer.tree_widget = MagicMock()
    return view


@pytest.fixture
def mock_settings():
    """Create a mock Settings object."""
    settings = MagicMock()
    settings.remote_base_dir = "/mnt/external"
    settings.config.current_server_id = "test-server"
    return settings


@pytest.fixture
def mock_history():
    """Create a mock ActivityHistoryService."""
    return MagicMock()


@pytest.fixture
def controller(mock_view, mock_settings, mock_history):
    """Create a FileOperationsController with mocked dependencies."""
    return FileOperationsController(
        view=mock_view,
        settings=mock_settings,
        history=mock_history,
    )


# ---------------------------------------------------------------------------
# DELETE — single item
# ---------------------------------------------------------------------------


class TestDeleteItem:
    def test_delete_remote_file_confirmed(self, controller, mock_view, mock_history):
        """Deleting a remote file should call sftp.remove and log to history."""
        # stat says it's a file (not a directory)
        file_stat = MagicMock()
        file_stat.st_mode = 0o100644  # S_IFREG | 0o644
        mock_view.remote_explorer.sftp.stat.return_value = file_stat

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_item("/mnt/external/Movies/old.mp4")

        mock_view.remote_explorer.sftp.remove.assert_called_once_with(
            "/mnt/external/Movies/old.mp4"
        )
        mock_view.remote_explorer.refresh.assert_called_once()
        mock_history.add.assert_called_once()
        assert mock_history.add.call_args.kwargs["action"] == "delete"

    def test_delete_remote_file_cancelled(self, controller, mock_view):
        """Cancelling delete should not call sftp.remove."""
        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.No
            controller.delete_item("/mnt/external/Movies/keep.mp4")

        mock_view.remote_explorer.sftp.remove.assert_not_called()
        mock_view.remote_explorer.sftp.rmdir.assert_not_called()

    def test_delete_remote_directory(self, controller, mock_view, mock_history):
        """Deleting a remote directory should use recursive deletion."""
        sftp = mock_view.remote_explorer.sftp
        dir_stat = MagicMock()
        dir_stat.st_mode = 0o40755  # S_IFDIR | 0o755
        sftp.stat.return_value = dir_stat
        sftp.listdir.return_value = []  # empty dir

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_item("/mnt/external/Movies/EmptyDir")

        sftp.rmdir.assert_called_with("/mnt/external/Movies/EmptyDir")

    def test_delete_local_file(self, controller, mock_view, mock_history, tmp_path):
        """Deleting a local file should use os.remove."""
        mock_view.remote_explorer.sftp = None  # Local mode

        test_file = tmp_path / "local.txt"
        test_file.write_text("hello")

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_item(str(test_file))

        assert not test_file.exists()
        mock_history.add.assert_called_once()

    def test_delete_local_directory(self, controller, mock_view, mock_history, tmp_path):
        """Deleting a local directory should use shutil.rmtree."""
        mock_view.remote_explorer.sftp = None  # Local mode

        test_dir = tmp_path / "subdir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("content")

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_item(str(test_dir))

        assert not test_dir.exists()

    def test_delete_connection_lost(self, controller, mock_view):
        """Connection lost during delete should show warning."""
        sftp = mock_view.remote_explorer.sftp
        sftp.remove.side_effect = IOError("Socket is closed")
        file_stat = MagicMock()
        file_stat.st_mode = 0o100644
        sftp.stat.return_value = file_stat

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_item("/mnt/external/Movies/gone.mp4")
            MockMB.warning.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE — multiple items
# ---------------------------------------------------------------------------


class TestDeleteMultiple:
    def test_delete_multiple_confirmed(self, controller, mock_view, mock_history):
        """Batch delete should delete all items and log each."""
        sftp = mock_view.remote_explorer.sftp
        file_stat = MagicMock()
        file_stat.st_mode = 0o100644
        sftp.stat.return_value = file_stat

        paths = [
            "/mnt/external/Movies/a.mp4",
            "/mnt/external/Movies/b.mp4",
            "/mnt/external/Movies/c.mp4",
        ]

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_items(paths)

        assert sftp.remove.call_count == 3
        assert mock_history.add.call_count == 3
        mock_view.remote_explorer.refresh.assert_called_once()

    def test_delete_multiple_cancelled(self, controller, mock_view):
        """Cancelling batch delete should not delete anything."""
        paths = ["/mnt/external/a.mp4", "/mnt/external/b.mp4"]

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.No
            controller.delete_items(paths)

        mock_view.remote_explorer.sftp.remove.assert_not_called()

    def test_delete_single_item_routes_to_delete_item(self, controller):
        """delete_items with one path should delegate to delete_item."""
        with patch.object(controller, "delete_item") as mock_delete:
            controller.delete_items(["/mnt/external/single.mp4"])
            mock_delete.assert_called_once_with("/mnt/external/single.mp4")

    def test_delete_empty_list(self, controller, mock_view):
        """delete_items with empty list should be a no-op."""
        controller.delete_items([])
        mock_view.remote_explorer.sftp.remove.assert_not_called()

    def test_delete_partial_failure(self, controller, mock_view, mock_history):
        """If one delete fails, others should still proceed."""
        sftp = mock_view.remote_explorer.sftp
        file_stat = MagicMock()
        file_stat.st_mode = 0o100644
        sftp.stat.return_value = file_stat

        call_count = [0]

        def side_effect(path):
            call_count[0] += 1
            if call_count[0] == 2:
                raise IOError("Permission denied")

        sftp.remove.side_effect = side_effect

        paths = ["/mnt/external/a.mp4", "/mnt/external/b.mp4", "/mnt/external/c.mp4"]

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.delete_items(paths)

        # First and third succeed, second fails
        assert mock_history.add.call_count == 2


# ---------------------------------------------------------------------------
# MOVE — single item
# ---------------------------------------------------------------------------


class TestMoveItem:
    def test_move_remote_confirmed(self, controller, mock_view, mock_history):
        """Moving a remote file should call sftp.rename."""
        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.move_item(
                "/mnt/external/Movies/movie.mp4",
                "/mnt/external/TV Shows/movie.mp4",
            )

        mock_view.remote_explorer.sftp.rename.assert_called_once_with(
            "/mnt/external/Movies/movie.mp4",
            "/mnt/external/TV Shows/movie.mp4",
        )
        mock_history.add.assert_called_once()
        assert mock_history.add.call_args.kwargs["action"] == "move"

    def test_move_cancelled(self, controller, mock_view):
        """Cancelling move should not call sftp.rename."""
        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.No
            controller.move_item("/mnt/external/a.mp4", "/mnt/external/b.mp4")

        mock_view.remote_explorer.sftp.rename.assert_not_called()

    def test_move_into_self_blocked(self, controller, mock_view):
        """Moving an item into itself should show an error."""
        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            controller.move_item(
                "/mnt/external/Movies",
                "/mnt/external/Movies/Subdir",
            )
            MockMB.critical.assert_called_once()
        mock_view.remote_explorer.sftp.rename.assert_not_called()

    def test_move_same_path_blocked(self, controller, mock_view):
        """Moving to the same path should show an error."""
        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            controller.move_item(
                "/mnt/external/Movies/a.mp4",
                "/mnt/external/Movies/a.mp4",
            )
            MockMB.critical.assert_called_once()

    def test_move_local_file(self, controller, mock_view, mock_history, tmp_path):
        """Moving a local file should use shutil.move."""
        mock_view.remote_explorer.sftp = None  # Local mode

        src = tmp_path / "source.txt"
        src.write_text("content")
        dest = tmp_path / "dest" / "source.txt"

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller._move_single(str(src), str(dest), confirm=True)

        assert not src.exists()
        assert dest.exists()
        mock_history.add.assert_called_once()


# ---------------------------------------------------------------------------
# MOVE — multiple items
# ---------------------------------------------------------------------------


class TestMoveMultiple:
    def test_move_multiple_confirmed(self, controller, mock_view, mock_history):
        """Batch move should move all items."""
        moves = [
            ("/mnt/external/Movies/a.mp4", "/mnt/external/TV/a.mp4"),
            ("/mnt/external/Movies/b.mp4", "/mnt/external/TV/b.mp4"),
        ]

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.move_items(moves)

        assert mock_view.remote_explorer.sftp.rename.call_count == 2
        mock_view.remote_explorer.refresh.assert_called()

    def test_move_multiple_cancelled(self, controller, mock_view):
        """Cancelling batch move should not move anything."""
        moves = [
            ("/mnt/external/a.mp4", "/mnt/external/dest/a.mp4"),
            ("/mnt/external/b.mp4", "/mnt/external/dest/b.mp4"),
        ]

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.No
            controller.move_items(moves)

        mock_view.remote_explorer.sftp.rename.assert_not_called()

    def test_move_empty_list(self, controller, mock_view):
        """Empty moves list should be a no-op."""
        controller.move_items([])
        mock_view.remote_explorer.sftp.rename.assert_not_called()

    def test_move_single_in_list(self, controller, mock_view, mock_history):
        """Single-item list should delegate to _move_single with confirm."""
        moves = [("/mnt/external/a.mp4", "/mnt/external/dest/a.mp4")]

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Yes = QMessageBox.StandardButton.Yes
            MockMB.StandardButton.No = QMessageBox.StandardButton.No
            MockMB.question.return_value = QMessageBox.StandardButton.Yes
            controller.move_items(moves)

        mock_view.remote_explorer.sftp.rename.assert_called_once()


# ---------------------------------------------------------------------------
# CREATE FOLDER
# ---------------------------------------------------------------------------


class TestCreateFolder:
    def test_create_remote_folder(self, controller, mock_view):
        """Creating a remote folder should call sftp.mkdir."""
        controller.create_folder("/mnt/external/Movies/NewFolder")

        mock_view.remote_explorer.sftp.mkdir.assert_called_once_with(
            "/mnt/external/Movies/NewFolder"
        )
        mock_view.remote_explorer.refresh.assert_called_once()

    def test_create_local_folder(self, controller, mock_view, tmp_path):
        """Creating a local folder should use os.makedirs."""
        mock_view.remote_explorer.sftp = None  # Local mode

        folder_path = str(tmp_path / "new_dir" / "nested")
        controller.create_folder(folder_path)

        assert os.path.isdir(folder_path)

    def test_create_folder_already_exists(self, controller, mock_view):
        """Creating an existing folder should show a warning."""
        mock_view.remote_explorer.sftp.mkdir.side_effect = FileExistsError()

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            controller.create_folder("/mnt/external/Movies/Existing")
            MockMB.warning.assert_called_once()

    def test_create_folder_no_connection(self, controller, mock_view):
        """Creating a folder with no sftp should show error."""
        mock_view.remote_explorer.sftp = MagicMock()
        mock_view.remote_explorer.sftp.mkdir.side_effect = RuntimeError("No connection")

        with patch("src.controllers.file_operations_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            controller.create_folder("/mnt/external/Movies/Broken")
            MockMB.critical.assert_called_once()
