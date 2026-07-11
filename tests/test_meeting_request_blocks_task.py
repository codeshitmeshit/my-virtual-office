#!/usr/bin/env python3
"""Meeting requests block Project Execution tasks until resolution."""

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
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-block-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


AGENTS = [
    {"id": "executor", "statusKey": "executor", "providerAgentId": "executor", "providerKind": "openclaw", "name": "Executor"},
    {"id": "reviewer", "statusKey": "reviewer", "providerAgentId": "reviewer", "providerKind": "openclaw", "name": "Reviewer"},
    {"id": "other-agent", "statusKey": "other-agent", "providerAgentId": "other-agent", "providerKind": "openclaw", "name": "Other Agent"},
]


def with_store(status_dir):
    old = (server.STATUS_DIR, server.PROJECT_STORE, server.get_roster)
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    server.get_roster = lambda: AGENTS
    return old


def restore_store(old):
    server.STATUS_DIR, server.PROJECT_STORE, server.get_roster = old


def create_fixture_project(workspace, *, auto_confirm=False):
    project = server._handle_project_create({
        "title": "Meeting Block Fixture",
        "projectExecutionEnabled": True,
        "workspacePath": workspace,
        "defaultExecutorAgentId": "executor",
        "defaultReviewerAgentId": "reviewer",
        "highPriorityAiMeetingAutoApprove": not auto_confirm,
    })["project"]
    validation = server.project_execution_service.validate_workspace(
        project["id"],
        {"workspacePath": workspace},
        load_projects=server._load_projects,
        save_projects=server._save_projects,
        validate_workspace_path=server._project_execution_validate_workspace,
        now=server._proj_now,
    )
    assert validation.status == 200
    assert validation.payload["ok"] is True
    task = server._handle_task_create(project["id"], {"title": "Resolve ambiguity", "columnId": project["columns"][0]["id"], "assignee": "executor"})["task"]
    project, task = reload_task(project["id"], task["id"])
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


def read_feishu_action_records(status_dir):
    path = os.path.join(status_dir, "feishu-card-actions.jsonl")
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def feishu_meeting_action_payload(action, request_id, open_id="ou_feishu_user"):
    return {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger"},
        "event": {
            "operator": {"open_id": open_id},
            "open_message_id": "om_meeting_request",
            "open_chat_id": "oc_meeting_chat",
            "action": {"value": {"action": action, "request_id": request_id}},
        },
    }


def test_feishu_meeting_request_card_actions_confirm_and_reject():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("feishu confirm"))["request"]
            sent_intents = []
            old_send = server.send_feishu_notification
            try:
                def fake_send(intent, **kwargs):
                    sent_intents.append(intent)
                    return {"ok": True, "record": {"type": intent["type"]}}

                server.send_feishu_notification = fake_send
                meeting_notification = server._send_meeting_request_notification(req)
            finally:
                server.send_feishu_notification = old_send
            assert meeting_notification["record"]["type"] == "application_form"
            assert [a["text"] for a in sent_intents[-1]["actions"]] == ["同意", "拒绝", "查看详情"]
            assert sent_intents[-1]["actions"][2]["url"].endswith("/#projects")
            assert sent_intents[-1]["actions"][2]["url"].startswith("http://")

            run_calls = []
            old_run = server._handle_executable_meeting_run
            try:
                def fake_run(meeting_id, body=None):
                    run_calls.append({"meetingId": meeting_id, "body": body or {}})
                    return {"ok": True, "meeting": {"id": meeting_id, "stage": "active_opening"}}

                server._handle_executable_meeting_run = fake_run
                result = server._handle_feishu_card_action(feishu_meeting_action_payload("confirm_meeting_request", req["id"]))
            finally:
                server._handle_executable_meeting_run = old_run
            assert result["ok"] is True
            assert result["toast"]["content"].startswith("会议申请已同意，会议已开始")
            detail = server._handle_meeting_request_detail(req["id"])
            assert detail["request"]["status"] == "confirmed"
            assert detail["request"]["review"]["confirmedBy"] == "ou_feishu_user"
            assert run_calls == [{
                "meetingId": detail["request"]["conversion"]["meetingId"],
                "body": {"action": "start", "actorId": "ou_feishu_user", "actorType": "user"},
            }]

            project2, task2 = create_fixture_project(status_dir)
            req2 = server._handle_meeting_request_create(project2["id"], task2["id"], meeting_request_body("feishu reject"))["request"]
            result2 = server._handle_feishu_card_action(feishu_meeting_action_payload("reject_meeting_request", req2["id"]))
            assert result2["ok"] is True
            assert result2["toast"]["content"].startswith("会议申请已拒绝")
            detail2 = server._handle_meeting_request_detail(req2["id"])
            assert detail2["request"]["status"] == "rejected"
            assert detail2["request"]["review"]["rejectedBy"] == "ou_feishu_user"
            assert detail2["request"]["review"]["rejectionReason"] == "Rejected from Feishu"

            rows = read_feishu_action_records(status_dir)
            outcomes = [row.get("outcome", {}) for row in rows if row.get("requestId") in {req["id"], req2["id"]}]
            assert {o.get("businessStatus") for o in outcomes} >= {"confirmed_started", "rejected"}
            confirmed_outcome = next(o for o in outcomes if o.get("businessStatus") == "confirmed_started")
            assert confirmed_outcome["run"]["ok"] is True
            assert confirmed_outcome["run"]["stage"] == "active_opening"
        finally:
            restore_store(old)


def test_auto_confirmed_meeting_request_pending_notification_is_view_only():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_fixture_project(status_dir, auto_confirm=True)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("auto"))["request"]
            assert req["status"] == "confirmed"
            assert req["review"]["autoConfirmed"] is True

            sent_intents = []
            old_send = server.send_feishu_notification
            try:
                def fake_send(intent, **kwargs):
                    sent_intents.append(intent)
                    return {"ok": True, "record": {"type": intent["type"]}}

                server.send_feishu_notification = fake_send
                notification = server._send_meeting_request_notification(req, "pending")
            finally:
                server.send_feishu_notification = old_send

            assert notification["record"]["type"] == "application_form"
            assert [a["text"] for a in sent_intents[-1]["actions"]] == ["查看会议"]
            assert sent_intents[-1]["actions"][0]["url"].endswith(f"/#meeting={req['conversion']['meetingId']}")
        finally:
            restore_store(old)


def test_feishu_meeting_request_card_actions_reject_invalid_states():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("stale"))["request"]
            confirmed = server._handle_meeting_request_confirm(req["id"], {"confirmedBy": "user"})
            assert confirmed["ok"] is True

            rejected_after_confirm = server._handle_feishu_card_action(feishu_meeting_action_payload("reject_meeting_request", req["id"]))
            assert rejected_after_confirm["ok"] is False
            assert "cannot be rejected" in rejected_after_confirm["toast"]["content"]
            detail = server._handle_meeting_request_detail(req["id"])
            assert detail["request"]["status"] == "confirmed"

            missing = server._handle_feishu_card_action(feishu_meeting_action_payload("confirm_meeting_request", "missing-request"))
            assert missing["ok"] is False
            assert "not found" in missing["toast"]["content"]

            malformed = server._handle_feishu_card_action(feishu_meeting_action_payload("confirm_meeting_request", ""))
            assert malformed["ok"] is False
            assert "request_id" in malformed["toast"]["content"]

            rows = read_feishu_action_records(status_dir)
            statuses = [row.get("outcome", {}).get("businessStatus") for row in rows]
            assert "request_confirmed" in statuses
            assert "request_not_found" in statuses
            assert "missing_request_id" in statuses
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
            assert len(task["meetingRecords"]) == 1
            assert task["meetingRecords"][0]["outcome"] == "approved"
            assert task["meetingRecords"][0]["decision"] == "Consensus reached."
            assert started and started[-1][1] == task["id"]

            project2, task2 = create_fixture_project(status_dir)
            req2 = server._handle_meeting_request_create(project2["id"], task2["id"], meeting_request_body("no consensus"))["request"]
            meeting2 = {"id": "m-no", "projectId": project2["id"], "source": {"meetingRequestId": req2["id"], "projectId": project2["id"], "taskId": task2["id"]}, "stage": "completed", "result": {"outcome": "no_consensus", "decision": "No consensus."}}
            applied2 = server._project_execution_apply_meeting_result(meeting2)
            assert applied2["ok"] is True
            project2, task2 = reload_task(project2["id"], task2["id"])
            assert task2["executionState"] == "blocked"
            assert "No consensus" in task2["blockedReason"]
            assert len(task2["meetingRecords"]) == 1
            assert task2["meetingRecords"][0]["outcome"] == "no_consensus"
            assert task2["meetingRecords"][0]["decision"] == "No consensus."

            project3, task3 = create_fixture_project(status_dir)
            req3 = server._handle_meeting_request_create(project3["id"], task3["id"], meeting_request_body("needs decision"))["request"]
            meeting3 = {"id": "m-user", "projectId": project3["id"], "source": {"meetingRequestId": req3["id"], "projectId": project3["id"], "taskId": task3["id"]}, "stage": "completed", "result": {"outcome": "needs_user_decision", "summary": "User must decide whether to continue."}}
            applied3 = server._project_execution_apply_meeting_result(meeting3)
            assert applied3["ok"] is True
            project3, task3 = reload_task(project3["id"], task3["id"])
            assert task3["executionState"] == "awaiting_meeting_resolution"
            assert task3["meetingRecords"][0]["outcome"] == "needs_user_decision"
            assert task3["meetingRecords"][0]["summary"] == "User must decide whether to continue."
        finally:
            server._handle_project_execution_start = old_start
            restore_store(old)


def test_moderator_user_takeover_applies_project_meeting_result():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_call = server._meeting_call_provider
        old_start = server._handle_project_execution_start
        started = []

        def failing_moderator(meeting, speaker, prompt):
            return {
                "ok": False,
                "reply": "[ERROR] moderator unavailable",
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 1,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        def fake_start(project_id, task_id, body=None):
            started.append((project_id, task_id, body or {}))
            return {"ok": True, "status": "started", "taskId": task_id}

        server._meeting_call_provider = failing_moderator
        server._handle_project_execution_start = fake_start
        try:
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("takeover"))["request"]
            confirmed = server._handle_meeting_request_confirm(req["id"], {"confirmedBy": "user"})
            meeting_id = confirmed["meetingId"]

            server._handle_executable_meeting_transition(meeting_id, {"action": "start"})
            failed = server._handle_meeting_end({"id": meeting_id, "endedBy": "user"})
            assert failed["ok"] is False
            assert failed["meeting"]["stage"] == "awaiting_user_decision"

            takeover = server._handle_executable_meeting_moderator_takeover(meeting_id, {
                "action": "user_takeover",
                "summary": "Manual moderator summary.",
                "decision": "Consensus reached.",
                "result": {"outcome": "approved"},
            })
            assert takeover["ok"] is True
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "backlog"
            assert task["meetingBlocker"]["status"] == "resolved_continue"
            assert task["meetingRecords"][0]["outcome"] == "approved"
            assert started and started[-1][1] == task["id"]
        finally:
            server._handle_project_execution_start = old_start
            server._meeting_call_provider = old_call
            restore_store(old)


def test_moderator_user_takeover_no_consensus_blocks_project_task():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_call = server._meeting_call_provider
        old_start = server._handle_project_execution_start
        started = []

        def failing_moderator(meeting, speaker, prompt):
            return {
                "ok": False,
                "reply": "[ERROR] moderator unavailable",
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 1,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        def fake_start(project_id, task_id, body=None):
            started.append((project_id, task_id, body or {}))
            return {"ok": True, "status": "started", "taskId": task_id}

        server._meeting_call_provider = failing_moderator
        server._handle_project_execution_start = fake_start
        try:
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("takeover no consensus"))["request"]
            confirmed = server._handle_meeting_request_confirm(req["id"], {"confirmedBy": "user"})
            meeting_id = confirmed["meetingId"]

            server._handle_executable_meeting_transition(meeting_id, {"action": "start"})
            failed = server._handle_meeting_end({"id": meeting_id, "endedBy": "user"})
            assert failed["ok"] is False
            assert failed["meeting"]["stage"] == "awaiting_user_decision"

            takeover = server._handle_executable_meeting_moderator_takeover(meeting_id, {
                "action": "user_takeover",
                "summary": "Manual moderator summary.",
                "decision": "No consensus; keep the task blocked.",
                "result": {"outcome": "no_consensus"},
            })
            assert takeover["ok"] is True
            assert takeover["meeting"]["result"]["outcome"] == "no_consensus"
            project, task = reload_task(project["id"], task["id"])
            assert task["executionState"] == "blocked"
            assert task["meetingBlocker"]["status"] == "blocked"
            assert task["meetingRecords"][0]["outcome"] == "no_consensus"
            assert not started
        finally:
            server._handle_project_execution_start = old_start
            server._meeting_call_provider = old_call
            restore_store(old)


def test_approved_meeting_applies_action_items_before_original_task_resumes():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_thread = server.threading.Thread
        old_start = server._handle_project_execution_start
        started = []
        try:
            class SyncThread:
                def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                    self.target = target
                    self.args = args
                    self.kwargs = kwargs or {}
                def start(self):
                    if self.target:
                        self.target(*self.args, **self.kwargs)

            def fake_start(project_id, task_id, body=None):
                started.append((project_id, task_id, body or {}))
                return {"ok": True, "status": "started", "taskId": task_id}

            server.threading.Thread = SyncThread
            server._handle_project_execution_start = fake_start
            project, task = create_fixture_project(status_dir)
            req = server._handle_meeting_request_create(project["id"], task["id"], meeting_request_body("action items"))["request"]
            meeting = {
                "id": "m-actions",
                "projectId": project["id"],
                "source": {"meetingRequestId": req["id"], "projectId": project["id"], "taskId": task["id"]},
                "stage": "completed",
                "result": {
                    "outcome": "approved",
                    "summary": "Consensus reached with follow-up work.",
                    "decision": "Use the smaller API surface.",
                    "actionItems": [
                        {"title": "Update the active implementation plan", "owner": "executor", "priority": None},
                        {"title": "Review copy changes", "owner": "other-agent"},
                    ],
                    "risks": ["Regression around meeting resume order"],
                },
            }

            applied = server._project_execution_apply_meeting_result(meeting)
            assert applied["ok"] is True
            assert applied["appliedMeetingResult"]["applied"] == 2
            assert applied["appliedMeetingResult"]["linked"] == 0
            assert applied["appliedMeetingResult"]["checklistSeeded"] is True
            assert applied["appliedMeetingResult"]["pendingRequired"] is True
            project, task = reload_task(project["id"], task["id"])
            assert len(task["meetingActionItems"]) == 2
            current_item = next(i for i in task["meetingActionItems"] if i["owner"] == "executor")
            delegated_item = next(i for i in task["meetingActionItems"] if i["owner"] == "other-agent")
            assert current_item["status"] == "pending"
            assert current_item["requiredForResume"] is True
            assert current_item["id"].endswith(":action:ai-1")
            assert current_item["priority"] == "medium"
            assert delegated_item["status"] == "pending"
            assert delegated_item["requiredForResume"] is True
            assert delegated_item["id"].endswith(":action:ai-2")
            assert not delegated_item.get("linkedTaskId")
            assert len(project["tasks"]) == 1
            acceptance_items = [c for c in task["checklist"] if c.get("source") == "project_execution_acceptance"]
            assert len(acceptance_items) >= 2
            assert any("完成任务目标" in c.get("text", "") for c in acceptance_items)
            assert not any(c.get("source") == "meeting_action_item" for c in task["checklist"])
            assert not any(c.get("source") == "meeting_risk" for c in task["checklist"])
            assert not any(c.get("source") == "meeting_risk" for c in task["comments"])
            assert any(c.get("kind") == "risk" and "Regression around meeting resume order" in c.get("text", "") for c in task["meetingDiscussionPoints"])
            assert task["meetingDecisionHistory"][0]["decision"] == "Use the smaller API surface."
            assert task["meetingRecords"][0]["actionItemCount"] == 2
            assert task["meetingRecords"][0]["risks"] == ["Regression around meeting resume order"]
            assert started and started[-1][1] == task["id"]

            repeated = server._project_execution_apply_meeting_result(meeting)
            assert repeated["ok"] is True
            assert repeated["appliedMeetingResult"]["checklistSeeded"] is False
            project, task = reload_task(project["id"], task["id"])
            assert len(task["meetingActionItems"]) == 2
            assert len(task["meetingRecords"]) == 1
            assert len([c for c in task["checklist"] if c.get("source") == "project_execution_acceptance"]) == len(acceptance_items)
            assert len([c for c in task["checklist"] if c.get("source") == "meeting_action_item"]) == 0
            assert len([c for c in task["meetingDiscussionPoints"] if c.get("kind") == "risk"]) == 1
        finally:
            server._handle_project_execution_start = old_start
            server.threading.Thread = old_thread
            restore_store(old)


def test_meeting_action_phase_checks_items_then_restarts_original_task():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_thread = server.threading.Thread
        try:
            class SyncThread:
                def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                    self.target = target
                    self.args = args
                    self.kwargs = kwargs or {}
                def start(self):
                    if self.target:
                        self.target(*self.args, **self.kwargs)

            calls = []
            def fake_executor(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
                calls.append({"attemptId": attempt_id, "prompt": prompt})
                return {"ok": True, "reply": "Completed meeting action item.", "status": "completed", "modifiedFiles": []}

            server.threading.Thread = SyncThread
            server._project_execution_call_executor = fake_executor
            project, task = create_fixture_project(status_dir)
            task["meetingActionItems"] = [{
                "id": "meeting:m1:action:a1",
                "meetingId": "m1",
                "requestId": "req1",
                "title": "Apply meeting decision",
                "owner": "executor",
                "status": "pending",
                "requiredForResume": True,
            }]
            task["checklist"] = [{"id": "c1", "text": "Original deliverable remains valid", "done": False}]
            server._save_projects({"projects": [project]})

            first = server._handle_project_execution_start(project["id"], task["id"], {"projectStart": True, "autoReviewAfterExecution": True})
            assert first["ok"] is True
            project, task = reload_task(project["id"], task["id"])
            assert task["meetingActionItems"][0]["status"] == "completed"
            assert task["checklist"][0]["done"] is False
            assert len(calls) >= 2
            assert "MEETING ACTION ITEM PHASE" in calls[0]["prompt"]
            assert "MEETING ACTION ITEM PHASE" not in calls[1]["prompt"]
        finally:
            server._project_execution_call_executor = old_executor
            server.threading.Thread = old_thread
            restore_store(old)
