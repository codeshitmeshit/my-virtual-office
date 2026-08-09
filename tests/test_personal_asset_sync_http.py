import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_sync_http import (  # noqa: E402
    SYNC_CONFLICT_PATH,
    SYNC_NOW_PATH,
    SYNC_PREFERENCES_PATH,
    PersonalAssetSyncHTTP,
)


class SyncStub:
    def __init__(self):
        self.value = {"enabled": True, "status": "synced"}
        self.calls = []

    def status(self):
        return dict(self.value)

    def set_enabled(self, enabled):
        self.calls.append(("enabled", enabled))
        return {**self.value, "enabled": enabled}

    def request_sync(self):
        self.calls.append(("sync",))
        return {**self.value, "status": "pending"}

    def resolve_conflict(self, resolution):
        self.calls.append(("resolve", resolution))
        return {**self.value, "status": "pending"}


def test_sync_commands_are_strict_and_queue_without_exposing_oss_settings():
    stub = SyncStub()
    http = PersonalAssetSyncHTTP(stub)

    enabled = http.post(SYNC_PREFERENCES_PATH, {"enabled": False})
    queued = http.post(SYNC_NOW_PATH, {})
    resolved = http.post(SYNC_CONFLICT_PATH, {"resolution": "remote"})

    assert enabled.status == 200 and enabled.payload["sync"]["enabled"] is False
    assert queued.status == 202 and queued.payload["sync"]["status"] == "pending"
    assert resolved.status == 202
    assert stub.calls == [("enabled", False), ("sync",), ("resolve", "remote")]
    assert "bucket" not in str(enabled.payload).lower()
    assert "endpoint" not in str(enabled.payload).lower()

    invalid_enabled = http.post(SYNC_PREFERENCES_PATH, {"enabled": "yes"})
    invalid_resolution = http.post(SYNC_CONFLICT_PATH, {"resolution": "latest"})
    unknown = http.post("/api/personal-assets/sync/unknown", {})
    assert invalid_enabled.status == 400
    assert invalid_resolution.status == 400
    assert unknown.status == 404
