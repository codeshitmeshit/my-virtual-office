import copy
import errno
import json
import os
import stat
import sys
import tempfile
import threading
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.meeting_repository import DATABASE_FILENAME, MeetingDomainRepository, MeetingStoreError, acquire_active_lock, empty_store


def meeting(meeting_id="m1", stage="active_discussion"):
    return {"id": meeting_id, "stage": stage, "participants": ["a1", "a2"]}


def test_repository_initializes_one_store_and_returns_deep_copies(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "empty"
    saved, _ = repo.create_meeting(lambda data: data["meetings"].update({"m1": meeting()}))
    assert (tmp_path / DATABASE_FILENAME).exists()
    assert not (tmp_path / "executable-meetings.json").exists()
    assert not (tmp_path / "meeting-requests.json").exists()
    saved["meetings"]["m1"]["stage"] = "failed"
    assert repo.get_meeting("m1")["stage"] == "active_discussion"


def test_repository_requires_migration_when_legacy_data_exists(tmp_path):
    (tmp_path / "executable-meetings.json").write_text(json.dumps({"meetings": {"m1": meeting()}}))
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "migration_required"
    try:
        repo.export_for_migration()
        assert False, "expected migration requirement"
    except MeetingStoreError as error:
        assert error.code == "meeting_store_migration_required"
    assert not (tmp_path / "meeting-domain.json").exists()


def test_repository_requires_migration_for_valid_legacy_unified_schema(tmp_path):
    path = tmp_path / "meeting-domain.json"
    data = empty_store(); data["schemaVersion"] = 99
    path.write_text(json.dumps(data))
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "invalid"
    try:
        repo.export_for_migration(); assert False
    except MeetingStoreError as error:
        assert error.code == "meeting_store_version_unsupported"


def test_repository_rejects_dangling_relationships_as_invalid_authority(tmp_path):
    data = empty_store()
    data["requests"]["r1"] = {"id": "r1", "status": "confirmed", "conversion": {"meetingId": "missing"}}
    (tmp_path / "meeting-domain.json").write_text(json.dumps(data))
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "invalid"
    try:
        repo.export_for_migration(); assert False
    except MeetingStoreError as error:
        assert error.code == "meeting_store_conflict"


def test_repository_rejects_malformed_nested_relationship_types(tmp_path):
    for mutate in (
        lambda data: data["requests"].update({"r1": {"id": "r1", "status": "confirmed", "conversion": "bad"}}),
        lambda data: data["meetings"].update({"m1": {"id": "m1", "stage": "active_discussion", "participants": 1}}),
    ):
        data = empty_store(); mutate(data)
        (tmp_path / "meeting-domain.json").write_text(json.dumps(data))
        assert MeetingDomainRepository(tmp_path).authority_state() == "invalid"


def test_repository_serializes_concurrent_updates_without_lost_entries(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.initialize_empty()
    repo.create_request(lambda data: data["requests"].update({"r1": {"id": "r1", "status": "pending"}}))
    barrier = threading.Barrier(9)
    errors = []
    def worker(index):
        try:
            barrier.wait()
            repo.mutate_request("r1", lambda data: data["idempotency"]["callbacks"].update({f"e{index}": index}))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join(timeout=3)
    assert errors == []
    assert repo.export_for_migration()["idempotency"]["callbacks"] == {f"e{index}": index for index in range(8)}


def test_typed_apis_share_one_atomic_store(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.create_meeting(lambda data: (data["meetings"].update({"m1": meeting()}), data["events"].update({"m1": []})))
    repo.create_request(lambda data: data["requests"].update({"r1": {"id": "r1", "status": "confirmed", "conversion": {"meetingId": "m1"}}}))
    unified = repo.export_for_migration()
    assert set(unified) >= {"meetings", "events", "occupancy", "requests", "idempotency", "schemaVersion"}
    assert repo.get_meeting("m1")["id"] == "m1"
    assert repo.get_request("r1")["conversion"]["meetingId"] == "m1"


def test_cache_invalidates_after_external_sqlite_update(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.create_meeting(lambda data: data["meetings"].update({"m1": meeting()}))
    assert repo.get_meeting("m1")["stage"] == "active_discussion"
    path = tmp_path / DATABASE_FILENAME
    connection = sqlite3.connect(path)
    payload = json.dumps({**meeting(), "stage": "paused"}, sort_keys=True, separators=(",", ":"))
    connection.execute("UPDATE meetings SET payload_json=? WHERE id='m1'", (payload,))
    connection.commit(); connection.close()
    assert repo.get_meeting("m1")["stage"] == "paused"


def test_sqlite_authority_rejects_symlink_and_preserves_target(tmp_path, monkeypatch):
    repo = MeetingDomainRepository(tmp_path)
    target = tmp_path / "outside-secret"
    target.write_text("preserve")
    (tmp_path / DATABASE_FILENAME).symlink_to(target)
    try:
        repo.initialize_empty(); assert False
    except (sqlite3.OperationalError, MeetingStoreError):
        pass
    assert target.read_text() == "preserve"


def test_transaction_failure_keeps_previous_store(tmp_path, monkeypatch):
    repo = MeetingDomainRepository(tmp_path)
    repo.initialize_empty()
    repo.create_request(lambda data: data["requests"].update({"r1": {"id": "r1", "status": "pending"}}))
    before = repo.export_for_migration()
    original = repo._sync_idempotency
    monkeypatch.setattr(repo, "_sync_idempotency", lambda *args: (_ for _ in ()).throw(OSError("write failed")))
    try:
        repo.mutate_request("r1", lambda data: data["idempotency"]["callbacks"].update({"e": 1})); assert False
    except OSError:
        pass
    monkeypatch.setattr(repo, "_sync_idempotency", original)
    assert repo.export_for_migration() == before


def test_database_file_is_private(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.initialize_empty()
    assert (tmp_path / DATABASE_FILENAME).stat().st_mode & 0o777 == 0o600


def test_active_lock_rejects_symlink_without_touching_target(tmp_path):
    target = tmp_path / "outside"
    target.write_text("preserve")
    (tmp_path / "meeting-store-active.lock").symlink_to(target)
    try:
        acquire_active_lock(tmp_path); assert False
    except OSError:
        pass
    assert target.read_text() == "preserve"
