#!/usr/bin/env python3
"""Phase 4 coverage for AI-originated meeting requests."""

import os
import sys
import tempfile
import json

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


def create_high_priority_confirmation_project_and_task():
    project = server._handle_project_create({
        "title": "High Priority AI Meeting Confirmation Project",
        "description": "Project level context should be retained.",
        "projectExecutionEnabled": False,
        "highPriorityAiMeetingAutoApprove": True,
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Resolve high priority blocker",
        "description": "The executor needs a fast AI meeting.",
        "assignee": "executor",
        "executorAgentId": "executor",
    })["task"]
    server._handle_task_create(project["id"], {
        "title": "Related high priority implementation task",
        "description": "Same high priority project related context.",
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
            project, task = create_high_priority_confirmation_project_and_task()

            missing_goal = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body(goal=""))
            assert missing_goal["_status"] == 400
            assert missing_goal["code"] == "goal_required"

            request = server._handle_meeting_request_create(project["id"], task["id"], valid_request_body())
            assert request["ok"] is True
            assert request["notification"]["status"] == "skipped_missing_webhook"
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
            records_path = os.path.join(status_dir, "feishu-notification-records.jsonl")
            with open(records_path, "r", encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]
            assert records[-1]["type"] == "application_form"
            assert records[-1]["related"]["id"] == req["id"]
            assert records[-1]["status"] == "skipped_missing_webhook"
        finally:
            restore_store(old)


def test_phase4_request_rejects_archive_manager_participant():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_high_priority_confirmation_project_and_task()
            blocked = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(
                    idempotencyKey="phase4-archive-manager-request",
                    suggestedParticipants=["executor", "archive-manager"],
                ),
            )
            assert blocked["_status"] == 400
            assert blocked["code"] == "archive_manager_not_meeting_participant"

            req = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(idempotencyKey="phase4-archive-manager-confirm"),
            )["request"]
            confirm_blocked = server._handle_meeting_request_confirm(req["id"], {
                "participants": ["executor", "archive-manager"],
                "moderator": "executor",
            })
            assert confirm_blocked["_status"] == 400
            assert confirm_blocked["code"] == "archive_manager_not_meeting_participant"
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


def test_phase4_high_priority_project_requires_user_confirmation_for_ai_request():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_high_priority_confirmation_project_and_task()
            selected = [f"task:{task['id']}"]

            created = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(
                    idempotencyKey="phase4-high-priority-auto",
                    urgency=3,
                    selectedContextIds=selected,
                    supplementalContext="AI supplied supplemental context.",
                ),
            )
            assert created["ok"] is True
            assert created.get("autoConfirmed") is None
            assert created["request"]["status"] == "pending"
            assert created["request"]["review"] == {}
            assert created["request"]["conversion"] == {}

            repeated = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(idempotencyKey="phase4-high-priority-auto", urgency=3),
            )
            assert repeated["idempotent"] is True
            assert repeated["request"]["status"] == "pending"

            detail = server._handle_meeting_request_detail(created["request"]["id"])
            assert detail["request"]["review"] == {}

            confirmed = server._handle_meeting_request_confirm(created["request"]["id"], {
                "confirmedBy": "user",
                "selectedContextIds": selected,
                "supplementalContext": "User approved supplemental context.",
                "idempotencyKey": "phase4-high-priority-user-confirm",
            })
            assert confirmed["ok"] is True
            assert confirmed["request"]["status"] == "confirmed"
            assert confirmed["request"]["review"]["autoConfirmed"] is False
            assert confirmed["meeting"]["createdByType"] == "user"
            assert confirmed["meeting"]["source"]["autoConfirmed"] is False
            assert "User approved supplemental context" in confirmed["meeting"]["context"]
            assert "Resolve high priority blocker" in confirmed["meeting"]["context"]

            project_after = server._handle_project_get(project["id"])["project"]
            assert project_after["highPriorityAiMeetingAutoApprove"] is True

            stored = server._load_projects()["projects"][0]
            assert stored["highPriorityAiMeetingAutoApprove"] is True
        finally:
            restore_store(old)


def test_phase4_high_priority_project_confirmation_overrides_high_urgency():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_high_priority_confirmation_project_and_task()
            created = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(idempotencyKey="phase4-high-priority-urgent", urgency=4),
            )
            assert created["ok"] is True
            assert created.get("autoConfirmed") is None
            assert created["request"]["status"] == "pending"
            assert created["request"]["urgency"] == 4
            assert created["request"]["review"] == {}
            assert created["request"]["conversion"] == {}
        finally:
            restore_store(old)


def test_phase4_project_auto_approve_flag_defaults_false_and_update_persists():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_project_and_task()
            assert project.get("highPriorityAiMeetingAutoApprove") is False

            req = server._handle_meeting_request_create(
                project["id"],
                task["id"],
                valid_request_body(idempotencyKey="phase4-default-non-auto", urgency=3),
            )
            assert req["ok"] is True
            assert req["autoConfirmed"] is True
            assert req["request"]["status"] == "confirmed"
            assert req["request"]["review"]["autoConfirmReason"] == "standard_project_ai_meeting_auto_approve"
            assert req["request"]["review"]["autoConfirmLabel"] == "已按普通项目自动批准"

            updated = server._handle_project_update(project["id"], {"highPriorityAiMeetingAutoApprove": True})
            assert updated["ok"] is True
            assert updated["project"]["highPriorityAiMeetingAutoApprove"] is True
            stored = server._load_projects()["projects"][0]
            assert stored["highPriorityAiMeetingAutoApprove"] is True
        finally:
            restore_store(old)


def test_phase4_reject_feedback_and_illegal_confirm():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_high_priority_confirmation_project_and_task()
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
            project, task = create_high_priority_confirmation_project_and_task()
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
            assert "Resolve high priority blocker" in meeting["context"]
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
    test_phase4_high_priority_project_requires_user_confirmation_for_ai_request()
    test_phase4_high_priority_project_confirmation_overrides_high_urgency()
    test_phase4_project_auto_approve_flag_defaults_false_and_update_persists()
    test_phase4_reject_feedback_and_illegal_confirm()
    test_phase4_confirm_creates_once_with_selected_context_snapshot()
    print("test_meeting_for_ai_phase4.py passed")
