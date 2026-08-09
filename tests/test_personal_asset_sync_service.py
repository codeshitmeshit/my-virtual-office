import io
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.oss_runtime import ActiveOssContext  # noqa: E402
from services.oss_settings import OssConnectionConfig  # noqa: E402
from services.oss_storage import (  # noqa: E402
    OssStorageError,
    OssStorageService,
    ProviderObjectMetadata,
    ProviderObjectPage,
)
from services.personal_asset_store import PersonalAssetStore  # noqa: E402
from services.personal_asset_sync_service import (  # noqa: E402
    OBJECT_ID,
    OSS_INTEGRATION_ID,
    PersonalAssetSyncService,
)
from services.personal_asset_sync_state import PersonalAssetSyncStateStore  # noqa: E402


NOW = datetime(2026, 8, 8, 10, 24, tzinfo=timezone.utc)


def entry(label, value):
    return {
        "category": "custom",
        "label": label,
        "value": value,
        "sensitivity": "standard",
    }


class MemoryProvider:
    def __init__(self):
        self.objects = {}
        self.failure = None

    def _fail(self):
        if self.failure:
            failure = self.failure
            self.failure = None
            raise failure

    def upload_from(self, key, reader, *, content_type=None):
        self._fail()
        content = reader.read()
        previous = self.objects.get(key)
        generation = int(previous[2] if previous else 0) + 1
        metadata = ProviderObjectMetadata(
            key=key,
            size=len(content),
            content_type=content_type,
            etag=f"etag-{generation}",
            last_modified=NOW,
        )
        self.objects[key] = (content, metadata, generation)
        return metadata

    def download_to(self, key, sink, *, chunk_size):
        self._fail()
        if key not in self.objects:
            raise OssStorageError("not found", code="oss_not_found")
        content, metadata, _generation = self.objects[key]
        for offset in range(0, len(content), chunk_size):
            sink.write(content[offset : offset + chunk_size])
        return metadata

    def head(self, key):
        self._fail()
        if key not in self.objects:
            raise OssStorageError("not found", code="oss_not_found")
        return self.objects[key][1]

    def exists(self, key):
        self._fail()
        return key in self.objects

    def delete(self, key):
        self.objects.pop(key, None)

    def list(self, prefix, *, continuation_token=None, limit=100):
        items = tuple(
            replace(value[1], content_type=None)
            for key, value in sorted(self.objects.items())
            if key.startswith(prefix)
        )
        return ProviderObjectPage(items=items[:limit], next_token=None)


def storage(provider):
    config = OssConnectionConfig.create(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="vo-materials",
        access_key_id="LTAI-test",
        access_key_secret="provider-secret-sentinel",
    )
    context = ActiveOssContext(config, provider, 1)
    return OssStorageService(lambda: context, transfer_buffer_size=1024)


def sync_service(tmp_path, name, shared_storage):
    profile = PersonalAssetStore(tmp_path / f"{name}-assets.json", now=lambda: NOW)
    state = PersonalAssetSyncStateStore(tmp_path / f"{name}-sync.json", now=lambda: NOW)
    return profile, PersonalAssetSyncService(
        profile,
        state,
        shared_storage,
        now=lambda: NOW,
    )


def mutate(profile, sync, label, value):
    result = profile.create_entry(
        entry(label, value), expected_revision=profile.snapshot()["revision"]
    )
    sync.on_profile_mutation(result["snapshot"])
    return result


def test_upload_uses_scoped_json_snapshot_and_oss_failure_never_changes_local(tmp_path):
    provider = MemoryProvider()
    shared = storage(provider)
    profile, sync = sync_service(tmp_path, "primary", shared)
    created = mutate(profile, sync, "职业", "产品")

    provider.failure = RuntimeError("provider-secret-sentinel and private-value")
    failed = sync.run_once()

    assert failed["status"] == "failed"
    assert failed["lastErrorCode"] == "oss_provider_operation_failed"
    assert profile.snapshot() == created["snapshot"]
    assert "provider-secret-sentinel" not in json.dumps(failed)

    deferred = sync.run_once()
    assert deferred["status"] == "failed"
    assert provider.objects == {}

    sync.request_sync()
    synced = sync.run_once()
    ref = synced["objectRef"]
    sink = io.BytesIO()
    metadata = shared.restore_to(OSS_INTEGRATION_ID, ref, sink)
    envelope = json.loads(sink.getvalue())

    assert synced["status"] == "synced"
    assert metadata.ref.object_id == OBJECT_ID
    assert metadata.content_type == "application/json"
    assert envelope["payload"]["entries"][0]["label"] == "职业"
    assert "accessLinks" not in envelope["payload"]
    assert "provider-secret-sentinel" not in sink.getvalue().decode()


def test_empty_region_restores_remote_and_unchanged_region_accepts_remote_update(tmp_path):
    provider = MemoryProvider()
    shared = storage(provider)
    profile_a, sync_a = sync_service(tmp_path, "region-a", shared)
    mutate(profile_a, sync_a, "聊天偏好", "简洁")
    sync_a.run_once()

    profile_b, sync_b = sync_service(tmp_path, "region-b", shared)
    restored = sync_b.run_once()
    assert restored["status"] == "synced"
    assert [item["label"] for item in profile_b.snapshot()["entries"]] == ["聊天偏好"]

    mutate(profile_b, sync_b, "兴趣", "阅读")
    sync_b.run_once()
    refreshed = sync_a.run_once()

    assert refreshed["status"] == "synced"
    assert {item["label"] for item in profile_a.snapshot()["entries"]} == {"聊天偏好", "兴趣"}


def test_divergence_requires_explicit_local_or_remote_resolution(tmp_path):
    provider = MemoryProvider()
    shared = storage(provider)
    profile_a, sync_a = sync_service(tmp_path, "region-a", shared)
    mutate(profile_a, sync_a, "共同", "baseline")
    sync_a.run_once()
    profile_b, sync_b = sync_service(tmp_path, "region-b", shared)
    sync_b.run_once()

    mutate(profile_a, sync_a, "本地", "a")
    mutate(profile_b, sync_b, "云端", "b")
    sync_b.run_once()

    conflict = sync_a.run_once()
    assert conflict["status"] == "conflict"
    assert {item["label"] for item in profile_a.snapshot()["entries"]} == {"共同", "本地"}

    sync_a.resolve_conflict("remote")
    remote = sync_a.run_once()
    assert remote["status"] == "synced"
    assert {item["label"] for item in profile_a.snapshot()["entries"]} == {"共同", "云端"}

    mutate(profile_a, sync_a, "保留本地", "yes")
    mutate(profile_b, sync_b, "再次云端", "new")
    sync_b.run_once()
    assert sync_a.run_once()["status"] == "conflict"
    sync_a.resolve_conflict("local")
    assert sync_a.run_once()["status"] == "synced"

    profile_c, sync_c = sync_service(tmp_path, "region-c", shared)
    sync_c.run_once()
    assert "保留本地" in {item["label"] for item in profile_c.snapshot()["entries"]}


def test_invalid_remote_snapshot_fails_closed_without_touching_empty_local(tmp_path):
    provider = MemoryProvider()
    shared = storage(provider)
    saved = shared.save(
        OSS_INTEGRATION_ID,
        OBJECT_ID,
        io.BytesIO(b'{"schemaVersion":1,"payload":{"entries":[]}}'),
        content_type="application/json",
    )
    profile, sync = sync_service(tmp_path, "empty", shared)

    result = sync.run_once()

    assert saved.ref.object_id == OBJECT_ID
    assert result["status"] == "failed"
    assert result["lastErrorCode"] == "personal_asset_sync_snapshot_invalid"
    assert profile.snapshot()["entries"] == []
