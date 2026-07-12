import copy
import errno
import json
import os
import stat
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.meeting_repository import MeetingDomainRepository, MeetingStoreError, acquire_active_lock, empty_store


def meeting(meeting_id="m1", stage="active_discussion"):
    return {"id": meeting_id, "stage": stage, "participants": ["a1", "a2"]}


def test_repository_initializes_one_store_and_returns_deep_copies(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "empty"
    saved, _ = repo.update(lambda data: data["meetings"].update({"m1": meeting()}))
    assert (tmp_path / "meeting-domain.json").exists()
    assert not (tmp_path / "executable-meetings.json").exists()
    assert not (tmp_path / "meeting-requests.json").exists()
    saved["meetings"]["m1"]["stage"] = "failed"
    assert repo.snapshot()["meetings"]["m1"]["stage"] == "active_discussion"


def test_repository_requires_migration_when_legacy_data_exists(tmp_path):
    (tmp_path / "executable-meetings.json").write_text(json.dumps({"meetings": {"m1": meeting()}}))
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "migration_required"
    try:
        repo.snapshot()
        assert False, "expected migration requirement"
    except MeetingStoreError as error:
        assert error.code == "meeting_store_migration_required"
    assert not (tmp_path / "meeting-domain.json").exists()


def test_repository_rejects_unknown_or_invalid_unified_schema(tmp_path):
    path = tmp_path / "meeting-domain.json"
    data = empty_store(); data["schemaVersion"] = 99
    path.write_text(json.dumps(data))
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "invalid"
    try:
        repo.snapshot(); assert False
    except MeetingStoreError as error:
        assert error.code == "meeting_store_version_unsupported"


def test_repository_rejects_dangling_relationships_as_invalid_authority(tmp_path):
    data = empty_store()
    data["requests"]["r1"] = {"id": "r1", "status": "confirmed", "conversion": {"meetingId": "missing"}}
    (tmp_path / "meeting-domain.json").write_text(json.dumps(data))
    repo = MeetingDomainRepository(tmp_path)
    assert repo.authority_state() == "invalid"
    try:
        repo.snapshot(); assert False
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
    repo.update(lambda data: None)
    barrier = threading.Barrier(9)
    errors = []
    def worker(index):
        try:
            barrier.wait()
            repo.update(lambda data: data["idempotency"]["callbacks"].update({f"e{index}": index}))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join(timeout=3)
    assert errors == []
    assert repo.snapshot()["idempotency"]["callbacks"] == {f"e{index}": index for index in range(8)}


def test_compatibility_views_share_one_atomic_store(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.replace_executable({"meetings": {"m1": meeting()}, "events": {"m1": []}, "occupancy": {}, "idempotency": {"create": "m1"}})
    repo.replace_requests({"requests": {"r1": {"id": "r1", "status": "confirmed", "conversion": {"meetingId": "m1"}}}, "idempotency": {"confirm": "r1"}})
    unified = json.loads((tmp_path / "meeting-domain.json").read_text())
    assert set(unified) >= {"meetings", "events", "occupancy", "requests", "idempotency", "schemaVersion"}
    assert unified["idempotency"]["meetings"] == {"create": "m1"}
    assert unified["idempotency"]["requests"] == {"confirm": "r1"}
    assert repo.executable_view()["meetings"]["m1"]["id"] == "m1"
    assert repo.request_view()["requests"]["r1"]["conversion"]["meetingId"] == "m1"


def test_cache_invalidates_after_external_atomic_replacement(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.update(lambda data: data["meetings"].update({"m1": meeting()}))
    assert repo.snapshot()["meetings"]["m1"]["stage"] == "active_discussion"
    changed = repo.snapshot(); changed["meetings"]["m1"]["stage"] = "paused"
    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps(changed))
    os.replace(replacement, tmp_path / "meeting-domain.json")
    assert repo.snapshot()["meetings"]["m1"]["stage"] == "paused"


def test_atomic_writer_rejects_precreated_symlink_and_preserves_target(tmp_path, monkeypatch):
    repo = MeetingDomainRepository(tmp_path)
    target = tmp_path / "outside-secret"
    target.write_text("preserve")
    temporary = tmp_path / f".meeting-domain.json.tmp-{os.getpid()}-{threading.get_ident()}"
    temporary.symlink_to(target)
    try:
        repo.update(lambda data: None); assert False
    except FileExistsError:
        pass
    assert target.read_text() == "preserve"


def test_atomic_replace_failure_keeps_previous_store(tmp_path, monkeypatch):
    repo = MeetingDomainRepository(tmp_path)
    repo.update(lambda data: None)
    before = (tmp_path / "meeting-domain.json").read_bytes()
    original_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda source, target: (_ for _ in ()).throw(OSError("replace failed")))
    try:
        repo.update(lambda data: data["idempotency"]["callbacks"].update({"e": 1})); assert False
    except OSError:
        pass
    monkeypatch.setattr(os, "replace", original_replace)
    assert (tmp_path / "meeting-domain.json").read_bytes() == before


def test_directory_fsync_io_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    repo = MeetingDomainRepository(tmp_path)
    original_fsync = os.fsync
    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.EIO, "directory fsync failed")
        return original_fsync(descriptor)
    monkeypatch.setattr(os, "fsync", fail_directory)
    try:
        repo.update(lambda data: None); assert False
    except OSError as error:
        assert error.errno == errno.EIO


def test_active_lock_rejects_symlink_without_touching_target(tmp_path):
    target = tmp_path / "outside"
    target.write_text("preserve")
    (tmp_path / "meeting-store-active.lock").symlink_to(target)
    try:
        acquire_active_lock(tmp_path); assert False
    except OSError:
        pass
    assert target.read_text() == "preserve"
