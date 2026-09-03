"""
IMDb metadata service for FileSling.

Fetches video metadata by IMDb ID (e.g. "tt0983514") and maps it to FileSling's
internal metadata field keys so it can populate the Edit Metadata dialog and be
written as a Jellyfin-compatible .nfo file.

Data sources (both accept IMDb IDs directly and require a free API key stored in
settings, never in code):
  - OMDb API (https://www.omdbapi.com/) — primary provider.
  - TMDB API (https://www.themoviedb.org/) — fallback, used when OMDb has no
    record for the ID (common for brand-new episodes). TMDB's community adds new
    titles quickly and its terms permit API use.

We deliberately do NOT scrape imdb.com — that violates IMDb's terms of service,
is fragile, and the data is copyrighted.

The fetch uses the standard-library urllib so no extra HTTP dependency is added
to the app bundle.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional

from src.utils.logging_signal import logger

# OMDb API base endpoint
OMDB_BASE_URL = "https://www.omdbapi.com/"

# TMDB API base endpoint (v3)
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Network timeout for metadata requests (seconds)
OMDB_TIMEOUT = 10
TMDB_TIMEOUT = 10

# Valid IMDb ID pattern: "tt" followed by 7+ digits
_IMDB_ID_PREFIX = "tt"


class IMDbLookupError(Exception):
    """Raised when an IMDb metadata lookup fails."""


class MetadataNotFoundError(IMDbLookupError):
    """
    Raised when a provider is reachable and authenticated but has no record for
    the given IMDb ID. Signals the orchestrator to try the fallback provider.
    """


def _http_get_json(url: str, timeout: int) -> Dict:
    """
    Perform a GET request and return parsed JSON.

    Raises:
        urllib.error.HTTPError / URLError on transport failures (caller handles).
        IMDbLookupError if the body isn't valid JSON.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "FileSling"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise IMDbLookupError("Provider returned an unreadable response")
    if not isinstance(data, dict):
        raise IMDbLookupError("Provider returned an unexpected response format")
    return data


def normalize_imdb_id(raw: str) -> str:
    """
    Normalize a user-entered IMDb ID.

    Accepts:
        - "tt0983514"
        - "0983514" (adds the tt prefix)
        - a full IMDb URL like "https://www.imdb.com/title/tt0983514/"

    Returns:
        A normalized IMDb ID string (e.g. "tt0983514").

    Raises:
        IMDbLookupError: If no valid IMDb ID can be extracted.
    """
    value = raw.strip()
    if not value:
        raise IMDbLookupError("No IMDb ID provided")

    # Extract from a URL if a full imdb.com link was pasted
    if "imdb.com" in value:
        # .../title/tt0983514/... → tt0983514
        parts = [p for p in value.split("/") if p]
        for part in parts:
            if part.startswith(_IMDB_ID_PREFIX) and part[2:].isdigit():
                return part

    # Bare numeric ID → add tt prefix
    if value.isdigit():
        value = _IMDB_ID_PREFIX + value

    if not value.startswith(_IMDB_ID_PREFIX) or not value[2:].isdigit():
        raise IMDbLookupError(
            f"Invalid IMDb ID: '{raw}'. Expected a value like 'tt0983514'."
        )

    return value


def _map_omdb_to_fields(data: Dict[str, str]) -> Dict[str, str]:
    """
    Map an OMDb API JSON response to FileSling's internal metadata field keys.

    FileSling field keys (from src.utils.constants) used here:
        title, show, season_number, episode_sort, director, artist, performer,
        date, genre, description, rating.

    OMDb "N/A" values are treated as empty and omitted.
    """

    def _clean(key: str) -> str:
        val = data.get(key, "")
        if not val or val == "N/A":
            return ""
        return val.strip()

    fields: Dict[str, str] = {}

    title = _clean("Title")
    if title:
        fields["title"] = title

    # OMDb "Year" can be "2009" or "2009–2015" for series; take the first year.
    year = _clean("Year")
    if year:
        fields["date"] = year.split("\u2013")[0].split("-")[0].strip()

    # OMDb genres are comma-separated; FileSling uses semicolons.
    genre = _clean("Genre")
    if genre:
        fields["genre"] = ";".join(g.strip() for g in genre.split(",") if g.strip())

    director = _clean("Director")
    if director:
        fields["director"] = director

    # OMDb "Actors" (comma-separated) → artist + performer (semicolon-separated).
    actors = _clean("Actors")
    if actors:
        people = ";".join(a.strip() for a in actors.split(",") if a.strip())
        fields["artist"] = people
        fields["performer"] = people

    plot = _clean("Plot")
    if plot:
        fields["description"] = plot

    rating = _clean("Rated")
    if rating:
        fields["rating"] = rating

    # Episode-specific fields (present when Type == "episode")
    season = _clean("Season")
    if season:
        fields["season_number"] = season

    episode = _clean("Episode")
    if episode:
        fields["episode_sort"] = episode

    # For an episode, OMDb's "Title" is the episode title. If a series title is
    # available via "seriesID" we don't get its name in the same call, so the
    # caller can do a second lookup for the show name if desired.
    media_type = _clean("Type")
    if media_type == "episode":
        # The episode's own title stays in "title"; the show name is filled
        # separately by fetch_show_name() when the caller wants it.
        pass

    return fields


def _fetch_omdb_json(imdb_id: str, api_key: str) -> Dict:
    """
    Perform the raw OMDb HTTP request and return the parsed JSON dict.

    Raises:
        MetadataNotFoundError: If OMDb has no record for this ID (triggers fallback).
        IMDbLookupError: On network errors, invalid key, or other OMDb errors.
    """
    if not api_key or not api_key.strip():
        raise IMDbLookupError(
            "No OMDb API key configured. Add one in Settings to fetch metadata."
        )

    params = urllib.parse.urlencode({"i": imdb_id, "apikey": api_key.strip()})
    url = f"{OMDB_BASE_URL}?{params}"

    try:
        data = _http_get_json(url, OMDB_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise IMDbLookupError(
                "OMDb rejected the API key (401). Check that the key is activated."
            )
        raise IMDbLookupError(f"OMDb request failed (HTTP {e.code})")
    except urllib.error.URLError as e:
        raise IMDbLookupError(f"Could not reach OMDb: {e.reason}")

    # OMDb signals failures with {"Response": "False", "Error": "..."}
    if data.get("Response") == "False":
        error = data.get("Error", "OMDb lookup failed")
        # Distinguish "not found" (fall back) from auth/other errors (stop).
        lowered = error.lower()
        if (
            "incorrect imdb" in lowered
            or "not found" in lowered
            or "error getting" in lowered
        ):
            raise MetadataNotFoundError(error)
        raise IMDbLookupError(error)

    return data


def fetch_show_name(series_imdb_id: str, api_key: str) -> str:
    """
    Look up just the series/show name for a given series IMDb ID.

    Returns an empty string if it can't be determined (never raises).
    """
    try:
        normalized = normalize_imdb_id(series_imdb_id)
        data = _fetch_omdb_json(normalized, api_key)
        name = data.get("Title", "")
        return "" if name == "N/A" else name.strip()
    except IMDbLookupError:
        return ""


def _fetch_omdb_metadata(imdb_id: str, api_key: str) -> Dict[str, str]:
    """
    Fetch and map metadata from OMDb for a normalized IMDb ID.

    Raises:
        MetadataNotFoundError: If OMDb has no record (triggers fallback).
        IMDbLookupError: On other errors.
    """
    data = _fetch_omdb_json(imdb_id, api_key)
    fields = _map_omdb_to_fields(data)

    # For an episode, resolve the show name from the parent series.
    if data.get("Type") == "episode":
        series_id = data.get("seriesID", "")
        if series_id and series_id != "N/A":
            show_name = fetch_show_name(series_id, api_key)
            if show_name:
                fields["show"] = show_name
                fields.setdefault("album", show_name)

    return fields


# =============================================================================
# TMDB provider (fallback)
#
# TMDB's terms permit API use of their data. The /find endpoint resolves an
# IMDb ID into TMDB movie / TV / episode objects. TMDB's community adds new
# episodes quickly, so it often has records OMDb doesn't yet.
# =============================================================================


def _tmdb_get(path: str, api_key: str, extra_params: Optional[Dict] = None) -> Dict:
    """
    Perform a TMDB v3 GET request.

    Raises:
        IMDbLookupError: On network errors or an invalid key (401).
    """
    params = {"api_key": api_key.strip()}
    if extra_params:
        params.update(extra_params)
    url = f"{TMDB_BASE_URL}{path}?{urllib.parse.urlencode(params)}"

    try:
        return _http_get_json(url, TMDB_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise IMDbLookupError("TMDB rejected the API key (401).")
        if e.code == 404:
            raise MetadataNotFoundError("TMDB has no record for this ID")
        raise IMDbLookupError(f"TMDB request failed (HTTP {e.code})")
    except urllib.error.URLError as e:
        raise IMDbLookupError(f"Could not reach TMDB: {e.reason}")


def _map_tmdb_movie(result: Dict, genre_names: list) -> Dict[str, str]:
    """Map a TMDB movie_result to FileSling field keys."""
    fields: Dict[str, str] = {}
    if result.get("title"):
        fields["title"] = result["title"]
    release = result.get("release_date", "")
    if release:
        fields["date"] = release.split("-")[0]
    if result.get("overview"):
        fields["description"] = result["overview"]
    if genre_names:
        fields["genre"] = ";".join(genre_names)
    return fields


def _map_tmdb_tv(result: Dict, genre_names: list) -> Dict[str, str]:
    """Map a TMDB tv_result (a series) to FileSling field keys."""
    fields: Dict[str, str] = {}
    name = result.get("name", "")
    if name:
        fields["title"] = name
        fields["show"] = name
        fields.setdefault("album", name)
    air = result.get("first_air_date", "")
    if air:
        fields["date"] = air.split("-")[0]
    if result.get("overview"):
        fields["description"] = result["overview"]
    if genre_names:
        fields["genre"] = ";".join(genre_names)
    return fields


def _map_tmdb_episode(result: Dict) -> Dict[str, str]:
    """Map a TMDB tv_episode_result to FileSling field keys."""
    fields: Dict[str, str] = {}
    if result.get("name"):
        fields["title"] = result["name"]
    if result.get("overview"):
        fields["description"] = result["overview"]
    air = result.get("air_date", "")
    if air:
        fields["date"] = air.split("-")[0]
    season = result.get("season_number")
    if season is not None:
        fields["season_number"] = str(season)
    episode = result.get("episode_number")
    if episode is not None:
        fields["episode_sort"] = str(episode)
    return fields


def _fetch_tmdb_metadata(imdb_id: str, api_key: str) -> Dict[str, str]:
    """
    Fetch and map metadata from TMDB for a normalized IMDb ID.

    Uses /find to resolve the IMDb ID, then for episodes does one follow-up
    /tv/{show_id} call to fill the show name and genres.

    Raises:
        MetadataNotFoundError: If TMDB has no matching record (all result arrays empty).
        IMDbLookupError: On network errors or invalid key.
    """
    if not api_key or not api_key.strip():
        raise IMDbLookupError("No TMDB API key configured.")

    found = _tmdb_get(f"/find/{imdb_id}", api_key, {"external_source": "imdb_id"})

    movie_results = found.get("movie_results") or []
    tv_results = found.get("tv_results") or []
    episode_results = found.get("tv_episode_results") or []

    if episode_results:
        result = episode_results[0]
        fields = _map_tmdb_episode(result)
        # Resolve the show name + genres from the parent series (best-effort).
        show_id = result.get("show_id")
        if show_id:
            try:
                show = _tmdb_get(f"/tv/{show_id}", api_key)
                show_name = show.get("name", "")
                if show_name:
                    fields["show"] = show_name
                    fields.setdefault("album", show_name)
                genres = [g.get("name", "") for g in show.get("genres", [])]
                genres = [g for g in genres if g]
                if genres:
                    fields.setdefault("genre", ";".join(genres))
            except IMDbLookupError:
                pass  # Episode fields still usable without the show lookup
        return fields

    if movie_results:
        result = movie_results[0]
        genres = _tmdb_genre_names(result.get("genre_ids", []), "movie", api_key)
        return _map_tmdb_movie(result, genres)

    if tv_results:
        result = tv_results[0]
        genres = _tmdb_genre_names(result.get("genre_ids", []), "tv", api_key)
        return _map_tmdb_tv(result, genres)

    raise MetadataNotFoundError("TMDB has no record for this ID")


# Cache TMDB genre id→name maps per media type so we don't refetch every call.
_TMDB_GENRE_CACHE: Dict[str, Dict[int, str]] = {}


def _tmdb_genre_names(genre_ids: list, media_type: str, api_key: str) -> list:
    """Resolve TMDB numeric genre ids to names (cached). Best-effort — [] on error."""
    if not genre_ids:
        return []
    cache = _TMDB_GENRE_CACHE.get(media_type)
    if cache is None:
        try:
            data = _tmdb_get(f"/genre/{media_type}/list", api_key)
            cache = {g["id"]: g["name"] for g in data.get("genres", [])}
            _TMDB_GENRE_CACHE[media_type] = cache
        except (IMDbLookupError, KeyError, TypeError):
            return []
    return [cache[g] for g in genre_ids if g in cache]


# =============================================================================
# Orchestration — OMDb primary, TMDB fallback
# =============================================================================


def fetch_metadata(
    imdb_id: str, omdb_api_key: str, tmdb_api_key: str = ""
) -> Dict[str, str]:
    """
    Fetch metadata for an IMDb ID, mapped to FileSling internal field keys.

    Tries OMDb first. If OMDb has no record for the ID (common for brand-new
    episodes) and a TMDB key is configured, falls back to TMDB automatically.

    Args:
        imdb_id: IMDb ID or URL (e.g. "tt0983514").
        omdb_api_key: OMDb API key (primary provider).
        tmdb_api_key: TMDB API key (fallback provider). Optional.

    Returns:
        Dict of {field_key: value} ready to populate the metadata dialog.

    Raises:
        IMDbLookupError: If both providers fail (or the only configured one does).
    """
    normalized = normalize_imdb_id(imdb_id)
    logger.search(f"IMDb: Looking up {normalized}")

    have_omdb = bool(omdb_api_key and omdb_api_key.strip())
    have_tmdb = bool(tmdb_api_key and tmdb_api_key.strip())

    if not have_omdb and not have_tmdb:
        raise IMDbLookupError(
            "No metadata API key configured. Add an OMDb or TMDB key in Settings."
        )

    omdb_error: Optional[Exception] = None

    # Primary: OMDb
    if have_omdb:
        try:
            fields = _fetch_omdb_metadata(normalized, omdb_api_key)
            logger.success(f"IMDb: Found metadata for {normalized} (OMDb)")
            return fields
        except MetadataNotFoundError as e:
            omdb_error = e
            logger.info(f"IMDb: OMDb has no record for {normalized}")
        except IMDbLookupError as e:
            omdb_error = e
            logger.warn(f"IMDb: OMDb lookup failed: {e}")

    # Fallback: TMDB
    if have_tmdb:
        try:
            fields = _fetch_tmdb_metadata(normalized, tmdb_api_key)
            logger.success(f"IMDb: Found metadata for {normalized} (TMDB fallback)")
            return fields
        except MetadataNotFoundError:
            raise IMDbLookupError(
                f"No metadata found for {normalized} on OMDb or TMDB."
            )
        except IMDbLookupError as e:
            # If OMDb also errored, surface both for clarity.
            if omdb_error is not None:
                raise IMDbLookupError(
                    f"OMDb: {omdb_error}. TMDB fallback also failed: {e}"
                )
            raise

    # Only OMDb was configured and it failed.
    assert omdb_error is not None
    raise IMDbLookupError(str(omdb_error))


def fetch_metadata_safe(
    imdb_id: str, omdb_api_key: str, tmdb_api_key: str = ""
) -> tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Non-raising variant of fetch_metadata for use in worker threads.

    Returns:
        (fields, None) on success, or (None, error_message) on failure.
    """
    try:
        return fetch_metadata(imdb_id, omdb_api_key, tmdb_api_key), None
    except IMDbLookupError as e:
        return None, str(e)
    except Exception as e:  # pragma: no cover - defensive
        return None, f"Unexpected error: {e}"
