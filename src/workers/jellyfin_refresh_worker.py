"""Background worker that asks Jellyfin to refresh its media libraries."""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal


class JellyfinRefreshWorker(QObject):
    """Send a library refresh request without blocking the Qt main thread."""

    done = Signal()
    error = Signal(str)
    requested = Signal()

    def __init__(self, server_url: str, api_key: str) -> None:
        super().__init__()
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key

    def run(self) -> None:
        try:
            url = urlsplit(self._server_url)
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("Enter an HTTP or HTTPS Jellyfin server URL")

            request = Request(
                f"{self._server_url}/Library/Refresh",
                data=b"",
                headers={
                    "X-Emby-Token": self._api_key,
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                if not 200 <= response.status < 300:
                    self.error.emit(f"Jellyfin returned HTTP {response.status}")
                else:
                    self.requested.emit()
        except HTTPError as e:
            self.error.emit(f"Jellyfin returned HTTP {e.code}")
        except URLError as e:
            self.error.emit(f"Could not reach Jellyfin: {e.reason}")
        except Exception as e:
            self.error.emit(f"Jellyfin refresh failed: {e}")
        finally:
            self.done.emit()
