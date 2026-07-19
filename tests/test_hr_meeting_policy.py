"""End-to-end meeting policy coverage for the HR system Agent."""

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_HR_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-hr-meeting-status-"))

import server


def with_meeting_store(status_dir):
    previous = server.STATUS_DIR, server.STATUS_FILE
    server.STATUS_DIR = str(status_dir)
    server.STATUS_FILE = str(status_dir / "virtual-office-status.json")
    return previous


def restore_meeting_store(previous):
    server.STATUS_DIR, server.STATUS_FILE = previous


def test_legacy_meeting_allows_hr_and_still_rejects_archive_manager(tmp_path):
    previous = with_meeting_store(tmp_path)
    try:
        allowed = server._handle_meeting_create({
            "id": "legacy-hr",
            "topic": "HR coordination",
            "participants": ["main", "hr"],
            "organizer": "hr",
        })
        assert allowed["ok"] is True
        assert allowed["meeting"]["participants"] == ["main", "hr"]

        blocked = server._handle_meeting_create({
            "id": "legacy-archive",
            "topic": "Archive manager remains protected",
            "participants": ["main", "archive-manager"],
            "organizer": "main",
        })
        assert blocked["code"] == "archive_manager_not_meeting_participant"
        assert blocked["_status"] == 400
        meetings = server._load_meetings_file().get("_meetings", [])
        assert [meeting["id"] for meeting in meetings] == ["legacy-hr"]
    finally:
        restore_meeting_store(previous)


def test_executable_hr_meeting_claims_releases_and_restores_without_hr_performance_event(tmp_path):
    previous = with_meeting_store(tmp_path)
    try:
        created = server._handle_executable_meeting_create({
            "topic": "HR joins an ordinary meeting",
            "participants": ["main", "hr"],
            "moderator": "hr",
            "idempotencyKey": "hr-meeting-create",
        })
        assert created["ok"] is True
        meeting_id = created["meeting"]["id"]
        store = server._load_exec_meeting_store()
        assert store["occupancy"] == {"main": meeting_id, "hr": meeting_id}

        store["meetings"][meeting_id]["originalWork"] = {
            "hr": {
                "pauseState": "logical_paused",
                "resumeStatus": "pending",
                "resumeToken": "hr-resume",
            }
        }
        server._save_exec_meeting_store(store)
        server._handle_executable_meeting_transition(
            meeting_id, {"action": "start", "expectedVersion": 1},
        )
        server._handle_executable_meeting_transition(
            meeting_id, {"stage": "active_discussion", "expectedVersion": 2},
        )
        server._handle_executable_meeting_transition(
            meeting_id, {"stage": "summarizing", "expectedVersion": 3},
        )
        completed = server._handle_executable_meeting_transition(
            meeting_id,
            {"stage": "completed", "expectedVersion": 4, "summary": "HR participated."},
        )
        assert completed["meeting"]["stage"] == "completed"

        final_store = server._load_exec_meeting_store()
        final_meeting = final_store["meetings"][meeting_id]
        assert final_store["occupancy"] == {}
        assert final_meeting["originalWork"]["hr"]["resumeStatus"] == "resumed"
        assert final_meeting["scoreAwarded"]["meetingParticipantXp"]["participants"] == ["main"]
        event_types = [event["type"] for event in final_store["events"][meeting_id]]
        assert "original_work_resumed" in event_types
        assert not any("performance" in event_type or event_type.startswith("hr_") for event_type in event_types)

        scores = json.loads((tmp_path / "project-scores.json").read_text(encoding="utf-8"))
        assert "main" in scores["agents"]
        assert "hr" not in scores["agents"]
        assert not (tmp_path / "human-resources").exists()
    finally:
        restore_meeting_store(previous)
