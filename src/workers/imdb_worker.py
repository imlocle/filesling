"""
IMDb metadata worker — fetches OMDb metadata on a background thread.

Keeps the UI responsive while the OMDb HTTP round-trip (and optional second
series lookup for episodes) runs. Emits the mapped field dict on success or an
error message on failure.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from src.services.imdb_service import fetch_metadata_safe


class IMDbWorker(QObject):
    """
    Runs an IMDb/OMDb metadata lookup on a background thread.

    Signals:
        finished: Emitted with the mapped {field_key: value} dict on success.
        error: Emitted with a human-readable message on failure.
    """

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, imdb_id: str, omdb_api_key: str, tmdb_api_key: str = "") -> None:
        super().__init__()
        self._imdb_id = imdb_id
        self._omdb_api_key = omdb_api_key
        self._tmdb_api_key = tmdb_api_key

    def run(self) -> None:
        """Perform the lookup and emit the result."""
        fields, error = fetch_metadata_safe(
            self._imdb_id, self._omdb_api_key, self._tmdb_api_key
        )
        if error is not None:
            self.error.emit(error)
        else:
            self.finished.emit(fields or {})
