"""Immutable versioned-template snapshots and legacy-template adapters."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence


TEMPLATE_SCHEMA_VERSION = 2
LEGACY_TEMPLATE_SCHEMA_VERSION = 1
_TASK_RUNTIME_FIELDS = frozenset({
    "activeAttemptId", "attempts", "blockedReason", "completedAt", "createdAt",
    "executionState", "lastError", "maintenanceHistory", "updatedAt",
})
_PROJECT_FIELDS = (
    "title", "description", "projectType", "priority", "dueDate", "tags", "branch",
    "longTermProject",
)
_EXECUTION_FIELDS = (
    "projectExecutionEnabled", "projectExecutionStartMode", "executionPolicy",
    "defaultExecutorAgentId", "defaultReviewerAgentId",
)


class ProjectTemplateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _version_number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _task_blueprint(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in task.items()
        if key not in _TASK_RUNTIME_FIELDS
    }


def build_template_snapshot(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze all fields needed to reproduce a confirmed project in the future."""
    project = {field: copy.deepcopy(draft.get(field)) for field in _PROJECT_FIELDS if field in draft}
    execution = {
        field: copy.deepcopy(draft.get(field))
        for field in _EXECUTION_FIELDS
        if field in draft
    }
    # New immutable snapshots always carry the resolved execution intent. Agent
    # validation normally supplies it; direct callers receive the same enabled
    # default rather than creating another ambiguous historical snapshot.
    execution.setdefault("projectExecutionEnabled", True)
    execution.setdefault("projectExecutionStartMode", "continuous")
    execution.setdefault("executionPolicy", {"maxActiveTasks": 1})
    tasks = [
        _task_blueprint(task)
        for task in (draft.get("tasks") or [])
        if isinstance(task, Mapping)
    ]
    return {
        "schemaVersion": TEMPLATE_SCHEMA_VERSION,
        **project,
        "columns": copy.deepcopy(draft.get("columns") or []),
        "tasks": tasks,
        "reviewerPolicy": "optional_user_confirmed_per_task",
        "agentMaintenanceMode": draft.get("agentMaintenanceMode") or "strict_confirmation",
        "executionSettings": execution,
    }


def append_template_version(
    versions: list[dict[str, Any]],
    *,
    template_id: str,
    name: str,
    draft: Mapping[str, Any],
    created_at: str,
    created_by: str,
    source_request_id: str = "",
) -> dict[str, Any]:
    """Append one immutable snapshot; existing records are never updated in place."""
    if not template_id:
        raise ProjectTemplateError("template_id_required", "Template id is required")
    existing_versions = [
        _version_number(item.get("version"))
        for item in versions
        if isinstance(item, Mapping)
    ]
    version_number = max(existing_versions, default=0) + 1
    snapshot = build_template_snapshot(draft)
    record = {
        "id": template_id,
        "templateId": template_id,
        "version": version_number,
        "name": str(name or draft.get("title") or "Template"),
        "createdAt": created_at,
        "createdBy": created_by,
        "sourceRequestId": source_request_id,
        "snapshotDigest": _digest(snapshot),
        "snapshot": snapshot,
    }
    versions.append(copy.deepcopy(record))
    return copy.deepcopy(record)


def adapt_legacy_template(template: Mapping[str, Any]) -> dict[str, Any]:
    """Expose an existing flat browser template as a read-only implicit version 1."""
    template_id = str(template.get("id") or "").strip()
    if not template_id:
        raise ProjectTemplateError("template_id_required", "Legacy template id is required")
    columns = []
    for index, column in enumerate(template.get("columns") or []):
        if not isinstance(column, Mapping):
            continue
        item = copy.deepcopy(dict(column))
        item.setdefault("id", f"column-{index + 1}")
        item.setdefault("order", index)
        columns.append(item)
    tasks = []
    for index, task in enumerate(template.get("taskTemplates") or template.get("tasks") or []):
        if not isinstance(task, Mapping):
            continue
        item = _task_blueprint(task)
        try:
            column_index = int(item.pop("columnIndex", 0) or 0)
        except (TypeError, ValueError):
            column_index = 0
        if "columnId" not in item and columns:
            item["columnId"] = columns[min(max(column_index, 0), len(columns) - 1)]["id"]
        item.setdefault("id", f"blueprint-{index + 1}")
        item.setdefault("responsibleActor", None)
        item.setdefault("executorActor", None)
        item.setdefault("reviewerActor", None)
        item.setdefault("reviewerRecommendation", {"recommended": False, "triggers": []})
        tasks.append(item)
    snapshot = {
        "schemaVersion": LEGACY_TEMPLATE_SCHEMA_VERSION,
        "legacy": True,
        "title": template.get("title") or "Template",
        "description": template.get("description") or "",
        "columns": columns,
        "tasks": tasks,
        "reviewerPolicy": "legacy_unassigned",
        "agentMaintenanceMode": "strict_confirmation",
        "executionSettings": {
            "projectExecutionEnabled": False,
            "projectExecutionStartMode": "continuous",
            "executionPolicy": {"maxActiveTasks": 1},
        },
    }
    return {
        "id": template_id,
        "templateId": template_id,
        "version": 1,
        "name": template.get("title") or "Template",
        "createdAt": template.get("createdAt") or "",
        "createdBy": template.get("createdBy") or "legacy_browser",
        "sourceRequestId": "",
        "legacy": True,
        "snapshotDigest": _digest(snapshot),
        "snapshot": snapshot,
    }


def resolve_template_version(
    versions_by_id: Mapping[str, Any],
    legacy_templates: Sequence[Any],
    template_id: str,
    version: int,
) -> dict[str, Any]:
    """Resolve an explicit immutable version, falling back to legacy implicit v1."""
    versions = versions_by_id.get(template_id) if isinstance(versions_by_id, Mapping) else None
    if isinstance(versions, list):
        match = next(
            (
                item for item in versions
                if isinstance(item, Mapping) and _version_number(item.get("version")) == int(version)
            ),
            None,
        )
        if match is not None:
            resolved = copy.deepcopy(dict(match))
            snapshot = resolved.get("snapshot")
            if isinstance(snapshot, dict):
                try:
                    schema_version = int(snapshot.get("schemaVersion") or 1)
                except (TypeError, ValueError):
                    schema_version = 1
                if schema_version <= LEGACY_TEMPLATE_SCHEMA_VERSION:
                    execution = snapshot.get("executionSettings")
                    if not isinstance(execution, dict):
                        execution = {}
                        snapshot["executionSettings"] = execution
                    # Version-1 snapshots predate explicit execution intent.
                    # Preserve their historical disabled behavior, including
                    # records where the old writer omitted the synthesized field.
                    execution.setdefault("projectExecutionEnabled", False)
            return resolved
    if int(version) == 1:
        legacy = next(
            (
                item for item in legacy_templates
                if isinstance(item, Mapping) and str(item.get("id") or "") == template_id
            ),
            None,
        )
        if legacy is not None:
            return adapt_legacy_template(legacy)
    raise ProjectTemplateError("template_version_not_found", "Template version was not found")


def template_version_to_legacy(record: Mapping[str, Any]) -> dict[str, Any]:
    """Render a version snapshot through the existing browser template contract."""
    snapshot = record.get("snapshot") if isinstance(record.get("snapshot"), Mapping) else {}
    columns = copy.deepcopy(snapshot.get("columns") or [])
    column_indexes = {
        str(column.get("id") or ""): index
        for index, column in enumerate(columns)
        if isinstance(column, Mapping)
    }
    task_templates = []
    for task in snapshot.get("tasks") or []:
        if not isinstance(task, Mapping):
            continue
        item = _task_blueprint(task)
        column_id = str(item.pop("columnId", "") or "")
        item["columnIndex"] = column_indexes.get(column_id, 0)
        task_templates.append(item)
    return {
        "id": record.get("templateId") or record.get("id"),
        "title": record.get("name") or snapshot.get("title") or "Template",
        "description": snapshot.get("description") or "",
        "version": _version_number(record.get("version")) or 1,
        "versioned": True,
        "columns": columns,
        "taskTemplates": task_templates,
    }


def latest_template_version(versions: Sequence[Any]) -> dict[str, Any] | None:
    records = [item for item in versions if isinstance(item, Mapping)]
    if not records:
        return None
    return copy.deepcopy(dict(max(records, key=lambda item: _version_number(item.get("version")))))
