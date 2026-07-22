"""Pure canonical materialization for newly persisted Projects and Tasks.

This module deliberately owns no validation, persistence, workspace side effects,
or execution orchestration. Callers resolve those concerns before projecting a
new persisted object here.
"""

from __future__ import annotations

import copy
import hashlib
import re
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

CANONICAL_TASK_BASE_FIELDS = frozenset({
    "activeAttemptId",
    "allowReviewerlessExecution",
    "assignee",
    "assigneeBranch",
    "attachments",
    "attempts",
    "blockedReason",
    "checklist",
    "columnId",
    "comments",
    "completedAt",
    "createdAt",
    "description",
    "dueDate",
    "evidence",
    "executionState",
    "executorActor",
    "executorAgentId",
    "id",
    "lastError",
    "meetingActionItems",
    "meetingDecisionHistory",
    "meetingDiscussionPoints",
    "meetingRecords",
    "order",
    "priority",
    "requiresUserAcceptance",
    "responsibleActor",
    "reviewerActor",
    "reviewerAgentId",
    "reviewerRecommendation",
    "scheduledRepeatEnabled",
    "source",
    "tags",
    "title",
    "updatedAt",
})

MAX_CHECKLIST_ITEMS = 100


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


def _normalized_checklist_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique_checklist_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def materialize_checklist(
    checklist: Sequence[Mapping[str, Any] | str] | None,
    *,
    max_items: int = MAX_CHECKLIST_ITEMS,
) -> list[dict[str, Any]]:
    """Normalize acceptance criteria into stable execution checklist items."""

    if checklist is None:
        return []
    if not isinstance(checklist, Sequence) or isinstance(checklist, (str, bytes)):
        raise ValueError("checklist must be a list of text values or mappings")
    if len(checklist) > max_items:
        raise ValueError(f"checklist cannot contain more than {max_items} items")

    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for value in checklist:
        if isinstance(value, Mapping):
            source = value
            text = _normalized_checklist_text(source.get("text"))
        elif isinstance(value, str):
            source = {}
            text = _normalized_checklist_text(value)
        else:
            continue
        if not text:
            continue

        supplied_id = str(source.get("id") or "").strip()
        stable_text = text.casefold()
        base_id = supplied_id or (
            "checklist-" + hashlib.sha256(stable_text.encode("utf-8")).hexdigest()[:12]
        )
        item = {
            "id": _unique_checklist_id(base_id, used_ids),
            "text": text,
            "done": source.get("done") is True,
        }
        if "evidence" in source:
            item["evidence"] = copy.deepcopy(source.get("evidence"))
        normalized.append(item)
    return normalized


def _canonical_task_column_id(
    requested: Any,
    columns: Sequence[Mapping[str, Any]],
) -> Any:
    valid_ids = [
        column.get("id")
        for column in columns
        if isinstance(column, Mapping) and column.get("id") is not None
    ]
    if requested in valid_ids:
        return copy.deepcopy(requested)
    backlog = next(
        (
            column.get("id")
            for column in columns
            if isinstance(column, Mapping)
            and str(column.get("title") or "").strip().casefold() == "backlog"
        ),
        None,
    )
    if backlog is not None:
        return copy.deepcopy(backlog)
    return copy.deepcopy(valid_ids[0] if valid_ids else None)


def materialize_task_base(
    configuration: Mapping[str, Any],
    *,
    columns: Sequence[Mapping[str, Any]],
    new_id: Callable[[], str],
    now: Callable[[], str],
    task_id: str | None = None,
    timestamp: str | None = None,
    order: Any = None,
) -> dict[str, Any]:
    """Project resolved Task configuration onto canonical persisted base fields."""

    created_at = str(timestamp or now())
    configured_order = configuration.get("order")
    resolved_order = (
        order if order is not None else (0 if configured_order is None else configured_order)
    )
    source = configuration.get("source")
    evidence = configuration.get("evidence")

    return {
        "id": str(task_id or configuration.get("id") or new_id()),
        "title": str(configuration.get("title") or "").strip(),
        "description": copy.deepcopy(configuration.get("description") or ""),
        "columnId": _canonical_task_column_id(configuration.get("columnId"), columns),
        "order": copy.deepcopy(resolved_order),
        "priority": configuration.get("priority") or "medium",
        "responsibleActor": copy.deepcopy(configuration.get("responsibleActor")),
        "executorActor": copy.deepcopy(configuration.get("executorActor")),
        "reviewerActor": copy.deepcopy(configuration.get("reviewerActor")),
        "reviewerRecommendation": copy.deepcopy(
            configuration.get("reviewerRecommendation") or {}
        ),
        "assignee": copy.deepcopy(configuration.get("assignee")),
        "assigneeBranch": copy.deepcopy(configuration.get("assigneeBranch")),
        "executorAgentId": copy.deepcopy(configuration.get("executorAgentId")),
        "reviewerAgentId": copy.deepcopy(configuration.get("reviewerAgentId")),
        "requiresUserAcceptance": configuration.get("requiresUserAcceptance") is True,
        "allowReviewerlessExecution": configuration.get("allowReviewerlessExecution") is True,
        "scheduledRepeatEnabled": configuration.get("scheduledRepeatEnabled") is True,
        "executionState": "backlog",
        "activeAttemptId": None,
        "attempts": [],
        "evidence": copy.deepcopy(dict(evidence)) if isinstance(evidence, Mapping) else {},
        "blockedReason": None,
        "lastError": None,
        "dueDate": copy.deepcopy(configuration.get("dueDate")),
        "tags": copy.deepcopy(configuration.get("tags") or []),
        "checklist": materialize_checklist(configuration.get("checklist")),
        "meetingActionItems": copy.deepcopy(
            configuration.get("meetingActionItems")
            if isinstance(configuration.get("meetingActionItems"), list)
            else []
        ),
        "meetingDecisionHistory": copy.deepcopy(
            configuration.get("meetingDecisionHistory")
            if isinstance(configuration.get("meetingDecisionHistory"), list)
            else []
        ),
        "meetingDiscussionPoints": copy.deepcopy(
            configuration.get("meetingDiscussionPoints")
            if isinstance(configuration.get("meetingDiscussionPoints"), list)
            else []
        ),
        "meetingRecords": copy.deepcopy(
            configuration.get("meetingRecords")
            if isinstance(configuration.get("meetingRecords"), list)
            else []
        ),
        "source": copy.deepcopy(dict(source)) if isinstance(source, Mapping) else {},
        "comments": [],
        "attachments": [],
        "createdAt": created_at,
        "updatedAt": created_at,
        "completedAt": None,
    }


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
