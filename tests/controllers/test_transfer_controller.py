"""
Tests for the transfer controller's QueuedTransfer dataclass.
"""

from src.controllers.transfer_controller import QueuedTransfer


class TestQueuedTransfer:
    def test_basic_creation(self):
        transfer = QueuedTransfer(
            local_paths=["/tmp/file.mp4"],
            remote_destination="/remote/uploads",
            delete_after=True,
            total_bytes=1024,
        )
        assert transfer.local_paths == ["/tmp/file.mp4"]
        assert transfer.remote_destination == "/remote/uploads"
        assert transfer.delete_after is True
        assert transfer.total_bytes == 1024
        assert transfer.attempts == 0

    def test_display_name_auto_generated(self):
        transfer = QueuedTransfer(
            local_paths=["/tmp/video.mp4"],
            remote_destination="/remote",
            delete_after=False,
        )
        assert transfer.display_name == "video.mp4"

    def test_display_name_multiple_files(self):
        transfer = QueuedTransfer(
            local_paths=["/tmp/a.mp4", "/tmp/b.mp4", "/tmp/c.mp4"],
            remote_destination="/remote",
            delete_after=False,
            total_bytes=100,
        )
        assert "a.mp4" in transfer.display_name
        assert "b.mp4" in transfer.display_name
        assert "c.mp4" in transfer.display_name

    def test_display_name_more_than_three(self):
        transfer = QueuedTransfer(
            local_paths=[f"/tmp/{i}.txt" for i in range(5)],
            remote_destination="/remote",
            delete_after=False,
            total_bytes=100,
        )
        assert "(+2 more)" in transfer.display_name

    def test_display_name_strips_trailing_slash(self):
        transfer = QueuedTransfer(
            local_paths=["/tmp/folder/"],
            remote_destination="/remote",
            delete_after=False,
            total_bytes=100,
        )
        assert transfer.display_name == "folder"

    def test_total_bytes_calculated_from_files(self, tmp_dir):
        # Create real files
        f1 = tmp_dir / "a.txt"
        f1.write_text("hello")  # 5 bytes
        f2 = tmp_dir / "b.txt"
        f2.write_text("world!")  # 6 bytes

        transfer = QueuedTransfer(
            local_paths=[str(f1), str(f2)],
            remote_destination="/remote",
            delete_after=False,
        )
        assert transfer.total_bytes == 11

    def test_total_bytes_calculated_from_directory(self, tmp_dir):
        sub = tmp_dir / "subdir"
        sub.mkdir()
        (sub / "file.txt").write_text("content")  # 7 bytes

        transfer = QueuedTransfer(
            local_paths=[str(sub)],
            remote_destination="/remote",
            delete_after=False,
        )
        assert transfer.total_bytes == 7

    def test_total_bytes_skips_hidden_files(self, tmp_dir):
        (tmp_dir / "visible.txt").write_text("yes")  # 3 bytes
        (tmp_dir / ".hidden").write_text("no")  # 2 bytes

        transfer = QueuedTransfer(
            local_paths=[str(tmp_dir)],
            remote_destination="/remote",
            delete_after=False,
        )
        # Only visible.txt should be counted
        assert transfer.total_bytes == 3

    def test_to_dict(self):
        transfer = QueuedTransfer(
            local_paths=["/tmp/file.mp4"],
            remote_destination="/remote",
            delete_after=True,
            total_bytes=500,
            display_name="file.mp4",
            attempts=2,
        )
        d = transfer.to_dict()
        assert d["local_paths"] == ["/tmp/file.mp4"]
        assert d["remote_destination"] == "/remote"
        assert d["delete_after"] is True
        assert d["total_bytes"] == 500
        assert d["display_name"] == "file.mp4"
        assert d["attempts"] == 2

    def test_from_dict(self):
        data = {
            "local_paths": ["/tmp/a.txt", "/tmp/b.txt"],
            "remote_destination": "/remote/dir",
            "delete_after": False,
            "total_bytes": 2048,
            "display_name": "a.txt, b.txt",
            "attempts": 1,
        }
        transfer = QueuedTransfer.from_dict(data)
        assert transfer.local_paths == ["/tmp/a.txt", "/tmp/b.txt"]
        assert transfer.remote_destination == "/remote/dir"
        assert transfer.delete_after is False
        assert transfer.total_bytes == 2048
        assert transfer.display_name == "a.txt, b.txt"
        assert transfer.attempts == 1

    def test_from_dict_with_missing_fields(self):
        data = {
            "local_paths": ["/tmp/x.txt"],
            "remote_destination": "/remote",
        }
        transfer = QueuedTransfer.from_dict(data)
        assert transfer.delete_after is True  # default
        assert transfer.total_bytes == 0
        assert transfer.attempts == 0

    def test_roundtrip_serialization(self, tmp_dir):
        f = tmp_dir / "test.bin"
        f.write_bytes(b"\x00" * 100)

        original = QueuedTransfer(
            local_paths=[str(f)],
            remote_destination="/remote/dest",
            delete_after=True,
        )
        restored = QueuedTransfer.from_dict(original.to_dict())

        assert restored.local_paths == original.local_paths
        assert restored.remote_destination == original.remote_destination
        assert restored.delete_after == original.delete_after
        assert restored.total_bytes == original.total_bytes
        assert restored.display_name == original.display_name
