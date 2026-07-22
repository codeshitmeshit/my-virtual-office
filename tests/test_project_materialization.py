#!/usr/bin/env python3
"""Unit contracts for pure canonical Project materialization."""

from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_materialization import (
    CANONICAL_PROJECT_BASE_FIELDS,
    materialize_columns,
    materialize_project_base,
)


NOW = "2026-07-23T08:00:00+00:00"


def _ids(*values: str):
    iterator = iter(values)
    return lambda: next(iterator)


def test_materialize_columns_uses_canonical_four_column_fallback():
    columns, source_map = materialize_columns([], new_id=_ids("c1", "c2", "c3", "c4"))

    assert columns == [
        {"id": "c1", "title": "Backlog", "color": "#6c757d", "order": 0},
        {"id": "c2", "title": "In Progress", "color": "#ffc107", "order": 1},
        {"id": "c3", "title": "Review", "color": "#fd7e14", "order": 2},
        {"id": "c4", "title": "Done", "color": "#198754", "order": 3},
    ]
    assert source_map == {0: "c1", 1: "c2", 2: "c3", 3: "c4"}


def test_materialize_columns_copies_custom_columns_and_maps_fresh_ids():
    source = [
        {
            "id": "source-backlog",
            "title": " Backlog ",
            "color": "#111111",
            "order": 7,
            "policy": {"limit": 2},
        },
        {"id": "ignored", "title": "  "},
        {"title": "Ship", "order": 9},
    ]
    original = copy.deepcopy(source)

    columns, source_map = materialize_columns(
        source,
        new_id=_ids("fresh-1", "fresh-2"),
        preserve_ids=False,
    )

    assert columns == [
        {
            "id": "fresh-1",
            "title": "Backlog",
            "color": "#111111",
            "order": 7,
            "policy": {"limit": 2},
        },
        {"id": "fresh-2", "title": "Ship", "color": "#6c757d", "order": 9},
    ]
    assert source_map == {0: "fresh-1", "source-backlog": "fresh-1", 2: "fresh-2"}
    assert source == original
    source[0]["policy"]["limit"] = 99
    assert columns[0]["policy"] == {"limit": 2}


def test_materialize_columns_preserves_valid_ids_without_calling_factory():
    columns, source_map = materialize_columns(
        [{"id": "todo", "title": "To Do", "color": "#123456", "order": 4}],
        new_id=lambda: (_ for _ in ()).throw(AssertionError("ID factory called")),
    )

    assert columns == [{"id": "todo", "title": "To Do", "color": "#123456", "order": 4}]
    assert source_map == {0: "todo", "todo": "todo"}


def test_materialize_project_base_supplies_complete_canonical_defaults():
    columns, _ = materialize_columns(None, new_id=_ids("c1", "c2", "c3", "c4"))
    project = materialize_project_base(
        {"title": " Canonical Project "},
        columns=columns,
        tasks=None,
        workspace=None,
        new_id=_ids("project-1"),
        now=lambda: NOW,
    )

    assert set(project) == CANONICAL_PROJECT_BASE_FIELDS
    assert project == {
        "id": "project-1",
        "title": "Canonical Project",
        "description": "",
        "projectType": "one_time",
        "status": "active",
        "priority": "medium",
        "createdAt": NOW,
        "updatedAt": NOW,
        "dueDate": None,
        "createdBy": "user",
        "tags": [],
        "branch": "",
        "longTermProject": False,
        "highPriorityAiMeetingAutoApprove": False,
        "archiveMaintenanceEnabled": False,
        "archiveMaintenance": {
            "enabled": False,
            "explicit": False,
            "updatedAt": NOW,
            "updatedBy": "user",
        },
        "projectExecutionEnabled": False,
        "workspacePath": None,
        "workspaceKind": None,
        "workspaceStatus": {},
        "workspaceManagedBy": None,
        "workspaceCreatedAt": None,
        "defaultExecutorAgentId": None,
        "defaultReviewerAgentId": None,
        "projectExecutionStartMode": "continuous",
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": None,
        "scheduledCronPaused": False,
        "executionPolicy": {"maxActiveTasks": 1},
        "executionDirtyConfirmations": [],
        "workflowActive": False,
        "workflowPhase": "idle",
        "activeTaskId": None,
        "activeAgent": None,
        "columns": columns,
        "tasks": [],
        "activity": [],
        "template": False,
    }


def test_materialize_project_base_uses_resolved_values_and_copies_mutables():
    configuration = {
        "title": "Configured",
        "description": {"rich": ["text"]},
        "projectType": "recurring",
        "status": "paused",
        "priority": "high",
        "dueDate": "2026-08-01",
        "createdBy": "author",
        "tags": ["one"],
        "branch": "feature/materializer",
        "longTermProject": True,
        "highPriorityAiMeetingAutoApprove": True,
        "projectExecutionEnabled": False,
        "defaultExecutorAgentId": "builder",
        "defaultReviewerAgentId": "reviewer",
        "projectExecutionStartMode": "single_task",
        "scheduledCronPaused": True,
        "executionPolicy": {"maxActiveTasks": 2, "gates": ["review"]},
    }
    columns = [{"id": "column-1", "title": "Backlog", "metadata": {"lane": 1}}]
    tasks = [{"id": "task-1", "title": "Build", "checklist": [{"text": "done"}]}]
    workspace = {
        "projectExecutionEnabled": True,
        "workspacePath": "/workspace/project",
        "workspaceKind": "directory",
        "workspaceStatus": {"ok": True, "details": ["ready"]},
        "workspaceManagedBy": "system",
        "workspaceCreatedAt": "2026-07-23T07:59:00+00:00",
    }
    originals = copy.deepcopy((configuration, columns, tasks, workspace))

    project = materialize_project_base(
        configuration,
        columns=columns,
        tasks=tasks,
        workspace=workspace,
        project_id="deterministic-project",
        timestamp=NOW,
        new_id=lambda: (_ for _ in ()).throw(AssertionError("ID factory called")),
        now=lambda: (_ for _ in ()).throw(AssertionError("clock called")),
        archive_maintenance_enabled=True,
        archive_maintenance_explicit=True,
        archive_maintenance_updated_by="operator",
    )

    assert project["id"] == "deterministic-project"
    assert project["createdAt"] == project["updatedAt"] == NOW
    assert project["description"] == {"rich": ["text"]}
    assert project["projectType"] == "recurring"
    assert project["status"] == "paused"
    assert project["priority"] == "high"
    assert project["dueDate"] == "2026-08-01"
    assert project["createdBy"] == "author"
    assert project["tags"] == ["one"]
    assert project["branch"] == "feature/materializer"
    assert project["longTermProject"] is True
    assert project["highPriorityAiMeetingAutoApprove"] is True
    assert project["archiveMaintenance"] == {
        "enabled": True,
        "explicit": True,
        "updatedAt": NOW,
        "updatedBy": "operator",
    }
    assert project["projectExecutionEnabled"] is True
    assert project["workspacePath"] == "/workspace/project"
    assert project["workspaceKind"] == "directory"
    assert project["workspaceStatus"] == {"ok": True, "details": ["ready"]}
    assert project["workspaceManagedBy"] == "system"
    assert project["workspaceCreatedAt"] == "2026-07-23T07:59:00+00:00"
    assert project["defaultExecutorAgentId"] == "builder"
    assert project["defaultReviewerAgentId"] == "reviewer"
    assert project["projectExecutionStartMode"] == "single_task"
    assert project["scheduledCronPaused"] is True
    assert project["executionPolicy"] == {"maxActiveTasks": 2, "gates": ["review"]}
    assert (configuration, columns, tasks, workspace) == originals

    configuration["executionPolicy"]["gates"].append("acceptance")
    columns[0]["metadata"]["lane"] = 9
    tasks[0]["checklist"][0]["text"] = "changed"
    workspace["workspaceStatus"]["details"].append("changed")
    assert project["executionPolicy"]["gates"] == ["review"]
    assert project["columns"][0]["metadata"] == {"lane": 1}
    assert project["tasks"][0]["checklist"] == [{"text": "done"}]
    assert project["workspaceStatus"]["details"] == ["ready"]
