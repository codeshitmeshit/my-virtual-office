#!/usr/bin/env python3
"""Meeting requests block Project Execution tasks until resolution."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-block-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


AGENTS = [
    {"id": "executor", "statusKey": "executor", "providerAgentId": "executor", "providerKind": "openclaw", "name": "Executor"},
    {"id": "reviewer", "statusKey": "reviewer", "providerAgentId": "reviewer", "providerKind": "openclaw", "name": "Reviewer"},
]


def with_store(status_dir):
    old = (server.STATUS_DIR, server.PROJECT_STORE, server.get_roster)
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    server.get_roster = lambda: AGENTS
    return old


def restore_store(old):
    server.STATUS_DIR, server.PROJECT_STORE, server.get_roster = old


def create_fixture_project(workspace):
    project = server._handle_project_create({
        "title": "Meeting Block Fixture",
        "projectExecutionEnabled": True,
        "workspacePath": workspace,
        "defaultExecutorAgentId": "executor",
        "defaultReviewerAgentId": "reviewer",
    })["project"]
    validation = server._handle_project_execution_workspace_validate(project["id"], {"workspacePath": workspace})
    assert validation["ok"] is True
    task = server._handle_task_create(project["id"], {"title": "Resolve ambiguity", "columnId": project["columns"][0]["id"], "assignee": "executor"})["task"]
    return project, task


def meeting_request_body(suffix=""):
    return {
        "goal": f"Align ambiguity {suffix}".strip(),
        "expectedOutcome": "Consensus on how to continue",
        "reason": "The agent found conflicting requirements.",
        "requestingAgentId": "executor",
        "suggestedParticipants": ["executor", "reviewer"],
        "suggestedModerator": "reviewer",
        "urgency": 3,
    }


def reload_task(project_id, task_id):
    _, project, task = server._project_execution_find(project_id, task_id)
    assert project and task
    return project, task


def test_meeting_request_blocks_task_and_prevents_duplicate_request():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_fixture_project(status_dir)
            result = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body())
            assert result["ok"] is True
            req = result["request"]
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "awaiting_meeting_resolution"
            assert task["columnId"] == next(c["id"] for c in project["columns"] if c["title"] == "In Progress")
            assert task["meetingBlocker"]["requestId"] == req["id"]
            assert project["workflowPhase"] == "awaiting_meeting_resolution"
            assert project["activeTaskId"] == task["id"]

            duplicate = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("again"))
            assert duplicate["ok"] is True
            assert duplicate.get("existingBlockingRequest") is True
            assert duplicate["request"]["id"] == req["id"]
        finally:
            restore_store(old)


def test_meeting_request_list_sorts_unprocessed_before_processed_then_time():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            store = {
                "requests": {
                    "confirmed-new": {"id": "confirmed-new", "status": "confirmed", "createdAt": "2026-06-23T10:03:00+00:00", "updatedAt": "2026-06-23T10:03:00+00:00"},
                    "pending-old": {"id": "pending-old", "status": "pending", "createdAt": "2026-06-23T10:01:00+00:00", "updatedAt": "2026-06-23T10:01:00+00:00"},
                    "rejected-newer": {"id": "rejected-newer", "status": "rejected", "createdAt": "2026-06-23T10:04:00+00:00", "updatedAt": "2026-06-23T10:04:00+00:00"},
                    "pending-new": {"id": "pending-new", "status": "pending", "createdAt": "2026-06-23T10:02:00+00:00", "updatedAt": "2026-06-23T10:02:00+00:00"},
                },
                "idempotency": {},
                "updatedAt": "2026-06-23T10:05:00+00:00",
            }
            server._save_meeting_request_store(store)

            listed = server._meeting_request_list_filtered()["requests"]
            assert [r["id"] for r in listed] == ["pending-new", "pending-old", "rejected-newer", "confirmed-new"]
        finally:
            restore_store(old)


def test_meeting_request_confirm_reject_and_user_takeover_paths():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body())["request"]
            confirmed = server._handle_meeting_request_confirm(req["id"], {"confirmedBy": "user"})
            assert confirmed["ok"] is True
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "awaiting_meeting_resolution"
            assert task["meetingBlocker"]["status"] == "confirmed"
            assert task["meetingBlocker"]["meetingId"] == confirmed["meetingId"]

            takeover = server._handle_project_execution_meeting_blocker_action(project["id"], task["id"], {"action": "mark_blocked", "feedback": "User decided meeting cannot resolve this."})
            assert takeover["ok"] is True
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "blocked"
            assert "cannot resolve" in task["blockedReason"]

            project2, task2 = create_fixture_project(status_dir)
            req2 = server._handle_meeting_request_create(project2["id"], task2["id"], meeting_request_body("reject"))["request"]
            rejected = server._handle_meeting_request_reject(req2["id"], {"reason": "Wrong participants"})
            assert rejected["ok"] is True
            project2, task2 = reload_task(project2["id"], task2["id"])
            assert task2["executionState"] == "awaiting_meeting_resolution"
            assert task2["meetingBlocker"]["status"] == "rejected"
            assert task2["meetingBlocker"]["awaitingUserDecision"] is True
        finally:
            restore_store(old)


def test_meeting_blocker_continue_starts_task_synchronously():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_start = server._handle_project_execution_start
        started = []
        try:
            def fake_start(project_id, task_id, body=None):
                started.append((project_id, task_id, body or {}))
                return {"ok": True, "status": "started", "taskId": task_id, "attemptId": "a-continue"}

            server._handle_project_execution_start = fake_start
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("continue"))["request"]
            rejected = server._handle_meeting_request_reject(req["id"], {"reason": "Wrong participants"})
            assert rejected["ok"] is True

            continued = server._handle_project_execution_meeting_blocker_action(project["id"], task["id"], {"action": "continue_execution"})
            assert continued["ok"] is True
            assert continued["status"] == "started"
            assert continued["startResult"]["ok"] is True
            assert started and started[-1][1] == task["id"]
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "backlog"
            assert task["meetingBlocker"]["status"] == "cleared"
        finally:
            server._handle_project_execution_start = old_start
            restore_store(old)


def test_meeting_blocker_continue_reports_start_failure_and_refreshable_state():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_start = server._handle_project_execution_start
        try:
            def fake_start(project_id, task_id, body=None):
                return {"ok": False, "error": "A valid executor agent is required", "code": "executor_required", "_status": 409}

            server._handle_project_execution_start = fake_start
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("continue fail"))["request"]
            rejected = server._handle_meeting_request_reject(req["id"], {"reason": "Wrong participants"})
            assert rejected["ok"] is True

            continued = server._handle_project_execution_meeting_blocker_action(project["id"], task["id"], {"action": "continue_execution"})
            assert continued["ok"] is False
            assert continued["status"] == "start_failed"
            assert continued["code"] == "executor_required"
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "backlog"
            assert task["columnId"] == next(c["id"] for c in project["columns"] if c["title"] == "Backlog")
            assert task["meetingBlocker"]["status"] == "cleared"
            assert task["lastError"] == "A valid executor agent is required"
            assert project["workflowPhase"] == "executor_required"
            assert project["projectExecutionFlowStopReason"] == "meeting_override_start_failed"
        finally:
            server._handle_project_execution_start = old_start
            restore_store(old)


def test_meeting_result_approved_releases_task_and_no_consensus_blocks():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_start = server._handle_project_execution_start
        started = []
        try:
            def fake_start(project_id, task_id, body=None):
                started.append((project_id, task_id, body or {}))
                return {"ok": True, "status": "started", "taskId": task_id}

            server._handle_project_execution_start = fake_start
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("approved"))["request"]
            meeting = {"id": "m-approved", "projectId": project["id"], "source": {"meetingRequestId": req["id"], "projectId": project["id"], "taskId": task["id"]}, "stage": "completed", "result": {"outcome": "approved", "decision": "Consensus reached."}}
            applied = server._project_execution_apply_meeting_result(meeting)
            assert applied["ok"] is True
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "backlog"
            assert task["columnId"] == next(c["id"] for c in project["columns"] if c["title"] == "Backlog")
            assert task["meetingBlocker"]["status"] == "resolved_continue"
            assert started and started[-1][1] == task["id"]

            project2, task2 = create_fixture_project(status_dir)
            req2 = server._handle_meeting_request_create(project2["id"], task2["id"], meeting_request_body("no consensus"))["request"]
            meeting2 = {"id": "m-no", "projectId": project2["id"], "source": {"meetingRequestId": req2["id"], "projectId": project2["id"], "taskId": task2["id"]}, "stage": "completed", "result": {"outcome": "no_consensus", "decision": "No consensus."}}
            applied2 = server._project_execution_apply_meeting_result(meeting2)
            assert applied2["ok"] is True
            project2, task2 = reload_task(project2["id"], task2["id"])
            assert task2["executionState"] == "blocked"
            assert "No consensus" in task2["blockedReason"]
        finally:
            server._handle_project_execution_start = old_start
            restore_store(old)
