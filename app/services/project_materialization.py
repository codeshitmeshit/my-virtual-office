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
from dataclasses import dataclass
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

# Persisted fields allowed in addition to the canonical Project base. Activity
# remains a canonical field; its source-specific event type is documented
# separately so overlays cannot use provenance to omit base fields.
PERMITTED_PROJECT_OVERLAY_FIELDS = {
    "manual": frozenset(),
    "browser_template": frozenset({"authoringSource", "recurrenceRef", "templateRef"}),
    "agent_direct": frozenset({
        "agentMaintenanceMode", "authoringAgentId", "authoringSource",
        "recurrenceRef", "templateRef",
    }),
    "versioned_template": frozenset({
        "agentMaintenanceMode", "authoringSource", "recurrenceRef", "templateRef",
    }),
    "recurrence": frozenset({
        "agentMaintenanceMode", "authoringSource", "recurrenceRef", "templateRef",
    }),
}
PROJECT_CREATION_ACTIVITY_TYPES = {
    "manual": "project_created",
    "browser_template": "project_created",
    "agent_direct": "project_authored",
    "versioned_template": "project_instantiated_from_template",
    "recurrence": "project_instantiated_from_template",
}

MAX_CHECKLIST_ITEMS = 100


class ProjectMaterializationError(ValueError):
    """Resolved creation input cannot be projected onto the canonical contract."""


@dataclass(frozen=True)
class PreparedWorkspace:
    """Canonical persisted workspace values plus non-persisted cleanup intent."""

    project_execution_enabled: bool
    workspace_path: Any = None
    workspace_kind: Any = None
    workspace_status: Any = None
    workspace_managed_by: str | None = None
    workspace_created_at: Any = None
    created_in_attempt: bool = False

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any] | None,
        *,
        created_in_attempt: bool = False,
        project_execution_enabled_default: bool = False,
    ) -> PreparedWorkspace:
        source = value if isinstance(value, Mapping) else {}
        managed_by = source.get("workspaceManagedBy")
        if managed_by not in (None, "system", "user"):
            raise ProjectMaterializationError(
                "workspaceManagedBy must be system, user, or null"
            )
        return cls(
            project_execution_enabled=bool(
                source.get(
                    "projectExecutionEnabled",
                    project_execution_enabled_default,
                )
            ),
            workspace_path=copy.deepcopy(source.get("workspacePath")),
            workspace_kind=copy.deepcopy(source.get("workspaceKind")),
            workspace_status=copy.deepcopy(source.get("workspaceStatus") or {}),
            workspace_managed_by=managed_by,
            workspace_created_at=copy.deepcopy(source.get("workspaceCreatedAt")),
            created_in_attempt=bool(created_in_attempt),
        )

    def project_fields(self) -> dict[str, Any]:
        return {
            "projectExecutionEnabled": self.project_execution_enabled,
            "workspacePath": copy.deepcopy(self.workspace_path),
            "workspaceKind": copy.deepcopy(self.workspace_kind),
            "workspaceStatus": copy.deepcopy(self.workspace_status or {}),
            "workspaceManagedBy": self.workspace_managed_by,
            "workspaceCreatedAt": copy.deepcopy(self.workspace_created_at),
        }

    @property
    def cleanup_path(self) -> Any:
        if self.created_in_attempt and self.workspace_managed_by == "system":
            return copy.deepcopy(self.workspace_path)
        return None


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
        raise ProjectMaterializationError(
            "checklist must be a list of text values or mappings"
        )
    if len(checklist) > max_items:
        raise ProjectMaterializationError(
            f"checklist cannot contain more than {max_items} items"
        )

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
    existing_tasks: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project resolved Task configuration onto canonical persisted base fields."""

    created_at = str(timestamp or now())
    column_id = _canonical_task_column_id(configuration.get("columnId"), columns)
    configured_order = configuration.get("order")
    if order is not None:
        resolved_order = order
    elif configured_order is not None:
        resolved_order = configured_order
    elif existing_tasks is not None:
        resolved_order = max(
            (
                task.get("order", 0)
                for task in existing_tasks
                if isinstance(task, Mapping) and task.get("columnId") == column_id
            ),
            default=-1,
        ) + 1
    else:
        resolved_order = 0
    source = configuration.get("source")
    evidence = configuration.get("evidence")

    return {
        "id": str(task_id or configuration.get("id") or new_id()),
        "title": str(configuration.get("title") or "").strip(),
        "description": copy.deepcopy(configuration.get("description") or ""),
        "columnId": column_id,
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


def _copy_with_activity(
    project: Mapping[str, Any],
    *,
    activity_type: str,
    actor: Any,
    timestamp: str,
    detail: str,
) -> dict[str, Any]:
    overlaid = copy.deepcopy(dict(project))
    activity = overlaid.get("activity")
    if not isinstance(activity, list):
        activity = []
        overlaid["activity"] = activity
    activity.append({
        "type": activity_type,
        "by": copy.deepcopy(actor),
        "at": timestamp,
        "detail": detail,
    })
    return overlaid


def apply_manual_overlay(
    project: Mapping[str, Any],
    *,
    actor: Any,
    timestamp: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """Add manual-creation activity without rebuilding canonical fields."""

    title = str(project.get("title") or "")
    return _copy_with_activity(
        project,
        activity_type="project_created",
        actor=actor,
        timestamp=timestamp,
        detail=detail or f"Created project '{title}'",
    )


def apply_authoring_overlay(
    project: Mapping[str, Any],
    *,
    actor: Any,
    request_id: str,
    timestamp: str,
    maintenance_mode: str,
    template_ref: Mapping[str, Any] | None = None,
    recurrence_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Add confirmed Agent provenance and its initial audit activity."""

    overlaid = _copy_with_activity(
        project,
        activity_type="project_authored",
        actor=actor,
        timestamp=timestamp,
        detail=f"Created from confirmed Agent draft {request_id}",
    )
    overlaid.update({
        "agentMaintenanceMode": maintenance_mode,
        "authoringAgentId": copy.deepcopy(actor),
        "authoringRequestId": request_id,
        "authoringSource": {"kind": "confirmed_agent_draft", "requestId": request_id},
        "templateRef": copy.deepcopy(dict(template_ref or {})),
        "recurrenceRef": copy.deepcopy(dict(recurrence_ref or {})),
    })
    return overlaid


def apply_template_overlay(
    project: Mapping[str, Any],
    *,
    actor: Any,
    timestamp: str,
    template_id: str,
    template_version: int,
    source_kind: str = "manual_template_instance",
    activity_type: str = "project_instantiated_from_template",
    detail: str | None = None,
) -> dict[str, Any]:
    """Add immutable template provenance and one source-appropriate activity."""

    overlaid = _copy_with_activity(
        project,
        activity_type=activity_type,
        actor=actor,
        timestamp=timestamp,
        detail=detail or f"Created from template {template_id} version {template_version}",
    )
    overlaid.update({
        "authoringSource": {
            "kind": source_kind,
            "templateId": template_id,
            "templateVersion": template_version,
        },
        "templateRef": {"id": template_id, "version": template_version},
        "recurrenceRef": {},
    })
    return overlaid


def apply_recurrence_overlay(
    project: Mapping[str, Any],
    *,
    actor: Any,
    timestamp: str,
    template_id: str,
    template_version: int,
    recurrence_id: str,
    occurrence_id: str,
) -> dict[str, Any]:
    """Add deterministic recurrence/template provenance to an occurrence Project."""

    overlaid = _copy_with_activity(
        project,
        activity_type="project_instantiated_from_template",
        actor=actor,
        timestamp=timestamp,
        detail=f"Created from template {template_id} version {template_version}",
    )
    overlaid.update({
        "authoringSource": {
            "kind": "recurrence_occurrence",
            "recurrenceId": recurrence_id,
            "occurrenceId": occurrence_id,
            "templateId": template_id,
            "templateVersion": template_version,
        },
        "templateRef": {"id": template_id, "version": template_version},
        "recurrenceRef": {"id": recurrence_id, "occurrenceId": occurrence_id},
    })
    return overlaid


def materialize_project_base(
    configuration: Mapping[str, Any],
    *,
    columns: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]] | None,
    workspace: PreparedWorkspace | Mapping[str, Any] | None,
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
    prepared_workspace = (
        workspace
        if isinstance(workspace, PreparedWorkspace)
        else PreparedWorkspace.from_mapping(
            workspace,
            project_execution_enabled_default=bool(
                configuration.get("projectExecutionEnabled", False)
            ),
        )
    )
    workspace_fields = prepared_workspace.project_fields()
    execution_enabled = bool(
        workspace_fields.get(
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
        "workspacePath": workspace_fields["workspacePath"],
        "workspaceKind": workspace_fields["workspaceKind"],
        "workspaceStatus": workspace_fields["workspaceStatus"],
        "workspaceManagedBy": workspace_fields["workspaceManagedBy"],
        "workspaceCreatedAt": workspace_fields["workspaceCreatedAt"],
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
