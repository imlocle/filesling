"""
Unit tests for ffmpeg_service.

Tests video detection, duration parsing, ffmpeg checks, and transport resolution.
"""

from unittest.mock import MagicMock

import pytest

from src.services.ffmpeg_service import (
    VIDEO_EXTENSIONS,
    _get_transport,
    check_ffmpeg_installed,
    get_video_duration,
    is_video_file,
    replace_original,
)


# ---------------------------------------------------------------------------
# is_video_file
# ---------------------------------------------------------------------------


class TestIsVideoFile:
    def test_common_video_extensions(self):
        assert is_video_file("movie.mp4") is True
        assert is_video_file("show.mkv") is True
        assert is_video_file("clip.avi") is True
        assert is_video_file("video.mov") is True
        assert is_video_file("stream.webm") is True
        assert is_video_file("file.m4v") is True
        assert is_video_file("broadcast.ts") is True

    def test_non_video_extensions(self):
        assert is_video_file("photo.jpg") is False
        assert is_video_file("song.mp3") is False
        assert is_video_file("doc.pdf") is False
        assert is_video_file("data.json") is False
        assert is_video_file("readme.txt") is False
        assert is_video_file("archive.zip") is False

    def test_case_insensitive(self):
        assert is_video_file("MOVIE.MP4") is True
        assert is_video_file("Show.MKV") is True
        assert is_video_file("VIDEO.AVI") is True

    def test_no_extension(self):
        assert is_video_file("noext") is False
        assert is_video_file("") is False

    def test_hidden_files(self):
        assert is_video_file(".hidden.mp4") is True
        assert is_video_file(".DS_Store") is False

    def test_nfo_file(self):
        assert is_video_file("movie.nfo") is False

    def test_video_extensions_constant(self):
        """VIDEO_EXTENSIONS should contain all expected formats."""
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mkv" in VIDEO_EXTENSIONS
        assert ".avi" in VIDEO_EXTENSIONS
        assert ".mov" in VIDEO_EXTENSIONS
        assert ".webm" in VIDEO_EXTENSIONS
        assert ".flv" in VIDEO_EXTENSIONS
        assert ".wmv" in VIDEO_EXTENSIONS
        assert ".m4v" in VIDEO_EXTENSIONS
        assert ".mpg" in VIDEO_EXTENSIONS
        assert ".mpeg" in VIDEO_EXTENSIONS
        assert ".ts" in VIDEO_EXTENSIONS
        assert ".divx" in VIDEO_EXTENSIONS
        assert ".xvid" in VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# _get_transport
# ---------------------------------------------------------------------------


class TestGetTransport:
    def test_sftp_client_path(self):
        """SFTPClient: get_channel() -> get_transport()."""
        transport = MagicMock()
        channel = MagicMock()
        channel.get_transport.return_value = transport

        client = MagicMock()
        client.get_channel.return_value = channel

        result = _get_transport(client)
        assert result is transport

    def test_ssh_client_path(self):
        """SSHClient: get_transport() directly."""
        transport = MagicMock()
        client = MagicMock(spec=["get_transport"])
        client.get_transport.return_value = transport

        result = _get_transport(client)
        assert result is transport

    def test_no_transport_available(self):
        """Object with neither get_channel nor get_transport returns None."""
        client = MagicMock(spec=[])
        result = _get_transport(client)
        assert result is None

    def test_null_channel(self):
        """If get_channel returns None, try get_transport."""
        transport = MagicMock()
        client = MagicMock()
        client.get_channel.return_value = None
        client.get_transport.return_value = transport

        result = _get_transport(client)
        assert result is transport


# ---------------------------------------------------------------------------
# check_ffmpeg_installed
# ---------------------------------------------------------------------------


class TestCheckFfmpegInstalled:
    def test_ffmpeg_found(self):
        transport = MagicMock()
        session = MagicMock()
        session.recv.return_value = b"/usr/bin/ffmpeg"
        session.recv_exit_status.return_value = 0
        transport.open_session.return_value = session

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        assert check_ffmpeg_installed(client) is True
        session.close.assert_called_once()

    def test_ffmpeg_not_found(self):
        transport = MagicMock()
        session = MagicMock()
        session.recv.return_value = b""
        session.recv_exit_status.return_value = 1
        transport.open_session.return_value = session

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        assert check_ffmpeg_installed(client) is False

    def test_no_transport(self):
        client = MagicMock(spec=[])
        assert check_ffmpeg_installed(client) is False

    def test_exception_returns_false(self):
        client = MagicMock()
        client.get_channel.side_effect = Exception("connection lost")
        assert check_ffmpeg_installed(client) is False


# ---------------------------------------------------------------------------
# get_video_duration
# ---------------------------------------------------------------------------


class TestGetVideoDuration:
    def test_duration_parsed(self):
        transport = MagicMock()
        session = MagicMock()
        session.recv.return_value = b"3723.45"
        transport.open_session.return_value = session

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        result = get_video_duration(client, "/remote/video.mp4")
        assert result == 3723.45
        session.close.assert_called_once()

    def test_empty_output_returns_zero(self):
        transport = MagicMock()
        session = MagicMock()
        session.recv.return_value = b""
        transport.open_session.return_value = session

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        assert get_video_duration(client, "/remote/video.mp4") == 0.0

    def test_invalid_output_returns_zero(self):
        transport = MagicMock()
        session = MagicMock()
        session.recv.return_value = b"N/A"
        transport.open_session.return_value = session

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        assert get_video_duration(client, "/remote/video.mp4") == 0.0

    def test_no_transport_returns_zero(self):
        client = MagicMock(spec=[])
        assert get_video_duration(client, "/remote/video.mp4") == 0.0

    def test_exception_returns_zero(self):
        client = MagicMock()
        client.get_channel.side_effect = OSError("disconnected")
        assert get_video_duration(client, "/remote/video.mp4") == 0.0


# ---------------------------------------------------------------------------
# replace_original
# ---------------------------------------------------------------------------


class TestReplaceOriginal:
    def test_replace_different_extension(self):
        """Replacing .mkv original with .mp4 converted should rm + mv."""
        transport = MagicMock()
        session1 = MagicMock()
        session1.recv_exit_status.return_value = 0
        session2 = MagicMock()
        session2.recv_exit_status.return_value = 0
        transport.open_session.side_effect = [session1, session2]

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        replace_original(client, "/remote/movie.mkv", "/remote/movie_converted.mp4")

        # First call: rm original
        session1.exec_command.assert_called_once()
        rm_cmd = session1.exec_command.call_args[0][0]
        assert "rm -f" in rm_cmd
        assert "movie.mkv" in rm_cmd

        # Second call: mv converted to final
        session2.exec_command.assert_called_once()
        mv_cmd = session2.exec_command.call_args[0][0]
        assert "mv" in mv_cmd
        assert "movie_converted.mp4" in mv_cmd
        assert "movie.mp4" in mv_cmd  # final name

    def test_replace_same_extension(self):
        """If original is .mp4 and converted is .mp4, no rm needed (same final path)."""
        transport = MagicMock()
        session1 = MagicMock()
        session1.recv_exit_status.return_value = 0
        # Only mv should be called (original_path == final_path skips rm)
        transport.open_session.return_value = session1

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        replace_original(client, "/remote/movie.mp4", "/remote/movie_converted.mp4")

        # The rm is skipped because original.mp4 == final.mp4
        mv_cmd = session1.exec_command.call_args[0][0]
        assert "mv" in mv_cmd

    def test_mv_failure_raises(self):
        """If mv fails, should raise RuntimeError."""
        transport = MagicMock()
        session1 = MagicMock()
        session1.recv_exit_status.return_value = 0
        session2 = MagicMock()
        session2.recv_exit_status.return_value = 1  # mv fails
        transport.open_session.side_effect = [session1, session2]

        client = MagicMock()
        client.get_channel.return_value = MagicMock(get_transport=MagicMock(return_value=transport))

        with pytest.raises(RuntimeError, match="Failed to rename"):
            replace_original(client, "/remote/movie.mkv", "/remote/movie_converted.mp4")

    def test_no_transport_raises(self):
        """No SSH connection should raise RuntimeError."""
        client = MagicMock(spec=[])

        with pytest.raises(RuntimeError, match="No SSH connection"):
            replace_original(client, "/remote/a.mkv", "/remote/a_converted.mp4")
