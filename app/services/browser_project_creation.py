"""Browser-template Project creation independent of HTTP and server globals."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .project_execution import ServiceResult
from .project_materialization import (
    ProjectMaterializationError,
    apply_manual_overlay,
    apply_template_overlay,
    materialize_columns,
    materialize_project_base,
    materialize_task_base,
)
from .project_repository import ProjectAlreadyExistsError, ProjectRepository


def _result_from_error(payload: Mapping[str, Any], default_status: int = 400) -> ServiceResult:
    status = int(payload.get("_status") or default_status)
    return ServiceResult(status, {key: value for key, value in payload.items() if key != "_status"})


def _find_template(
    template_id: str,
    catalog: Mapping[str, Any],
    browser_templates: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]]],
    builtin_templates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    template = next(
        (item for item in browser_templates(catalog) if item.get("id") == template_id),
        None,
    )
    if template is not None:
        return template
    return next(
        (item for item in builtin_templates if item.get("id") == template_id),
        None,
    )


def create_from_browser_template(
    body: Mapping[str, Any],
    *,
    repository: ProjectRepository,
    load_catalog: Callable[[], Mapping[str, Any]],
    browser_templates: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]]],
    builtin_templates: Sequence[Mapping[str, Any]],
    assignment_error: Callable[[Any, str], Mapping[str, Any] | None],
    prepare_workspace: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]],
    new_id: Callable[[], str],
    now: Callable[[], str],
) -> ServiceResult:
    """Validate, canonically materialize, and persist one browser template instance."""

    template_id = str(body.get("templateId") or "").strip()
    title = str(body.get("title") or "").strip()
    if not title:
        return ServiceResult(400, {"error": "Project title is required"})

    template = _find_template(
        template_id,
        load_catalog(),
        browser_templates,
        builtin_templates,
    )
    if template is None:
        return ServiceResult(404, {"error": "Template not found"})

    timestamp = now()
    columns, column_map = materialize_columns(
        template.get("columns"),
        new_id=new_id,
        preserve_ids=False,
    )
    tasks = []
    for blueprint in template.get("taskTemplates") or []:
        if not isinstance(blueprint, Mapping):
            continue
        task_configuration = {
            "title": blueprint.get("title") or "Task",
            "description": blueprint.get("description", ""),
            "columnId": column_map.get(blueprint.get("columnIndex", 0)),
            "order": blueprint.get("order", 0),
            "priority": blueprint.get("priority", "medium"),
            "responsibleActor": copy.deepcopy(blueprint.get("responsibleActor")),
            "executorActor": copy.deepcopy(blueprint.get("executorActor")),
            "reviewerActor": copy.deepcopy(blueprint.get("reviewerActor")),
            "reviewerRecommendation": copy.deepcopy(
                blueprint.get("reviewerRecommendation") or {}
            ),
            "assignee": blueprint.get("assignee"),
            "assigneeBranch": None,
            "executorAgentId": blueprint.get("executorAgentId"),
            "reviewerAgentId": blueprint.get("reviewerAgentId"),
            "requiresUserAcceptance": blueprint.get("requiresUserAcceptance", False),
            "allowReviewerlessExecution": blueprint.get(
                "allowReviewerlessExecution", False
            ),
            "scheduledRepeatEnabled": blueprint.get("scheduledRepeatEnabled", False),
            "dueDate": None,
            "tags": copy.deepcopy(blueprint.get("tags") or []),
            "checklist": copy.deepcopy(blueprint.get("checklist") or []),
        }
        try:
            task = materialize_task_base(
                task_configuration,
                columns=columns,
                task_id=new_id(),
                timestamp=timestamp,
                new_id=new_id,
                now=now,
            )
        except ProjectMaterializationError as exc:
            return ServiceResult(400, {"error": str(exc)})
        tasks.append(task)

    for field in ("defaultExecutorAgentId", "defaultReviewerAgentId"):
        if rejected := assignment_error(body.get(field), "template"):
            return _result_from_error(rejected)
    for task in tasks:
        for field in ("assignee", "executorAgentId", "reviewerAgentId"):
            if rejected := assignment_error(task.get(field), "task"):
                return _result_from_error(rejected)

    created_by = str(body.get("createdBy") or "user").strip() or "user"
    workspace = prepare_workspace(title, body, timestamp)
    if not workspace.get("ok"):
        return _result_from_error(workspace)

    maintenance_enabled = (
        bool(body["archiveMaintenanceEnabled"])
        if "archiveMaintenanceEnabled" in body
        else True
    )
    project = materialize_project_base(
        {
            **body,
            "title": title,
            "description": body.get("description", template.get("description", "")),
            "createdBy": created_by,
            "executionPolicy": {"maxActiveTasks": 1},
        },
        columns=columns,
        tasks=tasks,
        workspace=workspace,
        new_id=new_id,
        now=now,
        timestamp=timestamp,
        archive_maintenance_enabled=maintenance_enabled,
        archive_maintenance_explicit="archiveMaintenanceEnabled" in body,
        archive_maintenance_updated_by=created_by,
    )
    activity_detail = f"Created from template '{template.get('title', '')}'"
    if template.get("versioned") is True:
        project = apply_template_overlay(
            project,
            actor=created_by,
            timestamp=timestamp,
            template_id=template_id,
            template_version=int(template.get("version") or 1),
            source_kind="browser_template_instance",
            activity_type="project_created",
            detail=activity_detail,
        )
    else:
        project = apply_manual_overlay(
            project,
            actor=created_by,
            timestamp=timestamp,
            detail=activity_detail,
        )

    try:
        repository.create(project)
    except ProjectAlreadyExistsError:
        return ServiceResult(409, {"error": "Project already exists"})
    return ServiceResult(200, {"ok": True, "project": project})
