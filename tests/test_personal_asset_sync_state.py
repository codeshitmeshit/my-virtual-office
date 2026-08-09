import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_sync_state import (  # noqa: E402
    PersonalAssetSyncStateStore,
    PersonalAssetSyncStateValidationError,
)


NOW = datetime(2026, 8, 8, 10, 24, tzinfo=timezone.utc)


def test_default_state_is_enabled_and_origin_is_stable(tmp_path):
    store = PersonalAssetSyncStateStore(tmp_path / "sync.json", now=lambda: NOW)

    first = store.snapshot()
    second = store.snapshot()

    assert first == second
    assert first["enabled"] is True
    assert first["status"] == "idle"
    assert first["originId"].startswith("vo-")
    assert (tmp_path / "sync.json").exists()
    assert os.stat(tmp_path / "sync.json").st_mode & 0o777 == 0o600


def test_pending_syncing_and_synced_transitions_keep_only_sync_metadata(tmp_path):
    store = PersonalAssetSyncStateStore(tmp_path / "sync.json", now=lambda: NOW)

    pending = store.mark_pending(7)
    syncing = store.mark_syncing("upload")
    synced = store.mark_synced(
        revision=7,
        fingerprint="a" * 64,
        etag="etag-7",
    )

    assert pending["status"] == "pending" and pending["pendingRevision"] == 7
    assert syncing["status"] == "syncing" and syncing["operation"] == "upload"
    assert synced["status"] == "synced"
    assert synced["pendingRevision"] == 0
    assert synced["syncedRevision"] == 7
    assert synced["syncedFingerprint"] == "a" * 64
    assert synced["baseEtag"] == "etag-7"
    assert synced["lastSyncedAt"] == NOW.isoformat()
    assert "payload" not in synced and "accessKeySecret" not in synced


def test_failure_and_conflict_persist_stable_codes_without_raw_errors(tmp_path):
    store = PersonalAssetSyncStateStore(tmp_path / "sync.json", now=lambda: NOW)
    store.mark_pending(3)

    failed = store.mark_failed("oss_connectivity_failed", retry_at="2026-08-08T10:25:00+00:00")
    conflict = store.mark_conflict(remote_etag="etag-remote")

    assert failed["status"] == "failed"
    assert failed["lastErrorCode"] == "oss_connectivity_failed"
    assert failed["retryAt"] == "2026-08-08T10:25:00+00:00"
    assert failed["attempt"] == 1
    assert conflict["status"] == "conflict"
    assert conflict["remoteEtag"] == "etag-remote"
    persisted = (tmp_path / "sync.json").read_text(encoding="utf-8")
    assert "provider-secret-sentinel" not in persisted
    assert "lastErrorCode" in persisted


def test_enabled_and_conflict_resolution_validation(tmp_path):
    store = PersonalAssetSyncStateStore(tmp_path / "sync.json", now=lambda: NOW)

    assert store.set_enabled(False)["enabled"] is False
    assert store.set_resolution("local")["resolution"] == "local"
    assert store.set_resolution("remote")["resolution"] == "remote"

    with pytest.raises(PersonalAssetSyncStateValidationError):
        store.set_enabled("yes")
    with pytest.raises(PersonalAssetSyncStateValidationError):
        store.set_resolution("latest")


def test_finishing_older_upload_preserves_newer_pending_revision(tmp_path):
    store = PersonalAssetSyncStateStore(tmp_path / "sync.json", now=lambda: NOW)
    store.mark_pending(7)
    store.mark_syncing("upload")
    store.mark_pending(8)

    state = store.mark_synced(
        revision=7,
        fingerprint="a" * 64,
        etag="etag-7",
    )

    assert state["status"] == "pending"
    assert state["pendingRevision"] == 8
    assert state["syncedRevision"] == 7
    assert state["baseEtag"] == "etag-7"


def test_new_profile_mutation_invalidates_an_unconsumed_conflict_choice(tmp_path):
    store = PersonalAssetSyncStateStore(tmp_path / "sync.json", now=lambda: NOW)
    store.mark_conflict(remote_etag="etag-remote")
    store.set_resolution("remote")

    pending = store.mark_pending(9)

    assert pending["status"] == "pending"
    assert pending["resolution"] == ""
