import json
import fcntl
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/migrate_meeting_store.py"


def legacy_fixture(path: Path, *, dangling=False):
    meeting = {"id": "m1", "stage": "active_discussion", "participants": ["a1", "a2"]}
    executable = {"meetings": {"m1": meeting}, "events": {"m1": []}, "occupancy": {"a1": "m1"}, "idempotency": {"create": "m1"}, "updatedAt": "2026-01-01T00:00:00Z"}
    requests = {"requests": {"r1": {"id": "r1", "status": "confirmed", "conversion": {"meetingId": "missing" if dangling else "m1"}}}, "idempotency": {"confirm": "r1"}, "updatedAt": "2026-01-01T00:00:01Z"}
    (path / "executable-meetings.json").write_text(json.dumps(executable), encoding="utf-8")
    (path / "meeting-requests.json").write_text(json.dumps(requests), encoding="utf-8")


def run(status: Path, *args):
    completed = subprocess.run([sys.executable, str(SCRIPT), "--status-dir", str(status), *args], cwd=ROOT, text=True, capture_output=True)
    return completed, json.loads(completed.stdout)


def load_script_module():
    spec = importlib.util.spec_from_file_location("meeting_migration_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_module_main(module, status, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--status-dir", str(status), "--apply"])
    code = module.main()
    output = capsys.readouterr().out
    return code, json.loads(output)


def test_dry_run_validates_without_writing_unified_or_backups(tmp_path):
    legacy_fixture(tmp_path)
    completed, report = run(tmp_path)
    assert completed.returncode == 0 and report["status"] == "validated"
    assert report["counts"] == {"meetings": 1, "events": 1, "occupancy": 1, "requests": 1}
    assert {item["status"] for item in report["relationshipChecks"].values()} == {"pass"}
    assert not (tmp_path / "meeting-domain.json").exists()
    assert not list(tmp_path.glob("*.backup-*"))


def test_apply_backs_up_migrates_and_repeated_run_is_noop(tmp_path):
    legacy_fixture(tmp_path)
    executable_before = (tmp_path / "executable-meetings.json").read_bytes()
    requests_before = (tmp_path / "meeting-requests.json").read_bytes()
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 0 and report["status"] == "migrated"
    unified = json.loads((tmp_path / "meeting-domain.json").read_text())
    assert unified["schemaVersion"] == 1
    assert unified["requests"]["r1"]["conversion"]["meetingId"] == "m1"
    assert (tmp_path / report["backups"]["executable"]).read_bytes() == executable_before
    assert (tmp_path / report["backups"]["requests"]).read_bytes() == requests_before
    digest = (tmp_path / "meeting-domain.json").read_bytes()
    repeated, repeated_report = run(tmp_path, "--apply")
    assert repeated.returncode == 0 and repeated_report["status"] == "already_migrated"
    assert repeated_report["relationshipChecks"]["requestMeetingLinks"]["checked"] == 1
    assert (tmp_path / "meeting-domain.json").read_bytes() == digest
    assert len(list(tmp_path.glob("*.backup-*"))) == 2


def test_single_legacy_store_migrates_without_manufacturing_missing_source(tmp_path):
    meeting = {"id": "m1", "stage": "active_discussion", "participants": ["a1"]}
    executable = {
        "meetings": {"m1": meeting}, "events": {"m1": []},
        "occupancy": {"a1": "m1"}, "idempotency": {},
    }
    source = tmp_path / "executable-meetings.json"
    source.write_text(json.dumps(executable), encoding="utf-8")

    dry_run, dry_report = run(tmp_path)
    assert dry_run.returncode == 0 and dry_report["counts"]["requests"] == 0

    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 0 and report["status"] == "migrated"
    assert set(report["backups"]) == {"executable"}
    assert (tmp_path / report["backups"]["executable"]).read_bytes() == source.read_bytes()
    assert not (tmp_path / "meeting-requests.json").exists()
    assert json.loads((tmp_path / "meeting-domain.json").read_text())["requests"] == {}


def test_malformed_dangling_or_symlink_input_fails_without_destination(tmp_path):
    legacy_fixture(tmp_path, dangling=True)
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["code"] == "meeting_store_conflict"
    assert not (tmp_path / "meeting-domain.json").exists()


def test_malformed_nested_or_deep_json_returns_stable_failure_report(tmp_path):
    legacy_fixture(tmp_path)
    requests = {"requests": {"r1": {"id": "r1", "status": "confirmed", "conversion": "bad"}}, "idempotency": {}}
    (tmp_path / "meeting-requests.json").write_text(json.dumps(requests))
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["code"] == "meeting_store_conflict"
    deep = "[" * 1500 + "]" * 1500
    (tmp_path / "meeting-requests.json").write_text(deep)
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["status"] == "failed"
    assert "Traceback" not in completed.stderr
    (tmp_path / "meeting-requests.json").write_text("{broken", encoding="utf-8")
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["code"] == "meeting_store_migration_input_invalid"
    outside = tmp_path / "outside.json"; outside.write_text("{}")
    (tmp_path / "meeting-requests.json").unlink(); (tmp_path / "meeting-requests.json").symlink_to(outside)
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1
    assert not (tmp_path / "meeting-domain.json").exists()


def test_server_lock_and_changed_source_digest_fail_closed(tmp_path):
    legacy_fixture(tmp_path)
    lock_fd = os.open(tmp_path / "meeting-store-active.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        completed, report = run(tmp_path, "--apply")
        assert completed.returncode == 1 and report["code"] == "meeting_store_server_running"
    finally:
        os.close(lock_fd)
    assert run(tmp_path, "--apply")[0].returncode == 0
    requests = json.loads((tmp_path / "meeting-requests.json").read_text())
    requests["requests"]["r2"] = {"id": "r2", "status": "pending"}
    (tmp_path / "meeting-requests.json").write_text(json.dumps(requests))
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["code"] == "migration_source_changed"


def test_already_migrated_rejects_same_counts_with_changed_semantics(tmp_path):
    legacy_fixture(tmp_path)
    assert run(tmp_path, "--apply")[0].returncode == 0
    unified_path = tmp_path / "meeting-domain.json"
    unified = json.loads(unified_path.read_text())
    unified["meetings"]["m1"]["stage"] = "paused"
    unified["idempotency"]["meetings"] = {"different": "value"}
    unified_path.write_text(json.dumps(unified))
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["code"] == "meeting_store_conflict"


def test_apply_creates_private_store_backups_and_report_under_open_umask(tmp_path):
    legacy_fixture(tmp_path)
    command = [sys.executable, str(SCRIPT), "--status-dir", str(tmp_path), "--apply"]
    completed = subprocess.run(["sh", "-c", 'umask 000; exec "$@"', "sh", *command], cwd=ROOT, text=True, capture_output=True)
    report = json.loads(completed.stdout)
    assert completed.returncode == 0
    paths = [tmp_path / "meeting-domain.json", tmp_path / "meeting-store-migration-report.json"]
    paths += [tmp_path / name for name in report["backups"].values()]
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in paths)


def test_private_writer_handles_partial_os_writes(tmp_path, monkeypatch):
    module = load_script_module()
    original_write = module.os.write
    calls = []
    def short_write(descriptor, content):
        length = max(1, min(7, len(content)))
        calls.append(length)
        return original_write(descriptor, content[:length])
    monkeypatch.setattr(module.os, "write", short_write)
    payload = b"meeting-backup" * 100
    target = tmp_path / "backup"
    module._write_private(target, payload, exclusive=True)
    assert len(calls) > 1
    assert target.read_bytes() == payload


def test_migration_disk_failure_preserves_sources_and_does_not_cut_over(tmp_path, monkeypatch, capsys):
    legacy_fixture(tmp_path)
    before = {name: (tmp_path / name).read_bytes() for name in ("executable-meetings.json", "meeting-requests.json")}
    module = load_script_module()
    original = module._write_private
    def fail_backup(path, content, **kwargs):
        if ".backup-" in path.name:
            raise OSError("disk full")
        return original(path, content, **kwargs)
    monkeypatch.setattr(module, "_write_private", fail_backup)
    code, report = call_module_main(module, tmp_path, monkeypatch, capsys)
    assert code == 1 and report["status"] == "failed"
    assert not (tmp_path / "meeting-domain.json").exists()
    assert all((tmp_path / name).read_bytes() == content for name, content in before.items())


def test_migration_report_preflight_failure_does_not_cut_over(tmp_path, monkeypatch, capsys):
    legacy_fixture(tmp_path)
    module = load_script_module()
    original = module._write_report
    def fail_prepared(path, report):
        if report.get("status") == "prepared":
            raise OSError("report fsync failed")
        return original(path, report)
    monkeypatch.setattr(module, "_write_report", fail_prepared)
    code, report = call_module_main(module, tmp_path, monkeypatch, capsys)
    assert code == 1 and report["status"] == "failed"
    assert not (tmp_path / "meeting-domain.json").exists()


def test_migration_destination_replace_failure_preserves_legacy_and_no_authority(tmp_path, monkeypatch, capsys):
    legacy_fixture(tmp_path)
    module = load_script_module()
    original = module.MeetingDomainRepository._write_atomic
    def fail_destination(repository, data):
        if repository.status_dir == tmp_path.resolve():
            raise OSError("destination replace failed")
        return original(repository, data)
    monkeypatch.setattr(module.MeetingDomainRepository, "_write_atomic", fail_destination)
    code, report = call_module_main(module, tmp_path, monkeypatch, capsys)
    assert code == 1 and report["status"] == "failed"
    assert not (tmp_path / "meeting-domain.json").exists()
    assert (tmp_path / "executable-meetings.json").exists()
    assert (tmp_path / "meeting-requests.json").exists()


def test_source_change_after_prepared_report_aborts_before_cutover(tmp_path, monkeypatch, capsys):
    legacy_fixture(tmp_path)
    module = load_script_module()
    original = module._write_report
    def mutate_after_prepared(path, report):
        result = original(path, report)
        if report.get("status") == "prepared":
            requests = json.loads((tmp_path / "meeting-requests.json").read_text())
            requests["requests"]["r2"] = {"id": "r2", "status": "pending"}
            (tmp_path / "meeting-requests.json").write_text(json.dumps(requests))
        return result
    monkeypatch.setattr(module, "_write_report", mutate_after_prepared)
    code, report = call_module_main(module, tmp_path, monkeypatch, capsys)
    assert code == 1 and report["code"] == "migration_source_changed"
    assert not (tmp_path / "meeting-domain.json").exists()


def test_report_cannot_alias_destination_legacy_or_active_lock(tmp_path):
    legacy_fixture(tmp_path)
    protected = ["meeting-domain.json", "executable-meetings.json", "meeting-requests.json", "meeting-store-active.lock"]
    original = {name: (tmp_path / name).read_bytes() for name in protected if (tmp_path / name).exists()}
    for name in protected:
        completed, report = run(tmp_path, "--apply", "--report", str(tmp_path / name))
        assert completed.returncode == 1 and report["code"] == "meeting_store_migration_path_invalid"
        for original_name, content in original.items():
            assert (tmp_path / original_name).read_bytes() == content
        assert not (tmp_path / "meeting-domain.json").exists()
