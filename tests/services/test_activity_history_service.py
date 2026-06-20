"""
Tests for the activity history service.
"""

import json

import pytest

from src.services.activity_history_service import (
    ActivityHistoryService,
    ActivityRecord,
    MAX_HISTORY,
)


class TestActivityRecord:
    def test_defaults(self):
        record = ActivityRecord(filename="test.mp4", action="upload")
        assert record.filename == "test.mp4"
        assert record.action == "upload"
        assert record.source == ""
        assert record.destination == ""
        assert record.size_bytes == 0
        assert record.status == "completed"
        assert record.timestamp != ""  # auto-generated

    def test_custom_values(self):
        record = ActivityRecord(
            filename="video.mkv",
            action="download",
            source="/remote/video.mkv",
            destination="/local/Downloads",
            size_bytes=1024000,
            server_name="my-server",
        )
        assert record.size_bytes == 1024000
        assert record.server_name == "my-server"


class TestActivityHistoryService:
    @pytest.fixture
    def service(self, tmp_dir):
        """Create a service with a temp history file."""
        svc = ActivityHistoryService.__new__(ActivityHistoryService)
        svc._history_path = tmp_dir / "test_history.json"
        svc._records = []
        return svc

    def test_add_record(self, service):
        service.add(filename="test.mp4", action="upload", source="/tmp/test.mp4")
        assert len(service.records) == 1
        assert service.records[0].filename == "test.mp4"
        assert service.records[0].action == "upload"

    def test_add_with_direction_compat(self, service):
        service.add(filename="old.mp4", action="", direction="upload")
        assert service.records[0].action == "upload"

    def test_search(self, service):
        service.add(filename="video.mp4", action="upload")
        service.add(filename="photo.jpg", action="upload")
        service.add(filename="video_backup.mp4", action="download")

        results = service.search("video")
        assert len(results) == 2

    def test_search_case_insensitive(self, service):
        service.add(filename="MyVideo.MP4", action="upload")
        results = service.search("myvideo")
        assert len(results) == 1

    def test_has_been_uploaded(self, service):
        service.add(
            filename="test.mp4",
            action="upload",
            destination="/remote/files",
            status="completed",
        )
        assert service.has_been_uploaded("test.mp4", "/remote/files") is True
        assert service.has_been_uploaded("test.mp4", "/other/path") is False
        assert service.has_been_uploaded("other.mp4", "/remote/files") is False

    def test_clear(self, service):
        service.add(filename="a.txt", action="upload")
        service.add(filename="b.txt", action="download")
        assert len(service.records) == 2

        service.clear()
        assert len(service.records) == 0

    def test_max_history_limit(self, service):
        for i in range(MAX_HISTORY + 50):
            service.add(filename=f"file_{i}.txt", action="upload")

        assert len(service.records) <= MAX_HISTORY

    def test_persistence(self, tmp_dir):
        """Test that records persist to disk and can be reloaded."""
        history_path = tmp_dir / "history.json"

        # Create service and add records
        svc = ActivityHistoryService.__new__(ActivityHistoryService)
        svc._history_path = history_path
        svc._records = []
        svc.add(filename="persisted.mp4", action="upload")

        # Verify file was written
        assert history_path.exists()
        data = json.loads(history_path.read_text())
        assert len(data) == 1
        assert data[0]["filename"] == "persisted.mp4"

        # Create new service and verify it loads
        svc2 = ActivityHistoryService.__new__(ActivityHistoryService)
        svc2._history_path = history_path
        svc2._records = []
        svc2._load()
        assert len(svc2.records) == 1
        assert svc2.records[0].filename == "persisted.mp4"
