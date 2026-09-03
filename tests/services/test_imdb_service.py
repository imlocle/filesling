"""
Tests for the IMDb (OMDb-backed) metadata service.

Network calls are mocked — these tests never hit OMDb. They validate ID
normalization, field mapping, error handling, and the episode → show resolution.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.imdb_service import (
    IMDbLookupError,
    MetadataNotFoundError,
    _map_omdb_to_fields,
    _map_tmdb_episode,
    _map_tmdb_movie,
    _map_tmdb_tv,
    fetch_metadata,
    fetch_metadata_safe,
    fetch_show_name,
    normalize_imdb_id,
)

# --- Sample OMDb responses (shapes match the documented OMDb API) ---

SERIES_RESPONSE = {
    "Title": "The Challenge",
    "Year": "2009\u20132015",
    "Rated": "TV-14",
    "Genre": "Reality-TV, Action",
    "Director": "N/A",
    "Actors": "T.J. Lavin, Mark Long, Eric Nies",
    "Plot": "Contestants compete in extreme challenges.",
    "Type": "series",
    "Response": "True",
}

EPISODE_RESPONSE = {
    "Title": "The Final Battle",
    "Year": "2014",
    "Rated": "N/A",
    "Genre": "Reality-TV",
    "Director": "Jane Doe",
    "Actors": "T.J. Lavin, Someone Else",
    "Plot": "The finalists face off.",
    "Season": "24",
    "Episode": "15",
    "seriesID": "tt0983514",
    "Type": "episode",
    "Response": "True",
}


class TestNormalizeImdbId:
    def test_plain_id(self):
        assert normalize_imdb_id("tt0983514") == "tt0983514"

    def test_strips_whitespace(self):
        assert normalize_imdb_id("  tt0983514  ") == "tt0983514"

    def test_bare_numeric_gets_prefix(self):
        assert normalize_imdb_id("0983514") == "tt0983514"

    def test_extracts_from_url(self):
        url = "https://www.imdb.com/title/tt0983514/"
        assert normalize_imdb_id(url) == "tt0983514"

    def test_extracts_from_url_with_query(self):
        url = "https://www.imdb.com/title/tt0983514/?ref_=nv_sr_1"
        assert normalize_imdb_id(url) == "tt0983514"

    def test_empty_raises(self):
        with pytest.raises(IMDbLookupError):
            normalize_imdb_id("")

    def test_garbage_raises(self):
        with pytest.raises(IMDbLookupError):
            normalize_imdb_id("not-an-id")

    def test_wrong_prefix_raises(self):
        with pytest.raises(IMDbLookupError):
            normalize_imdb_id("nm0000123")  # person ID, not title


class TestMapOmdbToFields:
    def test_series_mapping(self):
        fields = _map_omdb_to_fields(SERIES_RESPONSE)
        assert fields["title"] == "The Challenge"
        # Year range → first year only
        assert fields["date"] == "2009"
        # Comma genres → semicolon
        assert fields["genre"] == "Reality-TV;Action"
        assert fields["artist"] == "T.J. Lavin;Mark Long;Eric Nies"
        assert fields["performer"] == "T.J. Lavin;Mark Long;Eric Nies"
        assert fields["description"] == "Contestants compete in extreme challenges."
        assert fields["rating"] == "TV-14"

    def test_na_values_omitted(self):
        # Director is "N/A" in the series response
        fields = _map_omdb_to_fields(SERIES_RESPONSE)
        assert "director" not in fields

    def test_episode_mapping(self):
        fields = _map_omdb_to_fields(EPISODE_RESPONSE)
        assert fields["title"] == "The Final Battle"
        assert fields["season_number"] == "24"
        assert fields["episode_sort"] == "15"
        assert fields["director"] == "Jane Doe"
        assert fields["date"] == "2014"
        # Rated is N/A here → omitted
        assert "rating" not in fields

    def test_empty_response(self):
        fields = _map_omdb_to_fields({"Response": "True"})
        assert fields == {}


class TestFetchMetadata:
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_series_fetch(self, mock_fetch):
        mock_fetch.return_value = SERIES_RESPONSE
        fields = fetch_metadata("tt0983514", "fakekey")
        assert fields["title"] == "The Challenge"
        mock_fetch.assert_called_once_with("tt0983514", "fakekey")

    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_episode_resolves_show_name(self, mock_fetch):
        # First call returns the episode; second call (series lookup) returns series
        mock_fetch.side_effect = [EPISODE_RESPONSE, SERIES_RESPONSE]
        fields = fetch_metadata("tt43730653", "fakekey")
        assert fields["season_number"] == "24"
        assert fields["show"] == "The Challenge"
        assert fields["album"] == "The Challenge"
        assert mock_fetch.call_count == 2

    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_episode_without_series_id(self, mock_fetch):
        episode = dict(EPISODE_RESPONSE)
        episode["seriesID"] = "N/A"
        mock_fetch.return_value = episode
        fields = fetch_metadata("tt43730653", "fakekey")
        # No show resolution, but episode fields still present
        assert "show" not in fields
        assert fields["season_number"] == "24"

    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_lookup_error_propagates(self, mock_fetch):
        mock_fetch.side_effect = IMDbLookupError("Invalid API key!")
        with pytest.raises(IMDbLookupError, match="Invalid API key"):
            fetch_metadata("tt0983514", "badkey")


class TestFetchMetadataSafe:
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_success_returns_fields_and_no_error(self, mock_fetch):
        mock_fetch.return_value = SERIES_RESPONSE
        fields, error = fetch_metadata_safe("tt0983514", "fakekey")
        assert error is None
        assert fields is not None
        assert fields["title"] == "The Challenge"

    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_failure_returns_none_and_message(self, mock_fetch):
        mock_fetch.side_effect = IMDbLookupError("boom")
        fields, error = fetch_metadata_safe("tt0983514", "fakekey")
        assert fields is None
        assert error == "boom"

    def test_invalid_id_returns_error(self):
        fields, error = fetch_metadata_safe("garbage", "fakekey")
        assert fields is None
        assert error is not None


class TestFetchShowName:
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_returns_title(self, mock_fetch):
        mock_fetch.return_value = SERIES_RESPONSE
        assert fetch_show_name("tt0983514", "fakekey") == "The Challenge"

    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_returns_empty_on_error(self, mock_fetch):
        mock_fetch.side_effect = IMDbLookupError("nope")
        assert fetch_show_name("tt0983514", "fakekey") == ""


class TestFetchOmdbJson:
    """Test the raw HTTP layer with urlopen mocked."""

    def test_no_api_key_raises(self):
        from src.services.imdb_service import _fetch_omdb_json

        with pytest.raises(IMDbLookupError, match="No OMDb API key"):
            _fetch_omdb_json("tt0983514", "")

    @patch("src.services.imdb_service.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        from src.services.imdb_service import _fetch_omdb_json

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(SERIES_RESPONSE).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        data = _fetch_omdb_json("tt0983514", "fakekey")
        assert data["Title"] == "The Challenge"

    @patch("src.services.imdb_service.urllib.request.urlopen")
    def test_omdb_error_response_raises(self, mock_urlopen):
        from src.services.imdb_service import _fetch_omdb_json

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"Response": "False", "Error": "Invalid API key!"}
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        with pytest.raises(IMDbLookupError, match="Invalid API key"):
            _fetch_omdb_json("tt0983514", "fakekey")

    @patch("src.services.imdb_service.urllib.request.urlopen")
    def test_http_401_raises_key_error(self, mock_urlopen):
        import urllib.error

        from src.services.imdb_service import _fetch_omdb_json

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="x", code=401, msg="Unauthorized", hdrs=None, fp=None
        )
        with pytest.raises(IMDbLookupError, match="key"):
            _fetch_omdb_json("tt0983514", "fakekey")


# --- Sample TMDB responses (shapes match TMDB v3 /find and /tv endpoints) ---

TMDB_FIND_EPISODE = {
    "movie_results": [],
    "tv_results": [],
    "tv_episode_results": [
        {
            "id": 123,
            "name": "New Episode",
            "overview": "A brand new episode plot.",
            "air_date": "2026-05-01",
            "season_number": 3,
            "episode_number": 7,
            "show_id": 456,
        }
    ],
}

TMDB_TV_SHOW = {
    "name": "My New Show",
    "first_air_date": "2024-01-01",
    "genres": [{"id": 18, "name": "Drama"}, {"id": 10765, "name": "Sci-Fi"}],
}

TMDB_FIND_MOVIE = {
    "movie_results": [
        {
            "id": 789,
            "title": "Some Movie",
            "release_date": "2020-06-15",
            "overview": "Movie plot.",
            "genre_ids": [28, 12],
        }
    ],
    "tv_results": [],
    "tv_episode_results": [],
}

TMDB_FIND_EMPTY = {
    "movie_results": [],
    "tv_results": [],
    "tv_episode_results": [],
}


class TestMapTmdb:
    def test_map_movie(self):
        fields = _map_tmdb_movie(TMDB_FIND_MOVIE["movie_results"][0], ["Action", "Adventure"])
        assert fields["title"] == "Some Movie"
        assert fields["date"] == "2020"
        assert fields["description"] == "Movie plot."
        assert fields["genre"] == "Action;Adventure"

    def test_map_episode(self):
        fields = _map_tmdb_episode(TMDB_FIND_EPISODE["tv_episode_results"][0])
        assert fields["title"] == "New Episode"
        assert fields["season_number"] == "3"
        assert fields["episode_sort"] == "7"
        assert fields["date"] == "2026"

    def test_map_tv(self):
        fields = _map_tmdb_tv(TMDB_TV_SHOW, ["Drama"])
        assert fields["title"] == "My New Show"
        assert fields["show"] == "My New Show"
        assert fields["album"] == "My New Show"
        assert fields["date"] == "2024"
        assert fields["genre"] == "Drama"

    def test_map_episode_zero_values(self):
        # season/episode 0 should still be emitted (not treated as missing)
        result = {"name": "Pilot", "season_number": 0, "episode_number": 0}
        fields = _map_tmdb_episode(result)
        assert fields["season_number"] == "0"
        assert fields["episode_sort"] == "0"


class TestFetchTmdbMetadata:
    @patch("src.services.imdb_service._tmdb_get")
    def test_episode_with_show_lookup(self, mock_get):
        # First call: /find returns episode; second: /tv/{id} returns show
        mock_get.side_effect = [TMDB_FIND_EPISODE, TMDB_TV_SHOW]
        from src.services.imdb_service import _fetch_tmdb_metadata

        fields = _fetch_tmdb_metadata("tt44466510", "tmdbkey")
        assert fields["title"] == "New Episode"
        assert fields["season_number"] == "3"
        assert fields["show"] == "My New Show"
        assert fields["genre"] == "Drama;Sci-Fi"
        assert mock_get.call_count == 2

    @patch("src.services.imdb_service._tmdb_get")
    def test_movie(self, mock_get):
        # /find returns movie; genre list resolved via a second call
        mock_get.side_effect = [
            TMDB_FIND_MOVIE,
            {"genres": [{"id": 28, "name": "Action"}, {"id": 12, "name": "Adventure"}]},
        ]
        from src.services.imdb_service import _fetch_tmdb_metadata, _TMDB_GENRE_CACHE

        _TMDB_GENRE_CACHE.clear()
        fields = _fetch_tmdb_metadata("tt0111161", "tmdbkey")
        assert fields["title"] == "Some Movie"
        assert "Action" in fields["genre"]

    @patch("src.services.imdb_service._tmdb_get")
    def test_empty_results_raises_not_found(self, mock_get):
        mock_get.return_value = TMDB_FIND_EMPTY
        from src.services.imdb_service import _fetch_tmdb_metadata

        with pytest.raises(MetadataNotFoundError):
            _fetch_tmdb_metadata("tt99999999", "tmdbkey")

    def test_no_key_raises(self):
        from src.services.imdb_service import _fetch_tmdb_metadata

        with pytest.raises(IMDbLookupError, match="No TMDB API key"):
            _fetch_tmdb_metadata("tt0983514", "")


class TestOmdbToTmdbFallback:
    @patch("src.services.imdb_service._fetch_tmdb_metadata")
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_falls_back_when_omdb_not_found(self, mock_omdb, mock_tmdb):
        # OMDb returns a "not found" style error → should fall back to TMDB
        mock_omdb.side_effect = MetadataNotFoundError("Incorrect IMDb ID.")
        mock_tmdb.return_value = {"title": "From TMDB"}

        fields = fetch_metadata("tt44466510", "omdbkey", "tmdbkey")
        assert fields["title"] == "From TMDB"
        mock_tmdb.assert_called_once()

    @patch("src.services.imdb_service._fetch_tmdb_metadata")
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_no_fallback_when_omdb_succeeds(self, mock_omdb, mock_tmdb):
        mock_omdb.return_value = SERIES_RESPONSE
        fields = fetch_metadata("tt0983514", "omdbkey", "tmdbkey")
        assert fields["title"] == "The Challenge"
        mock_tmdb.assert_not_called()

    @patch("src.services.imdb_service._fetch_tmdb_metadata")
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_no_tmdb_key_surfaces_omdb_error(self, mock_omdb, mock_tmdb):
        mock_omdb.side_effect = MetadataNotFoundError("Incorrect IMDb ID.")
        # No TMDB key → the OMDb not-found error is surfaced
        with pytest.raises(IMDbLookupError, match="Incorrect IMDb ID"):
            fetch_metadata("tt44466510", "omdbkey", "")
        mock_tmdb.assert_not_called()

    @patch("src.services.imdb_service._fetch_tmdb_metadata")
    def test_tmdb_only_when_no_omdb_key(self, mock_tmdb):
        mock_tmdb.return_value = {"title": "TMDB Only"}
        fields = fetch_metadata("tt44466510", "", "tmdbkey")
        assert fields["title"] == "TMDB Only"
        mock_tmdb.assert_called_once()

    @patch("src.services.imdb_service._fetch_tmdb_metadata")
    @patch("src.services.imdb_service._fetch_omdb_json")
    def test_both_not_found_raises(self, mock_omdb, mock_tmdb):
        mock_omdb.side_effect = MetadataNotFoundError("Incorrect IMDb ID.")
        mock_tmdb.side_effect = MetadataNotFoundError("TMDB has no record")
        with pytest.raises(IMDbLookupError, match="No metadata found"):
            fetch_metadata("tt44466510", "omdbkey", "tmdbkey")

    def test_no_keys_at_all_raises(self):
        with pytest.raises(IMDbLookupError, match="No metadata API key"):
            fetch_metadata("tt0983514", "", "")


class TestOmdbNotFoundClassification:
    @patch("src.services.imdb_service.urllib.request.urlopen")
    def test_incorrect_id_raises_not_found(self, mock_urlopen):
        from src.services.imdb_service import _fetch_omdb_json

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"Response": "False", "Error": "Incorrect IMDb ID."}
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        with pytest.raises(MetadataNotFoundError):
            _fetch_omdb_json("tt44466510", "fakekey")
