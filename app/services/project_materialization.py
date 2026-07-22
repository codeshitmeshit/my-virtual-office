"""Pure canonical materialization for newly persisted Projects and Tasks.

This module deliberately owns no validation, persistence, workspace side effects,
or execution orchestration. Callers resolve those concerns before projecting a
new persisted object here.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from typing import Any


DEFAULT_COLUMNS: tuple[Mapping[str, Any], ...] = (
    {"title": "Backlog", "color": "#6c757d", "order": 0},
    {"title": "In Progress", "color": "#ffc107", "order": 1},
    {"title": "Review", "color": "#fd7e14", "order": 2},
    {"title": "Done", "color": "#198754", "order": 3},
)

CANONICAL_PROJECT_BASE_FIELDS = frozenset({
    "activeAgent",
    "activeTaskId",
    "activity",
    "archiveMaintenance",
    "archiveMaintenanceEnabled",
    "branch",
    "columns",
    "createdAt",
    "createdBy",
    "defaultExecutorAgentId",
    "defaultReviewerAgentId",
    "description",
    "dueDate",
    "executionDirtyConfirmations",
    "executionPolicy",
    "highPriorityAiMeetingAutoApprove",
    "id",
    "longTermProject",
    "priority",
    "projectExecutionEnabled",
    "projectExecutionFlowActive",
    "projectExecutionFlowStopReason",
    "projectExecutionStartMode",
    "projectType",
    "scheduledCronPaused",
    "status",
    "tags",
    "tasks",
    "template",
    "title",
    "updatedAt",
    "workflowActive",
    "workflowPhase",
    "workspaceCreatedAt",
    "workspaceKind",
    "workspaceManagedBy",
    "workspacePath",
    "workspaceStatus",
})


def _meaningful_columns(
    columns: Sequence[Mapping[str, Any]] | None,
) -> list[tuple[int, Mapping[str, Any]]]:
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes)):
        return []
    return [
        (index, column)
        for index, column in enumerate(columns)
        if isinstance(column, Mapping) and str(column.get("title") or "").strip()
    ]


def materialize_columns(
    columns: Sequence[Mapping[str, Any]] | None,
    *,
    new_id: Callable[[], str],
    preserve_ids: bool = True,
) -> tuple[list[dict[str, Any]], dict[Any, str]]:
    """Return copied canonical columns and a source key-to-new-ID mapping.

    The mapping always contains source indexes and also contains non-empty source
    IDs. This supports both index-based browser templates and ID-based drafts.
    """

    indexed_sources = _meaningful_columns(columns)
    if not indexed_sources:
        indexed_sources = list(enumerate(DEFAULT_COLUMNS))

    materialized: list[dict[str, Any]] = []
    source_map: dict[Any, str] = {}
    for materialized_index, (source_index, source) in enumerate(indexed_sources):
        column = copy.deepcopy(dict(source))
        source_id = str(source.get("id") or "").strip()
        column_id = source_id if preserve_ids and source_id else str(new_id())
        column.update({
            "id": column_id,
            "title": str(source.get("title") or "").strip(),
            "color": source.get("color") or "#6c757d",
            "order": copy.deepcopy(source.get("order", materialized_index)),
        })
        materialized.append(column)
        source_map[source_index] = column_id
        if source_id:
            source_map[source_id] = column_id

    return materialized, source_map


def materialize_project_base(
    configuration: Mapping[str, Any],
    *,
    columns: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]] | None,
    workspace: Mapping[str, Any] | None,
    new_id: Callable[[], str],
    now: Callable[[], str],
    project_id: str | None = None,
    timestamp: str | None = None,
    archive_maintenance_enabled: bool = False,
    archive_maintenance_explicit: bool = False,
    archive_maintenance_updated_by: str | None = None,
) -> dict[str, Any]:
    """Project resolved configuration onto the canonical persisted base fields."""

    created_at = str(timestamp or now())
    created_by = str(configuration.get("createdBy") or "user").strip() or "user"
    prepared_workspace = workspace if isinstance(workspace, Mapping) else {}
    execution_enabled = bool(
        prepared_workspace.get(
            "projectExecutionEnabled",
            configuration.get("projectExecutionEnabled", False),
        )
    )
    maintenance_updated_by = archive_maintenance_updated_by or created_by

    project = {
        "id": str(project_id or new_id()),
        "title": str(configuration.get("title") or "").strip(),
        "description": copy.deepcopy(configuration.get("description") or ""),
        "projectType": configuration.get("projectType") or "one_time",
        "status": configuration.get("status") or "active",
        "priority": configuration.get("priority") or "medium",
        "createdAt": created_at,
        "updatedAt": created_at,
        "dueDate": copy.deepcopy(configuration.get("dueDate")),
        "createdBy": created_by,
        "tags": copy.deepcopy(configuration.get("tags") or []),
        "branch": copy.deepcopy(configuration.get("branch") or ""),
        "longTermProject": configuration.get("longTermProject") is True,
        "highPriorityAiMeetingAutoApprove": (
            configuration.get("highPriorityAiMeetingAutoApprove") is True
        ),
        "archiveMaintenanceEnabled": bool(archive_maintenance_enabled),
        "archiveMaintenance": {
            "enabled": bool(archive_maintenance_enabled),
            "explicit": bool(archive_maintenance_explicit),
            "updatedAt": created_at,
            "updatedBy": maintenance_updated_by,
        },
        "projectExecutionEnabled": execution_enabled,
        "workspacePath": copy.deepcopy(prepared_workspace.get("workspacePath")),
        "workspaceKind": copy.deepcopy(prepared_workspace.get("workspaceKind")),
        "workspaceStatus": copy.deepcopy(prepared_workspace.get("workspaceStatus") or {}),
        "workspaceManagedBy": copy.deepcopy(prepared_workspace.get("workspaceManagedBy")),
        "workspaceCreatedAt": copy.deepcopy(prepared_workspace.get("workspaceCreatedAt")),
        "defaultExecutorAgentId": copy.deepcopy(configuration.get("defaultExecutorAgentId")),
        "defaultReviewerAgentId": copy.deepcopy(configuration.get("defaultReviewerAgentId")),
        "projectExecutionStartMode": (
            configuration.get("projectExecutionStartMode") or "continuous"
        ),
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": None,
        "scheduledCronPaused": configuration.get("scheduledCronPaused") is True,
        "executionPolicy": copy.deepcopy(
            configuration.get("executionPolicy") or {"maxActiveTasks": 1}
        ),
        "executionDirtyConfirmations": [],
        "workflowActive": False,
        "workflowPhase": "idle",
        "activeTaskId": None,
        "activeAgent": None,
        "columns": copy.deepcopy(list(columns)),
        "tasks": copy.deepcopy(list(tasks or [])),
        "activity": [],
        "template": False,
    }
    return project
