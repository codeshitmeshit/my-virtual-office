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
    CANONICAL_TASK_BASE_FIELDS,
    MAX_CHECKLIST_ITEMS,
    PreparedWorkspace,
    apply_authoring_overlay,
    apply_manual_overlay,
    apply_recurrence_overlay,
    apply_template_overlay,
    materialize_columns,
    materialize_checklist,
    materialize_project_base,
    materialize_task_base,
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


def test_materialize_checklist_normalizes_text_ids_collisions_and_evidence():
    source = [
        "  Verify   output  ",
        {"text": "verify output", "done": True, "evidence": {"tests": ["pass"]}},
        {"id": "manual", "text": " Ship it ", "done": 1},
        {"id": "manual", "text": "Document it", "done": False},
        {"id": "blank", "text": "  "},
        42,
    ]
    original = copy.deepcopy(source)

    checklist = materialize_checklist(source)

    generated_id = checklist[0]["id"]
    assert generated_id.startswith("checklist-")
    assert checklist == [
        {"id": generated_id, "text": "Verify output", "done": False},
        {
            "id": generated_id + "-2",
            "text": "verify output",
            "done": True,
            "evidence": {"tests": ["pass"]},
        },
        {"id": "manual", "text": "Ship it", "done": False},
        {"id": "manual-2", "text": "Document it", "done": False},
    ]
    assert materialize_checklist(original) == checklist
    assert source == original
    source[1]["evidence"]["tests"].append("changed")
    assert checklist[1]["evidence"] == {"tests": ["pass"]}


def test_materialize_checklist_rejects_invalid_or_oversized_containers():
    for invalid in ("one item", {"text": "one item"}, 3):
        try:
            materialize_checklist(invalid)
        except ValueError as exc:
            assert "checklist must be a list" in str(exc)
        else:
            raise AssertionError(f"expected ValueError for {invalid!r}")

    try:
        materialize_checklist(["item"] * (MAX_CHECKLIST_ITEMS + 1))
    except ValueError as exc:
        assert str(MAX_CHECKLIST_ITEMS) in str(exc)
    else:
        raise AssertionError("expected ValueError for oversized checklist")

    assert len(materialize_checklist(["item"] * MAX_CHECKLIST_ITEMS)) == MAX_CHECKLIST_ITEMS


def test_materialize_task_base_supplies_complete_defaults_and_backlog_fallback():
    columns = [
        {"id": "doing", "title": "In Progress"},
        {"id": "backlog", "title": "Backlog"},
    ]
    task = materialize_task_base(
        {"title": " Canonical Task ", "columnId": "missing"},
        columns=columns,
        new_id=_ids("task-1"),
        now=lambda: NOW,
    )

    assert set(task) == CANONICAL_TASK_BASE_FIELDS
    assert task == {
        "id": "task-1",
        "title": "Canonical Task",
        "description": "",
        "columnId": "backlog",
        "order": 0,
        "executionOrder": 1,
        "priority": "medium",
        "responsibleActor": None,
        "executorActor": None,
        "reviewerActor": None,
        "reviewerRecommendation": {},
        "assignee": None,
        "assigneeBranch": None,
        "executorAgentId": None,
        "reviewerAgentId": None,
        "requiresUserAcceptance": False,
        "allowReviewerlessExecution": False,
        "scheduledRepeatEnabled": False,
        "executionState": "backlog",
        "activeAttemptId": None,
        "attempts": [],
        "evidence": {},
        "blockedReason": None,
        "lastError": None,
        "dueDate": None,
        "tags": [],
        "checklist": [],
        "meetingActionItems": [],
        "meetingDecisionHistory": [],
        "meetingDiscussionPoints": [],
        "meetingRecords": [],
        "source": {},
        "comments": [],
        "attachments": [],
        "createdAt": NOW,
        "updatedAt": NOW,
        "completedAt": None,
    }


def test_materialize_task_base_preserves_resolved_values_and_copies_mutables():
    configuration = {
        "id": "configured-id",
        "title": "Build",
        "description": {"rich": ["description"]},
        "columnId": "review",
        "order": 8,
        "executionOrder": 4,
        "priority": "critical",
        "responsibleActor": {"kind": "agent", "id": "owner"},
        "executorActor": {"kind": "agent", "id": "builder"},
        "reviewerActor": {"kind": "agent", "id": "reviewer"},
        "reviewerRecommendation": {"reason": ["quality"]},
        "assignee": "owner",
        "assigneeBranch": "feature/task",
        "executorAgentId": "builder",
        "reviewerAgentId": "reviewer",
        "requiresUserAcceptance": True,
        "allowReviewerlessExecution": True,
        "scheduledRepeatEnabled": True,
        "evidence": {"seed": ["confirmed"]},
        "dueDate": "2026-08-02",
        "tags": ["task"],
        "checklist": [{"id": "accept", "text": "Accepted", "evidence": ["spec"]}],
        "meetingActionItems": [{"id": "action"}],
        "meetingDecisionHistory": [{"id": "decision"}],
        "meetingDiscussionPoints": [{"id": "point"}],
        "meetingRecords": [{"id": "record"}],
        "source": {"kind": "template", "path": ["snapshot"]},
    }
    original = copy.deepcopy(configuration)

    task = materialize_task_base(
        configuration,
        columns=[{"id": "review", "title": "Review"}],
        new_id=lambda: (_ for _ in ()).throw(AssertionError("ID factory called")),
        now=lambda: (_ for _ in ()).throw(AssertionError("clock called")),
        task_id="deterministic-task",
        timestamp=NOW,
        order=3,
    )

    assert task["id"] == "deterministic-task"
    assert task["columnId"] == "review"
    assert task["order"] == 3
    assert task["executionOrder"] == 4
    assert task["priority"] == "critical"
    assert task["responsibleActor"] == {"kind": "agent", "id": "owner"}
    assert task["executorActor"] == {"kind": "agent", "id": "builder"}
    assert task["reviewerActor"] == {"kind": "agent", "id": "reviewer"}
    assert task["reviewerRecommendation"] == {"reason": ["quality"]}
    assert task["assignee"] == "owner"
    assert task["assigneeBranch"] == "feature/task"
    assert task["executorAgentId"] == "builder"
    assert task["reviewerAgentId"] == "reviewer"
    assert task["requiresUserAcceptance"] is True
    assert task["allowReviewerlessExecution"] is True
    assert task["scheduledRepeatEnabled"] is True
    assert task["evidence"] == {"seed": ["confirmed"]}
    assert task["tags"] == ["task"]
    assert task["checklist"] == [
        {"id": "accept", "text": "Accepted", "done": False, "evidence": ["spec"]}
    ]
    assert task["meetingActionItems"] == [{"id": "action"}]
    assert task["meetingDecisionHistory"] == [{"id": "decision"}]
    assert task["meetingDiscussionPoints"] == [{"id": "point"}]
    assert task["meetingRecords"] == [{"id": "record"}]
    assert task["source"] == {"kind": "template", "path": ["snapshot"]}
    assert task["createdAt"] == task["updatedAt"] == NOW
    assert configuration == original

    configuration["reviewerRecommendation"]["reason"].append("changed")
    configuration["evidence"]["seed"].append("changed")
    configuration["meetingRecords"][0]["id"] = "changed"
    configuration["source"]["path"].append("changed")
    assert task["reviewerRecommendation"] == {"reason": ["quality"]}
    assert task["evidence"] == {"seed": ["confirmed"]}
    assert task["meetingRecords"] == [{"id": "record"}]
    assert task["source"] == {"kind": "template", "path": ["snapshot"]}


def test_materialize_task_base_falls_back_to_first_column_or_none():
    first = materialize_task_base(
        {"title": "First fallback", "columnId": "missing"},
        columns=[{"id": "first", "title": "Ideas"}, {"id": "second", "title": "Done"}],
        new_id=_ids("task-first"),
        now=lambda: NOW,
    )
    empty = materialize_task_base(
        {"title": "No column"},
        columns=[],
        new_id=_ids("task-empty"),
        now=lambda: NOW,
    )

    assert first["columnId"] == "first"
    assert empty["columnId"] is None


def test_materialize_task_base_computes_next_order_after_column_fallback():
    task = materialize_task_base(
        {"title": "Fallback order", "columnId": "missing"},
        columns=[{"id": "backlog", "title": "Backlog"}, {"id": "done", "title": "Done"}],
        existing_tasks=[
            {"columnId": "backlog", "order": 1, "executionOrder": 1},
            {"columnId": "done", "order": 8, "executionOrder": 2},
            {"columnId": "backlog", "order": 4, "executionOrder": 3},
        ],
        new_id=_ids("ordered-task"),
        now=lambda: NOW,
    )

    assert task["columnId"] == "backlog"
    assert task["order"] == 5
    assert task["executionOrder"] == 4


def _overlay_base() -> dict:
    columns, _ = materialize_columns(None, new_id=_ids("c1", "c2", "c3", "c4"))
    return materialize_project_base(
        {"title": "Overlay Base", "createdBy": "actor"},
        columns=columns,
        tasks=[],
        workspace=None,
        project_id="overlay-project",
        timestamp=NOW,
        new_id=lambda: (_ for _ in ()).throw(AssertionError("ID factory called")),
        now=lambda: (_ for _ in ()).throw(AssertionError("clock called")),
    )


def _assert_overlay_preserves_base(base: dict, overlaid: dict):
    assert set(CANONICAL_PROJECT_BASE_FIELDS) <= set(overlaid)
    for field in CANONICAL_PROJECT_BASE_FIELDS - {"activity"}:
        assert overlaid[field] == base[field], field
    assert base["activity"] == []
    assert len(overlaid["activity"]) == 1


def test_source_overlays_only_add_owned_metadata_and_activity():
    base = _overlay_base()
    original = copy.deepcopy(base)

    manual = apply_manual_overlay(base, actor="user", timestamp=NOW)
    authored = apply_authoring_overlay(
        base,
        actor="author",
        request_id="request-1",
        timestamp=NOW,
        maintenance_mode="strict_confirmation",
        template_ref={"id": "template-1", "version": 2},
        recurrence_ref={"id": "recurrence-1"},
    )
    template = apply_template_overlay(
        base,
        actor="user",
        timestamp=NOW,
        template_id="template-1",
        template_version=2,
    )
    recurrence = apply_recurrence_overlay(
        base,
        actor="author",
        timestamp=NOW,
        template_id="template-1",
        template_version=2,
        recurrence_id="recurrence-1",
        occurrence_id="occurrence-1",
    )

    assert base == original
    for overlaid in (manual, authored, template, recurrence):
        _assert_overlay_preserves_base(base, overlaid)

    assert set(manual) == set(base)
    assert manual["activity"] == [{
        "type": "project_created",
        "by": "user",
        "at": NOW,
        "detail": "Created project 'Overlay Base'",
    }]
    assert {
        key: authored[key]
        for key in (
            "agentMaintenanceMode",
            "authoringAgentId",
            "authoringRequestId",
            "authoringSource",
            "templateRef",
            "recurrenceRef",
        )
    } == {
        "agentMaintenanceMode": "strict_confirmation",
        "authoringAgentId": "author",
        "authoringRequestId": "request-1",
        "authoringSource": {"kind": "confirmed_agent_draft", "requestId": "request-1"},
        "templateRef": {"id": "template-1", "version": 2},
        "recurrenceRef": {"id": "recurrence-1"},
    }
    assert authored["activity"][0]["type"] == "project_authored"
    assert template["authoringSource"] == {
        "kind": "manual_template_instance",
        "templateId": "template-1",
        "templateVersion": 2,
    }
    assert template["templateRef"] == {"id": "template-1", "version": 2}
    assert template["recurrenceRef"] == {}
    assert template["activity"][0]["type"] == "project_instantiated_from_template"
    assert recurrence["authoringSource"] == {
        "kind": "recurrence_occurrence",
        "recurrenceId": "recurrence-1",
        "occurrenceId": "occurrence-1",
        "templateId": "template-1",
        "templateVersion": 2,
    }
    assert recurrence["templateRef"] == {"id": "template-1", "version": 2}
    assert recurrence["recurrenceRef"] == {
        "id": "recurrence-1",
        "occurrenceId": "occurrence-1",
    }


def test_source_overlays_deep_copy_base_and_provenance_inputs():
    base = _overlay_base()
    base["tags"] = [{"nested": ["base"]}]
    template_ref = {"id": "template-1", "metadata": ["source"]}
    overlaid = apply_authoring_overlay(
        base,
        actor={"id": "author"},
        request_id="request-1",
        timestamp=NOW,
        maintenance_mode="strict_confirmation",
        template_ref=template_ref,
    )

    overlaid["tags"][0]["nested"].append("overlay")
    overlaid["templateRef"]["metadata"].append("overlay")
    overlaid["activity"][0]["by"]["id"] = "changed"
    assert base["tags"] == [{"nested": ["base"]}]
    assert template_ref == {"id": "template-1", "metadata": ["source"]}


def test_prepared_workspace_separates_persisted_projection_from_cleanup_metadata():
    source = {
        "projectExecutionEnabled": True,
        "workspacePath": "/workspace/system",
        "workspaceKind": "directory",
        "workspaceStatus": {"ok": True, "checks": ["ready"]},
        "workspaceManagedBy": "system",
        "workspaceCreatedAt": NOW,
    }
    prepared = PreparedWorkspace.from_mapping(source, created_in_attempt=True)
    source["workspaceStatus"]["checks"].append("changed")

    assert prepared.project_fields() == {
        "projectExecutionEnabled": True,
        "workspacePath": "/workspace/system",
        "workspaceKind": "directory",
        "workspaceStatus": {"ok": True, "checks": ["ready"]},
        "workspaceManagedBy": "system",
        "workspaceCreatedAt": NOW,
    }
    assert prepared.cleanup_path == "/workspace/system"

    projected = materialize_project_base(
        {"title": "Workspace"},
        columns=[],
        tasks=[],
        workspace=prepared,
        project_id="workspace-project",
        timestamp=NOW,
        new_id=lambda: "unused",
        now=lambda: "unused",
    )
    assert projected["projectExecutionEnabled"] is True
    assert projected["workspaceManagedBy"] == "system"
    assert "created_in_attempt" not in projected
    assert "cleanup_path" not in projected


def test_prepared_workspace_cleanup_requires_system_owned_creation_attempt():
    user = PreparedWorkspace.from_mapping(
        {
            "projectExecutionEnabled": True,
            "workspacePath": "/workspace/user",
            "workspaceManagedBy": "user",
        },
        created_in_attempt=True,
    )
    existing_system = PreparedWorkspace.from_mapping(
        {
            "projectExecutionEnabled": True,
            "workspacePath": "/workspace/existing-system",
            "workspaceManagedBy": "system",
        },
    )
    assert user.cleanup_path is None
    assert existing_system.cleanup_path is None

    try:
        PreparedWorkspace.from_mapping({"workspaceManagedBy": "project_authoring"})
    except ValueError as exc:
        assert "system, user, or null" in str(exc)
    else:
        raise AssertionError("expected invalid workspace owner to fail")


def test_project_materialization_uses_execution_default_without_workspace_projection():
    project = materialize_project_base(
        {"title": "Resolved execution", "projectExecutionEnabled": True},
        columns=[],
        tasks=[],
        workspace=None,
        project_id="execution-project",
        timestamp=NOW,
        new_id=lambda: "unused",
        now=lambda: "unused",
    )

    assert project["projectExecutionEnabled"] is True
