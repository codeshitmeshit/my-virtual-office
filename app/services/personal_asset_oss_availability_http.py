"""Transport-free HTTP projection for Personal Assets OSS availability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .personal_asset_oss_availability import PersonalAssetOssAvailability


OSS_AVAILABILITY_PATH = "/api/personal-assets/sync/availability"


@dataclass(frozen=True, slots=True)
class PersonalAssetOssAvailabilityHTTPResponse:
    status: int
    payload: dict[str, Any]


class PersonalAssetOssAvailabilityHTTP:
    def __init__(self, availability: PersonalAssetOssAvailability):
        self._availability = availability

    @staticmethod
    def handles_get(path: str) -> bool:
        return path == OSS_AVAILABILITY_PATH

    def get(self, path: str) -> PersonalAssetOssAvailabilityHTTPResponse:
        if not self.handles_get(path):
            return PersonalAssetOssAvailabilityHTTPResponse(
                404, {"ok": False, "code": "personal_asset_route_not_found"}
            )
        return PersonalAssetOssAvailabilityHTTPResponse(
            200, {"ok": True, "availability": self._availability.check()}
        )
