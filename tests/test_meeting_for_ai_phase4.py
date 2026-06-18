#!/usr/bin/env python3
"""Phase 4 coverage for AI-originated meeting requests."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-phase4-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


def with_store(status_dir):
    old = (server.STATUS_DIR, server.STATUS_FILE, server.PROJECT_STORE)
    server.STATUS_DIR = status_dir
    server.STATUS_FILE = os.path.join(status_dir, "virtual-office-status.json")
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    return old


def restore_store(old):
    server.STATUS_DIR, server.STATUS_FILE, server.PROJECT_STORE = old


def create_project_and_task():
    project = server._handle_project_create({
        "title": "Phase 4 Project",
        "description": "Project level context should be a candidate.",
        "projectExecutionEnabled": False,
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Resolve architecture blocker",
        "description": "The executor cannot choose a design alone.",
        "assignee": "executor",
        "executorAgentId": "executor",
    })["task"]
    server._handle_task_create(project["id"], {
        "title": "Related implementation task",
        "description": "Same project related context.",
        "assignee": "reviewer",
    })
    return project, task


def valid_request_body(**overrides):
    body = {
        "requestingAgentId": "executor",
        "topic": "Architecture decision meeting",
        "purpose": "Choose the next implementation direction.",
        "goal": "Resolve the architecture blocker.",
        "expectedOutcome": "A decision with next steps.",
        "reason": "The executor needs another AI to review tradeoffs.",
        "suggestedParticipants": ["executor", "reviewer"],
        "suggestedModerator": "executor",
        "meetingType": "discussion",
        "maxRounds": 2,
        "idempotencyKey": "phase4-request",
    }
    body.update(overrides)
    return body


def test_phase4_request_quality_gate_and_pending_safety():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_project_and_task()

            missing_goal = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body(goal=""))
            assert missing_goal["_status"] == 400
            assert missing_goal["code"] == "goal_required"

            request = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body())
            assert request["ok"] is True
            req = request["request"]
            assert req["status"] == "pending"
            assert req["sourceType"] == "project_task"
            assert req["source"]["projectId"] == project["id"]
            assert req["source"]["taskId"] == task["id"]
            assert req["urgency"] == 3
            assert req["originalProposal"]["urgency"] == 3
            assert all(c.get("selected") is False for c in req["contextCandidates"])
            assert {c["sourceKind"] for c in req["contextCandidates"]}.issuperset({"project", "task", "related_task"})

            repeated = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body())
            assert repeated["idempotent"] is True
            assert repeated["request"]["id"] == req["id"]

            active_ids = {m["id"] for m in server._meeting_active_projection()}
            assert req["id"] not in active_ids
            assert server._load_exec_meeting_store()["occupancy"] == {}

            aggregate = server._meeting_request_list_filtered("status=pending")
            assert aggregate["pendingCount"] == 1
            assert aggregate["requests"][0]["id"] == req["id"]
            task_requests = server._meeting_request_list_filtered(f"projectId={project['id']}&taskId={task['id']}")
            assert task_requests["requests"][0]["id"] == req["id"]
        finally:
            restore_store(old)


def test_phase4_high_urgency_auto_confirms_agent_request():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_project_and_task()
            created = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(idempotencyKey="phase4-urgent-request", urgency=4),
            )
            assert created["ok"] is True
            assert created["autoConfirmed"] is True
            assert created["request"]["status"] == "confirmed"
            assert created["request"]["urgency"] == 4
            assert created["request"]["review"]["autoConfirmed"] is True
            assert created["request"]["conversion"]["autoRun"]["attempted"] is True
            assert created["request"]["conversion"]["autoRun"]["ok"] is True

            meeting = created["meeting"]
            assert meeting["stage"] != "preparing"
            assert meeting["createdByType"] == "agent"
            assert meeting["createdByAgentId"] == "executor"
            assert meeting["source"]["requestingAgentId"] == "executor"
            assert meeting["source"]["urgency"] == 4
            assert meeting["resolutionPolicy"] == "moderator_decision"

            active = server._meeting_active_projection()
            projected = next(m for m in active if m["id"] == meeting["id"])
            assert projected["createdByType"] == "agent"
            assert projected["createdByAgentId"] == "executor"
            assert projected["urgency"] == 4
            assert projected["executionStage"] != "preparing"
            assert projected["resolutionPolicy"] == "moderator_decision"
        finally:
            restore_store(old)


def test_phase4_reject_feedback_and_illegal_confirm():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_project_and_task()
            req = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body())["request"]

            rejected = server._handle_meeting_request_reject(req["id"], {"reason": "Continue without a meeting."})
            assert rejected["ok"] is True
            assert rejected["request"]["status"] == "rejected"

            project_after = server._handle_project_get(project["id"])["project"]
            task_after = next(t for t in project_after["tasks"] if t["id"] == task["id"])
            assert any("Continue without a meeting" in c["text"] for c in task_after.get("comments", []))

            confirm = server._handle_meeting_request_confirm(req["id"], {"participants": ["executor", "reviewer"]})
            assert confirm["_status"] == 409
            assert confirm["code"] == "request_rejected"
        finally:
            restore_store(old)


def test_phase4_confirm_creates_once_with_selected_context_snapshot():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_project_and_task()
            req = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body())["request"]
            selected = [c["id"] for c in req["contextCandidates"] if c["sourceKind"] == "task"]

            confirmed = server._handle_meeting_request_confirm(req["id"], {
                "topic": "Edited architecture meeting",
                "purpose": "Edited purpose",
                "participants": ["executor", "reviewer", "codex-local"],
                "moderator": "executor",
                "selectedContextIds": selected,
                "supplementalContext": "User approved supplemental context.",
                "idempotencyKey": "confirm-phase4",
            })
            assert confirmed["ok"] is True
            assert confirmed["request"]["status"] == "confirmed"
            meeting = confirmed["meeting"]
            assert meeting["topic"] == "Edited architecture meeting"
            assert meeting["source"]["meetingRequestId"] == req["id"]
            assert "User approved supplemental context" in meeting["context"]
            assert "Resolve architecture blocker" in meeting["context"]
            assert "Project level context should be a candidate" not in meeting["context"]
            assert meeting["participantState"]["executor"]["status"] == "reserved"
            assert meeting["resolutionPolicy"] == "moderator_decision"

            repeated = server._handle_meeting_request_confirm(req["id"], {
                "participants": ["executor", "reviewer", "codex-local"],
                "moderator": "executor",
                "idempotencyKey": "confirm-phase4",
            })
            assert repeated["idempotent"] is True
            assert repeated["meetingId"] == meeting["id"]
            active = server._meeting_active_projection()
            assert len([m for m in active if m["id"] == meeting["id"]]) == 1
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_phase4_request_quality_gate_and_pending_safety()
    test_phase4_high_urgency_auto_confirms_agent_request()
    test_phase4_reject_feedback_and_illegal_confirm()
    test_phase4_confirm_creates_once_with_selected_context_snapshot()
    print("test_meeting_for_ai_phase4.py passed")
