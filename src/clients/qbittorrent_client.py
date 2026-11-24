"""Minimal qBittorrent Web API client carried over the active SSH session."""

from __future__ import annotations

import http.client
import json
import os
import secrets
from typing import Optional, Sequence, Tuple
from urllib.parse import urlencode

from paramiko import Transport

from src.models.torrent import TorrentInfo

REQUEST_TIMEOUT_SECONDS = 8


class _SSHHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that opens its socket through an SSH direct channel."""

    def __init__(self, transport: Transport, port: int) -> None:
        super().__init__("127.0.0.1", port, timeout=REQUEST_TIMEOUT_SECONDS)
        self._transport = transport

    def connect(self) -> None:
        if not self._transport.is_active():
            raise ConnectionError("The SSH connection is no longer active")
        self.sock = self._transport.open_channel(
            "direct-tcpip",
            ("127.0.0.1", self.port),
            ("127.0.0.1", 0),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if self.sock is None:
            raise ConnectionError("Could not open the qBittorrent SSH tunnel")
        self.sock.settimeout(REQUEST_TIMEOUT_SECONDS)


class QBittorrentClient:
    """Call qBittorrent's v2 Web API through an authenticated SSH transport."""

    def __init__(
        self,
        transport: Transport,
        port: int,
        username: str,
        password: str,
    ) -> None:
        if not 1 <= int(port) <= 65535:
            raise ValueError("qBittorrent Web UI port must be between 1 and 65535")
        if not username.strip() or not password:
            raise ValueError("Enter the qBittorrent Web UI username and password")
        self._transport = transport
        self._port = int(port)
        self._username = username.strip()
        self._password = password
        self._sid: Optional[str] = None

    def login(self) -> None:
        """Authenticate and retain the returned SID for this client instance."""
        body = urlencode(
            {"username": self._username, "password": self._password}
        ).encode("utf-8")
        status, headers, response_body = self._request(
            "POST",
            "/api/v2/auth/login",
            body=body,
            content_type="application/x-www-form-urlencoded",
        )
        if status != 200 or response_body.decode("utf-8", "replace").strip() != "Ok.":
            raise PermissionError(
                "qBittorrent login failed. Check the Web UI username and password."
            )

        cookie = next(
            (value for key, value in headers if key.lower() == "set-cookie"), ""
        )
        sid = next(
            (
                part.split("=", 1)[1]
                for part in cookie.split(";")
                if part.strip().startswith("SID=")
            ),
            "",
        )
        if not sid:
            raise PermissionError("qBittorrent did not return a login session")
        self._sid = sid

    def list_torrents(self) -> list[TorrentInfo]:
        self._ensure_login()
        _, _, body = self._request(
            "GET", "/api/v2/torrents/info", authenticated=True
        )
        try:
            records = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "qBittorrent returned an invalid torrent list"
            ) from error
        if not isinstance(records, list):
            raise RuntimeError("qBittorrent returned an unexpected torrent list")
        return [
            TorrentInfo.from_api(record)
            for record in records
            if isinstance(record, dict) and record.get("hash")
        ]

    def add_magnet(self, magnet_link: str, save_path: str = "") -> None:
        self._ensure_login()
        fields = [("urls", magnet_link)]
        if save_path:
            fields.extend(
                [
                    ("savepath", save_path),
                    ("autoTMM", "false"),
                ]
            )
        body, content_type = self._multipart_body(fields)
        self._post_torrent_add(body, content_type)

    def add_torrent_file(
        self, filename: str, contents: bytes, save_path: str = ""
    ) -> None:
        self._ensure_login()
        fields: list[Tuple[str, str]] = []
        if save_path:
            fields.extend(
                [
                    ("savepath", save_path),
                    ("autoTMM", "false"),
                ]
            )
        body, content_type = self._multipart_body(
            fields,
            file=("torrents", filename, contents),
        )
        self._post_torrent_add(body, content_type)

    def pause(self, torrent_hash: str) -> None:
        self._change_state("stop", torrent_hash)

    def resume(self, torrent_hash: str) -> None:
        self._change_state("start", torrent_hash)

    def remove(self, torrent_hash: str) -> None:
        self._remove(torrent_hash, delete_files=False)

    def remove_with_data(self, torrent_hash: str) -> None:
        self._remove(torrent_hash, delete_files=True)

    def set_location(self, torrent_hash: str, location: str) -> None:
        self._ensure_login()
        body = urlencode(
            {
                "hashes": self._validate_hash(torrent_hash),
                "location": location,
            }
        )
        self._post_form("/api/v2/torrents/setLocation", body)

    def _remove(self, torrent_hash: str, delete_files: bool) -> None:
        self._ensure_login()
        body = urlencode(
            {
                "hashes": self._validate_hash(torrent_hash),
                "deleteFiles": str(delete_files).lower(),
            }
        )
        self._post_form("/api/v2/torrents/delete", body)

    def _change_state(self, endpoint: str, torrent_hash: str) -> None:
        self._ensure_login()
        body = urlencode({"hashes": self._validate_hash(torrent_hash)})
        self._post_form(f"/api/v2/torrents/{endpoint}", body)

    def _post_torrent_add(self, body: bytes, content_type: str) -> None:
        _, _, response_body = self._request(
            "POST",
            "/api/v2/torrents/add",
            body=body,
            content_type=content_type,
            authenticated=True,
        )
        result = response_body.decode("utf-8", "replace").strip()
        if result and result.lower() not in ("ok.", "ok"):
            raise RuntimeError(f"qBittorrent could not add the torrent: {result}")

    def _post_form(self, endpoint: str, body: str) -> None:
        self._request(
            "POST",
            endpoint,
            body=body.encode("utf-8"),
            content_type="application/x-www-form-urlencoded",
            authenticated=True,
        )

    def _ensure_login(self) -> None:
        if self._sid is None:
            self.login()

    def _request(
        self,
        method: str,
        endpoint: str,
        body: Optional[bytes] = None,
        content_type: str = "",
        authenticated: bool = False,
    ) -> Tuple[int, Sequence[Tuple[str, str]], bytes]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Connection": "close",
            "Host": f"127.0.0.1:{self._port}",
            "Origin": f"http://127.0.0.1:{self._port}",
            "Referer": f"http://127.0.0.1:{self._port}/",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if authenticated:
            if not self._sid:
                raise PermissionError("Log in to qBittorrent before making requests")
            headers["Cookie"] = f"SID={self._sid}"

        connection = _SSHHTTPConnection(self._transport, self._port)
        try:
            connection.request(method, endpoint, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            response_headers = response.getheaders()
            if response.status < 200 or response.status >= 300:
                if (
                    response.status == 403
                    and endpoint == "/api/v2/torrents/setLocation"
                ):
                    raise PermissionError(
                        "qBittorrent cannot write to the selected server folder. "
                        "Check that it exists and is writable by the qBittorrent user."
                    )
                if (
                    response.status == 409
                    and endpoint == "/api/v2/torrents/setLocation"
                ):
                    raise RuntimeError(
                        "qBittorrent could not create or use the selected server folder."
                    )
                if response.status == 401:
                    raise PermissionError(
                        "qBittorrent rejected the request. Check Web UI access "
                        "and credentials."
                    )
                if response.status == 403:
                    raise PermissionError(
                        "qBittorrent denied this action. Check the Web UI user's "
                        "permissions."
                    )
                raise RuntimeError(
                    f"qBittorrent returned HTTP {response.status} for {endpoint}"
                )
            return response.status, response_headers, response_body
        finally:
            connection.close()

    @staticmethod
    def _validate_hash(torrent_hash: str) -> str:
        value = torrent_hash.strip()
        if not value or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError("The selected torrent has an invalid hash")
        return value

    @staticmethod
    def _multipart_body(
        fields: Sequence[Tuple[str, str]],
        file: Optional[Tuple[str, str, bytes]] = None,
    ) -> Tuple[bytes, str]:
        boundary = f"filesling-{secrets.token_hex(16)}"
        chunks = []
        for name, value in fields:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                        "ascii"
                    ),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        if file is not None:
            field_name, filename, contents = file
            safe_filename = os.path.basename(filename).replace('"', "_")
            safe_filename = safe_filename.replace("\r", "_").replace("\n", "_")
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    (
                        f'Content-Disposition: form-data; name="{field_name}"; '
                        f'filename="{safe_filename}"\r\n'
                    ).encode("utf-8"),
                    b"Content-Type: application/x-bittorrent\r\n\r\n",
                    contents,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
