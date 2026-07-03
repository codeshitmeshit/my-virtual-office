#!/usr/bin/env python3
"""Phase 6 coverage for meeting action items and project task closure."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-phase6-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


def with_store(status_dir):
    old = (
        server.STATUS_DIR,
        server.STATUS_FILE,
        server.WORKFLOW_STATE_FILE,
        server.PROJECT_STORE,
        dict(server._WORKFLOW_STATE),
    )
    server.STATUS_DIR = status_dir
    server.STATUS_FILE = os.path.join(status_dir, "virtual-office-status.json")
    server.WORKFLOW_STATE_FILE = os.path.join(status_dir, "workflow-state.json")
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    with server._WORKFLOW_LOCK:
        server._WORKFLOW_STATE.clear()
    return old


def restore_store(old):
    server.STATUS_DIR, server.STATUS_FILE, server.WORKFLOW_STATE_FILE, server.PROJECT_STORE, workflow_state = old
    with server._WORKFLOW_LOCK:
        server._WORKFLOW_STATE.clear()
        server._WORKFLOW_STATE.update(workflow_state)


def create_project(title="Phase 6 Project"):
    return server._handle_project_create({"title": title, "createdBy": "tester"})["project"]


def create_project_task(project):
    return server._handle_task_create(project["id"], {
        "title": "Source task",
        "description": "Task that requested the meeting.",
        "assignee": "codex",
    })["task"]


def create_completed_task_meeting(project_id="", task_id=""):
    created = server._handle_executable_meeting_create({
        "topic": "Phase 6 Task Meeting",
        "purpose": "Turn meeting output into project tasks.",
        "meetingType": "task",
        "participants": ["codex", "hermes"],
        "moderator": "codex",
        "projectId": project_id,
        "source": {"projectId": project_id, "taskId": task_id, "meetingRequestId": "req-phase6"} if project_id and task_id else {},
        "allowConflicts": True,
        "idempotencyKey": "phase6-meeting",
    })["meeting"]
    opened = server._handle_executable_meeting_transition(created["id"], {
        "stage": "active_opening",
        "expectedVersion": created["version"],
        "idempotencyKey": "phase6-open",
    })["meeting"]
    summarizing = server._handle_executable_meeting_transition(created["id"], {
        "stage": "summarizing",
        "expectedVersion": opened["version"],
        "idempotencyKey": "phase6-summarize",
    })["meeting"]
    completed = server._handle_executable_meeting_transition(created["id"], {
        "stage": "completed",
        "expectedVersion": summarizing["version"],
        "summary": "The team agreed on follow-up tasks.",
        "result": {
            "summary": "The team agreed on follow-up tasks.",
            "decision": "Create project work items.",
            "actionItems": [
                {"title": "Implement action item bridge", "description": "Wire meeting results to task drafts.", "owner": "codex"},
                "Document the workflow",
            ],
        },
        "idempotencyKey": "phase6-complete",
    })
    return completed["meeting"]


def fake_feishu_sender(calls):
    def _send(intent, **kwargs):
        calls.append({"intent": intent, "kwargs": kwargs})
        return {"ok": True, "status": "sent", "channel": "test", "record": {"id": intent.get("id")}}
    return _send


def test_phase6_project_bound_meeting_adds_action_to_source_task_without_backlog():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        try:
            project = create_project()
            source_task = create_project_task(project)
            meeting = create_completed_task_meeting(project["id"], source_task["id"])
            assert not [c for c in feishu_calls if c["intent"]["target"] == "feishu-meeting-failure"]
            assert meeting["projectId"] == project["id"]
            drafts = meeting["actionItemDrafts"]
            assert len(drafts) == 2
            assert drafts[0]["status"] == "draft"
            assert drafts[0]["targetProjectId"] == project["id"]
            assert len(server._handle_project_get(project["id"])["project"]["tasks"]) == 1

            confirmed = server._handle_executable_meeting_action_item(meeting["id"], drafts[0]["id"], {
                "action": "confirm",
                "idempotencyKey": "confirm-once",
            })
            assert confirmed["ok"] is True
            task = confirmed["task"]
            assert task["id"] == source_task["id"]
            assert confirmed["meetingActionItem"]["meetingId"] == meeting["id"]
            assert confirmed["meetingActionItem"]["sourceActionItemId"] == drafts[0]["id"]

            project_after = server._handle_project_get(project["id"])["project"]
            assert len(project_after["tasks"]) == 1
            assert project_after["tasks"][0]["id"] == source_task["id"]
            assert project_after["tasks"][0]["meetingActionItems"][0]["status"] == "pending"
        finally:
            server.send_feishu_notification = old_send
            restore_store(old)


def test_phase6_moderator_failure_sends_feishu_notification_once():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_send = server.send_feishu_notification
        old_call = server._meeting_call_provider
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        server._meeting_call_provider = lambda meeting, speaker, prompt: {
            "ok": False,
            "reply": "password=hunter2 moderator failed",
            "error": "password=hunter2 moderator failed",
            "durationMs": 10,
        }
        try:
            created = server._handle_executable_meeting_create({
                "topic": "Failing moderator meeting",
                "purpose": "Exercise moderator failure notification.",
                "meetingType": "discussion",
                "participants": ["codex", "hermes"],
                "moderator": "codex",
                "allowConflicts": True,
                "idempotencyKey": "phase6-moderator-failure",
            })["meeting"]
            opened = server._handle_executable_meeting_transition(created["id"], {
                "stage": "active_opening",
                "expectedVersion": created["version"],
                "idempotencyKey": "phase6-failure-open",
            })["meeting"]
            summarizing = server._handle_executable_meeting_transition(created["id"], {
                "stage": "summarizing",
                "expectedVersion": opened["version"],
                "idempotencyKey": "phase6-failure-summarize",
            })["meeting"]
            result = server._handle_executable_meeting_end_with_moderator(summarizing["id"])
            assert result["ok"] is False
            failure_calls = [c for c in feishu_calls if c["intent"]["target"] == "feishu-meeting-failure"]
            assert len(failure_calls) == 1
            assert failure_calls[0]["intent"]["type"] == "error"
            assert failure_calls[0]["intent"]["actions"][0]["url"].startswith("http://")
            assert "/#meeting=" in failure_calls[0]["intent"]["actions"][0]["url"]
            assert "hunter2" not in str(failure_calls[0]["intent"])
            duplicate = server._send_meeting_failure_notification(result["meeting"], result["moderatorFailure"])
            assert duplicate["status"] == "skipped_duplicate"
            assert len([c for c in feishu_calls if c["intent"]["target"] == "feishu-meeting-failure"]) == 1
        finally:
            server._meeting_call_provider = old_call
            server.send_feishu_notification = old_send
            restore_store(old)


def test_phase6_direct_meeting_rejects_missing_project_id():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            missing = server._handle_executable_meeting_create({
                "topic": "Missing project meeting",
                "purpose": "Should not silently unbind.",
                "meetingType": "task",
                "participants": ["codex", "hermes"],
                "moderator": "codex",
                "projectId": "missing-project-id",
                "idempotencyKey": "missing-project-meeting",
            })
            assert missing["_status"] == 404
            assert missing["code"] == "project_not_found"

            project = create_project("Existing Project")
            created = server._handle_executable_meeting_create({
                "topic": "Existing project meeting",
                "purpose": "Should bind to the project.",
                "meetingType": "task",
                "participants": ["codex", "hermes"],
                "moderator": "codex",
                "projectId": project["id"],
                "idempotencyKey": "existing-project-meeting",
            })
            assert created["ok"] is True
            assert created["meeting"]["projectId"] == project["id"]
            assert created["meeting"]["projectTitle"] == "Existing Project"
        finally:
            restore_store(old)


def test_phase6_unbound_meeting_requires_target_project_or_keep():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            meeting = create_completed_task_meeting("")
            draft = meeting["actionItemDrafts"][0]
            denied = server._handle_executable_meeting_action_item(meeting["id"], draft["id"], {
                "action": "confirm",
                "idempotencyKey": "missing-project",
            })
            assert denied["_status"] == 400
            assert denied["code"] == "source_task_required"

            kept = server._handle_executable_meeting_action_item(meeting["id"], draft["id"], {
                "action": "keep",
                "idempotencyKey": "keep-only",
            })
            assert kept["actionItem"]["status"] == "kept_as_meeting_item"
        finally:
            restore_store(old)


def test_phase6_edit_reject_and_confirm_are_idempotent():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project = create_project()
            source_task = create_project_task(project)
            meeting = create_completed_task_meeting(project["id"], source_task["id"])
            first, second = meeting["actionItemDrafts"]

            updated = server._handle_executable_meeting_action_item(meeting["id"], first["id"], {
                "action": "update",
                "title": "Edited action item title",
                "priority": "high",
                "idempotencyKey": "edit-first",
            })
            assert updated["actionItem"]["title"] == "Edited action item title"
            assert updated["actionItem"]["priority"] == "high"
            assert updated["actionItem"]["audit"][-1]["action"] == "update"

            rejected = server._handle_executable_meeting_action_item(meeting["id"], second["id"], {
                "action": "reject",
                "reason": "Not needed",
                "idempotencyKey": "reject-second",
            })
            assert rejected["actionItem"]["status"] == "rejected"

            confirmed = server._handle_executable_meeting_action_item(meeting["id"], first["id"], {
                "action": "confirm",
                "idempotencyKey": "confirm-edit",
            })
            repeated = server._handle_executable_meeting_action_item(meeting["id"], first["id"], {
                "action": "confirm",
                "idempotencyKey": "confirm-edit",
            })
            assert repeated["idempotent"] is True
            assert repeated["taskId"] == confirmed["taskId"]
            project_after = server._handle_project_get(project["id"])["project"]
            assert len(project_after["tasks"]) == 1
            assert project_after["tasks"][0]["meetingActionItems"][0]["title"] == "Edited action item title"
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_phase6_project_bound_meeting_adds_action_to_source_task_without_backlog()
    test_phase6_moderator_failure_sends_feishu_notification_once()
    test_phase6_unbound_meeting_requires_target_project_or_keep()
    test_phase6_edit_reject_and_confirm_are_idempotent()
    print("test_meeting_for_ai_phase6.py passed")
