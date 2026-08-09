"""Transport-free management commands for Personal Assets weak synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .personal_asset_sync_service import PersonalAssetSyncService
from .personal_asset_sync_state import PersonalAssetSyncStateValidationError


SYNC_PREFIX = "/api/personal-assets/sync"
SYNC_PREFERENCES_PATH = f"{SYNC_PREFIX}/preferences"
SYNC_NOW_PATH = f"{SYNC_PREFIX}/now"
SYNC_CONFLICT_PATH = f"{SYNC_PREFIX}/conflict"


@dataclass(frozen=True, slots=True)
class PersonalAssetSyncHTTPResponse:
    status: int
    payload: dict[str, Any]


class PersonalAssetSyncHTTP:
    def __init__(self, sync: PersonalAssetSyncService):
        self._sync = sync

    def status(self) -> dict[str, object]:
        return self._sync.status()

    @staticmethod
    def handles(path: str) -> bool:
        return path in {SYNC_PREFERENCES_PATH, SYNC_NOW_PATH, SYNC_CONFLICT_PATH}

    @staticmethod
    def _error(status: int, code: str) -> PersonalAssetSyncHTTPResponse:
        return PersonalAssetSyncHTTPResponse(status, {"ok": False, "code": code})

    def post(
        self, path: str, body: Mapping[str, object]
    ) -> PersonalAssetSyncHTTPResponse:
        payload = body if isinstance(body, Mapping) else {}
        try:
            if path == SYNC_PREFERENCES_PATH:
                enabled = payload.get("enabled")
                if not isinstance(enabled, bool):
                    raise PersonalAssetSyncStateValidationError(
                        "enabled must be a boolean"
                    )
                return PersonalAssetSyncHTTPResponse(
                    200, {"ok": True, "sync": self._sync.set_enabled(enabled)}
                )
            if path == SYNC_NOW_PATH:
                if payload:
                    raise PersonalAssetSyncStateValidationError(
                        "sync now body must be empty"
                    )
                return PersonalAssetSyncHTTPResponse(
                    202, {"ok": True, "sync": self._sync.request_sync()}
                )
            if path == SYNC_CONFLICT_PATH:
                if set(payload) != {"resolution"}:
                    raise PersonalAssetSyncStateValidationError(
                        "resolution is required"
                    )
                resolution = payload.get("resolution")
                if resolution not in {"local", "remote"}:
                    raise PersonalAssetSyncStateValidationError(
                        "resolution must be local or remote"
                    )
                return PersonalAssetSyncHTTPResponse(
                    202,
                    {"ok": True, "sync": self._sync.resolve_conflict(resolution)},
                )
            return self._error(404, "personal_asset_route_not_found")
        except PersonalAssetSyncStateValidationError:
            return self._error(400, "personal_asset_sync_invalid")
        except Exception:
            return self._error(503, "personal_asset_sync_unavailable")
