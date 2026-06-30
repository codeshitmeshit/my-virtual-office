#!/usr/bin/env python3
"""Agent workspace project context is read-only and sourced from projects."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-agent-workspace-context-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


AGENTS = [
    {"id": "executor", "statusKey": "executor", "providerAgentId": "executor", "providerKind": "openclaw", "name": "Executor"},
    {"id": "reviewer", "statusKey": "reviewer", "providerAgentId": "reviewer", "providerKind": "openclaw", "name": "Reviewer"},
]


def with_store(status_dir):
    old = (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.AGENT_WORKSPACES_FILE,
        server.get_roster,
    )
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    server.AGENT_WORKSPACES_FILE = os.path.join(status_dir, "agent-workspaces.json")
    server.get_roster = lambda: AGENTS
    server.refresh_agent_maps()
    return old


def restore_store(old):
    server.STATUS_DIR, server.PROJECT_STORE, server.AGENT_WORKSPACES_FILE, server.get_roster = old
    server.refresh_agent_maps()


def test_agent_workspace_project_context_is_read_only_snapshot():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project = server._handle_project_create({
                "title": "Workspace Context",
                "projectExecutionEnabled": True,
                "workspacePath": status_dir,
                "defaultExecutorAgentId": "executor",
                "defaultReviewerAgentId": "reviewer",
            })["project"]
            task = server._handle_task_create(project["id"], {
                "title": "Implement read-only projection",
                "description": "Surface project context in the agent workspace.",
                "columnId": project["columns"][0]["id"],
                "assignee": "executor",
                "executorAgentId": "executor",
                "reviewerAgentId": "reviewer",
                "priority": "high",
                "scheduledRepeatEnabled": True,
            })["task"]
            blocked = server._project_execution_block_for_meeting_request(project["id"], task["id"], {
                "id": "req-readonly",
                "status": "pending",
                "requestingAgentId": "executor",
                "createdAt": "2026-01-01T00:00:00+00:00",
                "conversion": {"meetingId": "meeting-readonly"},
            }, reason="Read-only projection fixture")
            assert blocked["ok"] is True

            executor_payload = server._get_agent_workspace_payload("executor")
            assert executor_payload["ok"] is True
            items = executor_payload["projectTasks"]
            assert len(items) == 1
            item = items[0]
            assert item["readOnly"] is True
            assert item["projectId"] == project["id"]
            assert item["taskId"] == task["id"]
            assert item["id"] == task["id"]
            assert item["projectExecutionEnabled"] is True
            assert item["role"] == "executor"
            assert item["executionState"] == "awaiting_meeting_resolution"
            assert item["meetingBlocker"]["status"] == "pending"
            assert item["meetingBlocker"]["requestId"] == "req-readonly"
            assert item["meetingBlocker"]["meetingId"] == "meeting-readonly"
            assert item["scheduledRepeatEnabled"] is True
            assert item["activeAttemptId"] == ""
            assert "actions" not in item

            reviewer_payload = server._get_agent_workspace_payload("reviewer")
            assert reviewer_payload["ok"] is True
            assert reviewer_payload["projectTasks"][0]["role"] == "reviewer"
            assert reviewer_payload["projectTasks"][0]["taskId"] == task["id"]
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_agent_workspace_project_context_is_read_only_snapshot()
    print("test_agent_workspace_project_context.py passed")
