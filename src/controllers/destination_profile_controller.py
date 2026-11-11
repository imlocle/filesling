"""Controller facade for destination profile operations."""

from __future__ import annotations

from typing import Optional

from src.models.destination_profile import DestinationProfile
from src.services.destination_profile_service import DestinationProfileService


class DestinationProfileController:
    """Expose profile workflows to the main window and profile dialog."""

    def __init__(self, service: DestinationProfileService) -> None:
        self._service = service

    def list_profiles(self) -> list[DestinationProfile]:
        return self._service.list_profiles()

    def get_profile(self, profile_id: str) -> Optional[DestinationProfile]:
        return self._service.get_profile(profile_id)

    def get_active_profile(self) -> Optional[DestinationProfile]:
        return self._service.get_active_profile()

    def get_duplicate_policy(self, server_id: str) -> str:
        return self._service.get_duplicate_policy(server_id)

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
        return self._service.save_profile(
            profile_id=profile_id,
            name=name,
            server_id=server_id,
            remote_path=remote_path,
            duplicate_policy=duplicate_policy,
            refresh_jellyfin=refresh_jellyfin,
        )

    def delete_profile(self, profile_id: str) -> None:
        self._service.delete_profile(profile_id)

    def activate_profile(self, profile_id: str) -> Optional[DestinationProfile]:
        return self._service.activate_profile(profile_id)
