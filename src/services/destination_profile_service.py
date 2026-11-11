"""Business rules for saved upload destinations."""

from __future__ import annotations

import uuid
from typing import Optional

from src.config.settings import Settings
from src.models.destination_profile import (
    DUPLICATE_POLICIES,
    DestinationProfile,
)


class DestinationProfileService:
    """Validate and manage profiles that point to configured connections."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_profiles(self) -> list[DestinationProfile]:
        """Return saved profiles in their configured order."""
        return [
            DestinationProfile.from_dict(data)
            for data in self._settings.get_destination_profiles()
        ]

    def get_profile(self, profile_id: str) -> Optional[DestinationProfile]:
        """Look up a saved profile by ID."""
        for profile in self.list_profiles():
            if profile.profile_id == profile_id:
                return profile
        return None

    def save_profile(
        self,
        *,
        profile_id: str,
        name: str,
        server_id: str,
        remote_path: str,
        duplicate_policy: str,
        refresh_jellyfin: Optional[bool],
    ) -> DestinationProfile:
        """Validate and persist a profile, generating an ID for new entries."""
        clean_name = name.strip()
        clean_path = remote_path.strip()
        if not clean_name:
            raise ValueError("Enter a name for this destination.")
        if server_id not in self._settings.get_servers():
            raise ValueError("Choose a configured server or device.")
        if not clean_path.startswith("/"):
            raise ValueError("The destination folder must be an absolute path.")
        if duplicate_policy not in DUPLICATE_POLICIES:
            raise ValueError("Choose a valid duplicate handling option.")

        profile = DestinationProfile(
            profile_id=profile_id.strip() or uuid.uuid4().hex,
            name=clean_name,
            server_id=server_id,
            remote_path=clean_path,
            duplicate_policy=duplicate_policy,
            refresh_jellyfin=refresh_jellyfin,
        )
        self._settings.save_destination_profile(profile.to_dict())
        return profile

    def delete_profile(self, profile_id: str) -> None:
        """Delete a saved profile."""
        self._settings.delete_destination_profile(profile_id)

    def activate_profile(self, profile_id: str) -> Optional[DestinationProfile]:
        """Persist the selected profile and return it when it still exists."""
        profile = self.get_profile(profile_id) if profile_id else None
        if profile_id and profile is None:
            raise ValueError("This destination profile no longer exists.")
        self._settings.set_active_destination_profile(profile_id)
        return profile

    def get_active_profile(self) -> Optional[DestinationProfile]:
        """Return the active profile when it is still saved."""
        return self.get_profile(self._settings.config.active_destination_profile_id)

    def get_duplicate_policy(self, server_id: str) -> str:
        """Return the active profile's duplicate policy for this connection."""
        profile = self.get_active_profile()
        if profile and profile.server_id == server_id:
            return profile.duplicate_policy
        return "ask"
