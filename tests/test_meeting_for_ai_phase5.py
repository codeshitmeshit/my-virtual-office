#!/usr/bin/env python3
"""Phase 5 coverage for busy Agent conflicts and pause/resume safety."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-phase5-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server


def with_store(status_dir):
    old = (server.STATUS_DIR, server.STATUS_FILE, server.WORKFLOW_STATE_FILE, dict(server._WORKFLOW_STATE))
    server.STATUS_DIR = status_dir
    server.STATUS_FILE = os.path.join(status_dir, "virtual-office-status.json")
    server.WORKFLOW_STATE_FILE = os.path.join(status_dir, "workflow-state.json")
    with server._WORKFLOW_LOCK:
        server._WORKFLOW_STATE.clear()
    return old


def restore_store(old):
    server.STATUS_DIR, server.STATUS_FILE, server.WORKFLOW_STATE_FILE, workflow_state = old
    with server._WORKFLOW_LOCK:
        server._WORKFLOW_STATE.clear()
        server._WORKFLOW_STATE.update(workflow_state)


def create_meeting(**overrides):
    body = {
        "topic": "Phase 5 Conflict Meeting",
        "purpose": "Handle busy agent safely.",
        "participants": ["busy-agent", "reviewer"],
        "moderator": "reviewer",
        "meetingType": "discussion",
        "maxRounds": 1,
        "context": "Phase 5 fixture.",
        "idempotencyKey": "phase5-create",
    }
    body.update(overrides)
    return server._handle_executable_meeting_create(body)


def mark_busy(agent_id="busy-agent"):
    with server._WORKFLOW_LOCK:
        server._WORKFLOW_STATE["project-1"] = {
            "active": True,
            "phase": "in_progress",
            "currentAssignee": agent_id,
            "currentTaskId": "task-1",
            "currentTaskTitle": "Implement a risky change",
        }


def test_phase5_busy_agent_requires_conflict_aware_creation_and_advisory_is_read_only():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            mark_busy()
            rejected = create_meeting(idempotencyKey="phase5-default-reject")
            assert rejected["_status"] == 409
            assert rejected["conflicts"][0]["agentId"] == "busy-agent"

            created = create_meeting(idempotencyKey="phase5-conflict-aware", allowConflicts=True)
            assert created["ok"] is True
            meeting = created["meeting"]
            assert meeting["stage"] == "conflict"
            conflict = meeting["conflicts"][0]
            assert conflict["reason"] == "project_task"
            assert conflict["riskLevel"] == "medium"
            assert conflict["advisory"]["status"] == "completed"
            assert conflict["advisory"]["recommendation"] == "wait"
            assert server._load_exec_meeting_store()["occupancy"] == {}

            run = server._handle_executable_meeting_run(meeting["id"], {})
            assert run["_status"] == 409
            assert run["conflicts"][0]["agentId"] == "busy-agent"
        finally:
            restore_store(old)


def test_phase5_reservation_does_not_lock_agent_and_refresh_rechecks_conflict():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            mark_busy()
            meeting = create_meeting(idempotencyKey="phase5-reserve", allowConflicts=True)["meeting"]
            reserved = server._handle_executable_meeting_conflict_action(meeting["id"], {
                "action": "reserve",
                "agentId": "busy-agent",
                "targetAt": "2026-06-18T01:00:00+08:00",
                "idempotencyKey": "reserve-once",
            })
            assert reserved["ok"] is True
            assert reserved["meeting"]["stage"] == "conflict"
            assert reserved["meeting"]["reservation"]["busy-agent"]["status"] == "scheduled"
            assert server._load_exec_meeting_store()["occupancy"] == {}

            refreshed = server._handle_executable_meeting_conflict_action(meeting["id"], {
                "action": "refresh",
                "idempotencyKey": "refresh-still-busy",
            })
            assert refreshed["meeting"]["stage"] == "conflict"
            assert refreshed["meeting"]["conflicts"][0]["agentId"] == "busy-agent"
        finally:
            restore_store(old)


def test_phase5_force_join_requires_confirmation_snapshots_work_and_resumes_once():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            mark_busy()
            meeting = create_meeting(idempotencyKey="phase5-force", allowConflicts=True)["meeting"]
            denied = server._handle_executable_meeting_conflict_action(meeting["id"], {
                "action": "force_join",
                "agentId": "busy-agent",
                "idempotencyKey": "force-denied",
            })
            assert denied["_status"] == 409

            forced = server._handle_executable_meeting_conflict_action(meeting["id"], {
                "action": "force_join",
                "agentId": "busy-agent",
                "confirmForce": True,
                "idempotencyKey": "force-confirmed",
            })
            assert forced["ok"] is True
            meeting = forced["meeting"]
            assert meeting["stage"] == "preparing"
            assert meeting["originalWork"]["busy-agent"]["pauseState"] == "logical_paused"
            assert server._load_exec_meeting_store()["occupancy"]["busy-agent"] == meeting["id"]

            completed = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "cancelled",
                "expectedVersion": meeting["version"],
                "idempotencyKey": "phase5-cancel",
            })
            assert completed["meeting"]["originalWork"]["busy-agent"]["resumeStatus"] == "resumed"
            repeated = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "cancelled",
                "idempotencyKey": "phase5-cancel",
            })
            assert repeated["idempotent"] is True
            events = server._handle_executable_meeting_detail(meeting["id"])["events"]
            assert len([e for e in events if e["type"] == "original_work_resumed"]) == 1
        finally:
            restore_store(old)


def test_phase5_force_join_transfers_existing_meeting_occupancy():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            first = create_meeting(
                topic="Existing Meeting",
                participants=["busy-agent", "first-reviewer"],
                moderator="first-reviewer",
                idempotencyKey="phase5-existing-meeting",
            )["meeting"]
            assert first["stage"] == "preparing"

            second = create_meeting(
                topic="Forced Meeting",
                participants=["busy-agent", "second-reviewer"],
                moderator="second-reviewer",
                allowConflicts=True,
                idempotencyKey="phase5-force-meeting-occupied",
            )["meeting"]
            assert second["stage"] == "conflict"
            assert second["conflicts"][0]["reason"] == "meeting_occupied"

            forced = server._handle_executable_meeting_conflict_action(second["id"], {
                "action": "force_join",
                "agentId": "busy-agent",
                "confirmForce": True,
                "idempotencyKey": "force-existing-meeting",
            })
            assert forced["ok"] is True
            meeting = forced["meeting"]
            assert meeting["stage"] == "preparing"
            assert all(c.get("status") != "open" for c in meeting["conflicts"])
            assert meeting["participantState"]["busy-agent"]["forcedJoin"] is True
            store = server._load_exec_meeting_store()
            assert store["occupancy"]["busy-agent"] == meeting["id"]
            assert store["occupancy"]["second-reviewer"] == meeting["id"]
            assert store["meetings"][first["id"]]["stage"] == "preparing"
        finally:
            restore_store(old)


def test_phase5_replace_and_single_agent_single_meeting_guard():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            mark_busy()
            meeting = create_meeting(idempotencyKey="phase5-replace", allowConflicts=True)["meeting"]
            replaced = server._handle_executable_meeting_conflict_action(meeting["id"], {
                "action": "replace",
                "agentId": "busy-agent",
                "replacement": "alt-agent",
                "idempotencyKey": "replace-busy",
            })
            assert replaced["ok"] is True
            assert replaced["meeting"]["stage"] == "preparing"
            assert "alt-agent" in replaced["meeting"]["participants"]
            assert "busy-agent" not in replaced["meeting"]["participants"]

            conflict = create_meeting(
                topic="Second Meeting",
                participants=["alt-agent", "other-agent"],
                moderator="alt-agent",
                idempotencyKey="phase5-second-conflict",
            )
            assert conflict["_status"] == 409
            assert conflict["conflicts"]["alt-agent"] == meeting["id"]
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_phase5_busy_agent_requires_conflict_aware_creation_and_advisory_is_read_only()
    test_phase5_reservation_does_not_lock_agent_and_refresh_rechecks_conflict()
    test_phase5_force_join_requires_confirmation_snapshots_work_and_resumes_once()
    test_phase5_force_join_transfers_existing_meeting_occupancy()
    test_phase5_replace_and_single_agent_single_meeting_guard()
    print("test_meeting_for_ai_phase5.py passed")
