#!/usr/bin/env python3
"""Project Execution eligibility for typed Agent and human task executors."""

import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-execution-actor-eligibility-")

import server


def _project(tasks):
    return {
        "id": "project-1",
        "defaultExecutorAgentId": "default-agent",
        "columns": [
            {"id": "backlog", "title": "Backlog", "order": 0},
            {"id": "done", "title": "Done", "order": 1},
        ],
        "tasks": tasks,
    }


def _task(task_id, executor, *, responsible=None, order=0):
    return {
        "id": task_id,
        "title": task_id,
        "columnId": "backlog",
        "order": order,
        "executionState": "backlog",
        "assignee": (responsible or {}).get("id"),
        "responsibleActor": responsible,
        "executorActor": executor,
    }


def test_human_executor_remains_trackable_but_direct_automation_is_rejected(monkeypatch):
    monkeypatch.setattr(server, "_office_agent_lookup", lambda agent_id: {"id": agent_id} if agent_id else None)
    human_task = _task(
        "human-task",
        {"type": "user", "id": "user:local"},
        responsible={"type": "agent", "id": "responsible-agent"},
    )
    project = _project([human_task])

    roles = server._project_execution_resolve_start_roles(project, human_task, allow_skip_reviewer=True)

    assert roles["ok"] is False
    assert roles["code"] == "executor_required"
    assert server._project_execution_next_task(project)["id"] == "human-task"
    assert project["tasks"] == [human_task]
    assert human_task["executionState"] == "backlog"


def test_hybrid_project_keeps_lower_order_human_task_before_agent_task(monkeypatch):
    registered = {"builder": {"id": "builder"}}
    monkeypatch.setattr(server, "_office_agent_lookup", registered.get)
    human_task = _task(
        "human-task",
        {"type": "user", "id": "user:local"},
        responsible={"type": "agent", "id": "responsible-agent"},
        order=0,
    )
    agent_task = _task(
        "agent-task",
        {"type": "agent", "id": "builder"},
        responsible={"type": "user", "id": "user:local"},
        order=1,
    )
    project = _project([human_task, agent_task])

    selected = server._project_execution_next_task(project)

    assert selected["id"] == "human-task"
    assert human_task["executionState"] == "backlog"


def test_agent_executor_is_not_overridden_by_human_responsible_actor(monkeypatch):
    monkeypatch.setattr(server, "_office_agent_lookup", lambda agent_id: {"id": agent_id} if agent_id == "builder" else None)
    task = _task(
        "agent-task",
        {"type": "agent", "id": "builder"},
        responsible={"type": "user", "id": "user:local"},
    )
    project = _project([task])

    assert server._project_execution_executor_agent_id(project, task) == "builder"
    assert server._project_execution_next_task(project)["id"] == "agent-task"
