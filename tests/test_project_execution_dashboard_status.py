#!/usr/bin/env python3
"""Project Execution visibility in dashboard/sidebar summaries."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-project-dashboard-status-")
os.environ["VO_OPENCLAW_PATH"] = tempfile.mkdtemp(prefix="vo-project-dashboard-openclaw-")

import server


def fake_project():
    return {
        "id": "p-1",
        "title": "高仿测试",
        "status": "active",
        "priority": "medium",
        "projectExecutionEnabled": True,
        "workflowActive": True,
        "workflowPhase": "executing",
        "activeTaskId": "t-1",
        "activeAgent": "codex-local",
        "tasks": [
            {
                "id": "t-1",
                "title": "实现验收项",
                "executionState": "executing",
                "activeAttemptId": "a-1",
                "assignee": "codex-local",
                "executorAgentId": "codex-local",
                "reviewerAgentId": "claude-code-local",
            }
        ],
        "columns": [],
    }


def install_project_fixture(project):
    old_load = server._load_projects
    old_roster = server.get_roster
    server._load_projects = lambda: {"projects": [project]}
    server.get_roster = lambda: [
        {
            "id": "codex-local",
            "statusKey": "codex-local",
            "providerAgentId": "local",
            "providerKind": "codex",
            "name": "Codex",
        },
        {
            "id": "claude-code-local",
            "statusKey": "claude-code-local",
            "providerAgentId": "local",
            "providerKind": "claude-code",
            "name": "Claude Code",
        },
    ]
    return old_load, old_roster


def restore_project_fixture(old):
    server._load_projects, server.get_roster = old


def test_project_execution_merges_agent_presence_as_working():
    old = install_project_fixture(fake_project())
    try:
        state = {
            "codex-local": {"state": "idle", "task": "", "updated": 1, "source": "snapshot"},
            "_meetings": [],
        }
        server._merge_project_execution_presence(state)

        assert state["codex-local"]["state"] == "working"
        assert state["codex-local"]["source"] == "project-execution"
        assert state["codex-local"]["projectId"] == "p-1"
        assert "高仿测试" in state["codex-local"]["task"]
        assert "实现验收项" in state["codex-local"]["task"]
    finally:
        restore_project_fixture(old)


def test_project_execution_presence_uses_project_active_agent_when_task_state_lags():
    project = fake_project()
    project["workflowPhase"] = "executing"
    project["activeAgent"] = "codex-local"
    project["tasks"][0]["executionState"] = "backlog"
    project["tasks"][0]["executorAgentId"] = ""
    project["tasks"][0]["assignee"] = ""
    old = install_project_fixture(project)
    try:
        state = {
            "codex-local": {"state": "idle", "task": "", "updated": 1, "source": "snapshot"},
            "_meetings": [],
        }
        server._merge_project_execution_presence(state)

        assert state["codex-local"]["state"] == "working"
        assert state["codex-local"]["source"] == "project-execution"
        assert state["codex-local"]["projectExecutionState"] == "executing"
        assert "实现验收项" in state["codex-local"]["task"]
    finally:
        restore_project_fixture(old)


def test_project_execution_presence_does_not_mark_waiting_user_acceptance_as_working():
    project = fake_project()
    project["workflowPhase"] = "awaiting_user_acceptance"
    project["activeAgent"] = "codex-local"
    project["tasks"][0]["executionState"] = "awaiting_user_acceptance"
    old = install_project_fixture(project)
    try:
        state = {
            "codex-local": {"state": "idle", "task": "", "updated": 1, "source": "snapshot"},
            "_meetings": [],
        }
        server._merge_project_execution_presence(state)

        assert state["codex-local"]["state"] == "idle"
        assert state["codex-local"]["source"] == "snapshot"
    finally:
        restore_project_fixture(old)


def test_project_list_summary_exposes_active_execution():
    old = install_project_fixture(fake_project())
    try:
        result = server._handle_projects_list("status=active")
        summary = result["projects"][0]

        assert summary["projectExecutionActive"] is True
        assert summary["projectExecutionPhase"] == "executing"
        assert summary["activeTaskId"] == "t-1"
        assert summary["activeTaskTitle"] == "实现验收项"
        assert summary["activeAgent"] == "codex-local"
        assert summary["activeTaskCount"] == 1
    finally:
        restore_project_fixture(old)


def test_project_list_summary_counts_execution_state_done_tasks():
    project = fake_project()
    project["workflowActive"] = False
    project["workflowPhase"] = "idle"
    project["activeTaskId"] = ""
    project["activeAgent"] = ""
    project["tasks"] = [
        {
            "id": "t-1",
            "title": "已完成但没有 completedAt",
            "executionState": "done",
            "completedAt": None,
        },
        {
            "id": "t-2",
            "title": "仍在执行",
            "executionState": "executing",
            "executorAgentId": "codex-local",
            "activeAttemptId": "a-2",
        },
    ]
    old = install_project_fixture(project)
    try:
        result = server._handle_projects_list("status=active")
        summary = result["projects"][0]

        assert summary["taskCount"] == 2
        assert summary["taskDone"] == 1
        assert summary["projectExecutionActive"] is True
        assert summary["activeTaskTitle"] == "仍在执行"
    finally:
        restore_project_fixture(old)
