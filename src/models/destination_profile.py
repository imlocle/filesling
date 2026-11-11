"""Typed model for reusable upload destinations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


DUPLICATE_POLICIES = ("ask", "skip", "overwrite")


@dataclass(frozen=True)
class DestinationProfile:
    """A saved destination that references an existing connection."""

    profile_id: str
    name: str
    server_id: str
    remote_path: str
    duplicate_policy: str = "ask"
    refresh_jellyfin: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: dict) -> "DestinationProfile":
        """Build a profile from the settings JSON representation."""
        policy = str(data.get("duplicate_policy", "ask"))
        if policy not in DUPLICATE_POLICIES:
            policy = "ask"
        refresh_jellyfin = data.get("refresh_jellyfin")
        if not isinstance(refresh_jellyfin, bool):
            refresh_jellyfin = None
        return cls(
            profile_id=str(data.get("profile_id", "")),
            name=str(data.get("name", "")),
            server_id=str(data.get("server_id", "")),
            remote_path=str(data.get("remote_path", "")),
            duplicate_policy=policy,
            refresh_jellyfin=refresh_jellyfin,
        )

    def to_dict(self) -> dict[str, Union[str, bool]]:
        """Serialize the profile without connection credentials."""
        data: dict[str, Union[str, bool]] = {
            "profile_id": self.profile_id,
            "name": self.name,
            "server_id": self.server_id,
            "remote_path": self.remote_path,
            "duplicate_policy": self.duplicate_policy,
        }
        if self.refresh_jellyfin is not None:
            data["refresh_jellyfin"] = self.refresh_jellyfin
        return data
