import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/migrate_performance_stores.py"
APP = ROOT / "app"
sys.path.insert(0, str(APP))

from services.agent_event_repository import AgentEventRepository
from services.meeting_repository import MeetingDomainRepository, empty_store


def run(status, *args):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--status-dir", str(status), *args],
        cwd=ROOT, text=True, capture_output=True,
    )
    return completed, json.loads(completed.stdout)


def fixture(status):
    events = [{"id": "e1", "agentId": "a1", "conversationId": "c1", "sequence": 1, "type": "turn", "status": "done", "ts": 1}]
    (status / "codex-activity.json").write_text(json.dumps(events))
    meeting = empty_store()
    meeting["meetings"]["m1"] = {"id": "m1", "stage": "active_discussion", "participants": ["a1"]}
    meeting["events"]["m1"] = []
    meeting["occupancy"]["a1"] = "m1"
    (status / "meeting-domain.json").write_text(json.dumps(meeting))


def test_combined_migration_dry_run_apply_and_repeat(tmp_path):
    fixture(tmp_path)
    dry, report = run(tmp_path)
    assert dry.returncode == 0 and report["status"] == "validated"
    assert not (tmp_path / "agent-events.sqlite3").exists()
    applied, report = run(tmp_path, "--apply")
    assert applied.returncode == 0 and report["status"] == "migrated"
    assert AgentEventRepository(tmp_path).count() == 1
    assert MeetingDomainRepository(tmp_path).list_events("m1") == []
    assert set(report["backups"]) == {"codex-activity.json", "meeting-domain.json"}
    repeated, report = run(tmp_path, "--apply")
    assert repeated.returncode == 0 and report["status"] == "already_migrated"


def test_combined_migration_fails_closed_for_invalid_source(tmp_path):
    fixture(tmp_path)
    (tmp_path / "codex-activity.json").write_text("{broken")
    completed, report = run(tmp_path, "--apply")
    assert completed.returncode == 1 and report["status"] == "failed"
    assert not (tmp_path / "agent-events.sqlite3").exists()
    assert not (tmp_path / "meeting-domain.sqlite3").exists()
