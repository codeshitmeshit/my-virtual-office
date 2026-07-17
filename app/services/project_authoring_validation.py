"""Complete, side-effect-free validation for Agent-authored project drafts."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.project_actors import (
    ActorReferenceError,
    legacy_task_role_fields,
    validate_actor_reference,
)
from services.project_authoring_config import DEFAULT_CONFIG, ProjectAuthoringConfig


PROJECT_TYPES = frozenset({"one_time", "reusable", "recurring"})
MAINTENANCE_MODES = frozenset({"strict_confirmation", "autonomous"})
TEMPLATE_MODES = frozenset({"none", "create", "reference"})
REVIEW_TRIGGERS = frozenset({"high_risk", "cross_team", "critical_delivery"})
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


@dataclass(frozen=True)
class DraftValidationIssue:
    code: str
    path: str
    message: str
    actor_id: str = ""

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "path": self.path, "error": self.message}
        if self.actor_id:
            result["actorId"] = self.actor_id
        return result


@dataclass
class DraftValidationError(ValueError):
    issues: tuple[DraftValidationIssue, ...]
    code: str = "invalid_project_draft"

    def __str__(self) -> str:
        return self.issues[0].message if self.issues else "Invalid project draft"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "error": "Project draft validation failed",
            "issues": [issue.as_dict() for issue in self.issues],
            "_status": 400,
        }


def validate_idempotency_key(value: Any) -> str:
    key = str(value or "").strip()
    if not IDEMPOTENCY_PATTERN.fullmatch(key):
        raise DraftValidationError((DraftValidationIssue(
            "invalid_idempotency_key",
            "idempotencyKey",
            "Idempotency key must be 8-128 safe characters",
        ),))
    return key


def _text(
    value: Any,
    *,
    path: str,
    issues: list[DraftValidationIssue],
    required: bool,
    maximum: int,
) -> str:
    result = str(value or "").strip()
    if required and not result:
        issues.append(DraftValidationIssue("required", path, f"{path} is required"))
    elif len(result) > maximum:
        issues.append(DraftValidationIssue("too_long", path, f"{path} must not exceed {maximum} characters"))
    return result


def _schedule_error(schedule: Any) -> str | None:
    if not isinstance(schedule, Mapping):
        return "Recurring project schedule is required"
    kind = str(schedule.get("kind") or "").strip()
    if kind == "cron":
        fields = str(schedule.get("expr") or "").strip().split()
        if len(fields) < 5 or len(fields) > 7:
            return "Cron schedule requires a 5-7 field expr"
    elif kind == "every":
        try:
            every_ms = int(schedule.get("everyMs") or 0)
        except (TypeError, ValueError):
            every_ms = 0
        if every_ms < 60000:
            return "Recurring schedule everyMs must be at least 60000"
    else:
        return "Recurring project schedule kind must be cron or every"
    timezone_name = str(schedule.get("timezone") or "UTC").strip()
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return "Recurring project schedule timezone is invalid"
    return None


def _validate_template(
    value: Any,
    *,
    project_type: str,
    issues: list[DraftValidationIssue],
) -> dict[str, Any]:
    template = copy.deepcopy(value) if isinstance(value, Mapping) else {}
    mode = str(template.get("mode") or "").strip()
    if mode not in TEMPLATE_MODES:
        issues.append(DraftValidationIssue(
            "invalid_template_mode", "template.mode",
            "template.mode must be none, create, or reference",
        ))
        return template
    if project_type in {"reusable", "recurring"} and mode == "none":
        issues.append(DraftValidationIssue(
            "template_required", "template.mode",
            f"{project_type} projects require a created or referenced template",
        ))
    if mode == "create":
        name = str(template.get("name") or "").strip()
        if not name:
            issues.append(DraftValidationIssue("required", "template.name", "template.name is required"))
        template["name"] = name
    if mode == "reference":
        template_id = str(template.get("templateId") or "").strip()
        try:
            version = int(template.get("version") or 0)
        except (TypeError, ValueError):
            version = 0
        if not template_id:
            issues.append(DraftValidationIssue("required", "template.templateId", "template.templateId is required"))
        if version < 1:
            issues.append(DraftValidationIssue("invalid_template_version", "template.version", "template.version must be positive"))
        template.update({"templateId": template_id, "version": version})
    template["mode"] = mode
    return template


def _validate_recurrence(
    value: Any,
    *,
    project_type: str,
    issues: list[DraftValidationIssue],
) -> dict[str, Any]:
    recurrence = copy.deepcopy(value) if isinstance(value, Mapping) else {}
    enabled = recurrence.get("enabled") is True
    if project_type == "recurring" and not enabled:
        issues.append(DraftValidationIssue(
            "recurrence_required", "recurrence.enabled",
            "recurring projects require recurrence.enabled=true",
        ))
    if project_type != "recurring" and enabled:
        issues.append(DraftValidationIssue(
            "recurrence_not_allowed", "recurrence.enabled",
            "Only recurring projects may enable recurrence",
        ))
    if enabled:
        error = _schedule_error(recurrence.get("schedule"))
        if error:
            issues.append(DraftValidationIssue("invalid_recurrence_schedule", "recurrence.schedule", error))
        recurrence["paused"] = recurrence.get("paused") is True
    recurrence["enabled"] = enabled
    return recurrence


def _validate_reviewer_recommendation(
    value: Any,
    *,
    task_path: str,
    lookup_agent,
    is_excluded_agent,
    issues: list[DraftValidationIssue],
) -> dict[str, Any]:
    path = f"{task_path}.reviewerRecommendation"
    if not isinstance(value, Mapping):
        issues.append(DraftValidationIssue(
            "reviewer_recommendation_required", path,
            "Every task must include an explicit reviewer recommendation decision",
        ))
        return {"recommended": False, "triggers": []}
    recommendation = copy.deepcopy(value)
    recommended = recommendation.get("recommended") is True
    raw_triggers = recommendation.get("triggers")
    triggers = sorted({str(item).strip() for item in raw_triggers if str(item).strip()}) if isinstance(raw_triggers, list) else []
    invalid_triggers = [trigger for trigger in triggers if trigger not in REVIEW_TRIGGERS]
    if invalid_triggers:
        issues.append(DraftValidationIssue(
            "invalid_reviewer_trigger", f"{path}.triggers",
            "Reviewer triggers must be high_risk, cross_team, or critical_delivery",
        ))
    recommendation.update({"recommended": recommended, "triggers": triggers})
    if recommended:
        if not triggers:
            issues.append(DraftValidationIssue(
                "reviewer_trigger_required", f"{path}.triggers",
                "A recommended reviewer requires at least one risk trigger",
            ))
        rationale = _text(
            recommendation.get("rationale"), path=f"{path}.rationale",
            issues=issues, required=True, maximum=1000,
        )
        recommendation["rationale"] = rationale
        try:
            recommendation["candidate"] = validate_actor_reference(
                recommendation.get("candidate"), role="reviewerRecommendation",
                lookup_agent=lookup_agent, is_excluded_agent=is_excluded_agent,
                agent_only=True,
            )
        except ActorReferenceError as exc:
            issues.append(DraftValidationIssue(exc.code, f"{path}.candidate", exc.message, exc.actor_id))
    elif triggers:
        issues.append(DraftValidationIssue(
            "reviewer_recommendation_required", f"{path}.recommended",
            "Risk triggers require recommended=true and a reviewer candidate",
        ))
    return recommendation


def validate_project_draft(
    draft: Any,
    *,
    idempotency_key: Any,
    lookup_agent,
    is_excluded_agent,
    config: ProjectAuthoringConfig = DEFAULT_CONFIG,
    reviewer_assignment_confirmed: bool = False,
) -> dict[str, Any]:
    """Validate and normalize one complete project draft without side effects."""
    validate_idempotency_key(idempotency_key)
    if not isinstance(draft, Mapping):
        raise DraftValidationError((DraftValidationIssue(
            "invalid_draft", "draft", "Project draft must be an object",
        ),))
    normalized = copy.deepcopy(draft)
    issues: list[DraftValidationIssue] = []
    normalized["title"] = _text(
        draft.get("title"), path="title", issues=issues, required=True, maximum=200,
    )
    normalized["description"] = _text(
        draft.get("description"), path="description", issues=issues, required=False, maximum=20000,
    )
    project_type = str(draft.get("projectType") or "").strip()
    if project_type not in PROJECT_TYPES:
        issues.append(DraftValidationIssue(
            "invalid_project_type", "projectType",
            "projectType must be one_time, reusable, or recurring",
        ))
    normalized["projectType"] = project_type
    maintenance_mode = str(draft.get("agentMaintenanceMode") or "").strip()
    if maintenance_mode not in MAINTENANCE_MODES:
        issues.append(DraftValidationIssue(
            "invalid_maintenance_mode", "agentMaintenanceMode",
            "agentMaintenanceMode must be strict_confirmation or autonomous",
        ))
    normalized["agentMaintenanceMode"] = maintenance_mode

    columns = draft.get("columns", [])
    if not isinstance(columns, list):
        issues.append(DraftValidationIssue("invalid_columns", "columns", "columns must be an array"))
        columns = []
    normalized_columns = []
    column_ids: set[str] = set()
    for index, column in enumerate(columns):
        path = f"columns[{index}]"
        if not isinstance(column, Mapping):
            issues.append(DraftValidationIssue("invalid_column", path, "Column must be an object"))
            continue
        item = copy.deepcopy(column)
        item["id"] = str(column.get("id") or f"column-{index + 1}").strip()
        item["title"] = _text(column.get("title"), path=f"{path}.title", issues=issues, required=True, maximum=100)
        if item["id"] in column_ids:
            issues.append(DraftValidationIssue("duplicate_column_id", f"{path}.id", "Column ids must be unique"))
        column_ids.add(item["id"])
        normalized_columns.append(item)
    normalized["columns"] = normalized_columns

    tasks = draft.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        issues.append(DraftValidationIssue("tasks_required", "tasks", "At least one initial task is required"))
        tasks = []
    elif len(tasks) > config.max_initial_tasks:
        issues.append(DraftValidationIssue(
            "too_many_tasks", "tasks",
            f"Project draft must not exceed {config.max_initial_tasks} initial tasks",
        ))
    normalized_tasks = []
    for index, task in enumerate(tasks[: config.max_initial_tasks]):
        path = f"tasks[{index}]"
        if not isinstance(task, Mapping):
            issues.append(DraftValidationIssue("invalid_task", path, "Task must be an object"))
            continue
        item = copy.deepcopy(task)
        item["title"] = _text(task.get("title"), path=f"{path}.title", issues=issues, required=True, maximum=300)
        item["description"] = _text(task.get("description"), path=f"{path}.description", issues=issues, required=False, maximum=20000)
        if column_ids and task.get("columnId") not in column_ids:
            issues.append(DraftValidationIssue("unknown_column", f"{path}.columnId", "Task columnId was not found"))

        actors: dict[str, Any] = {}
        for role, required, agent_only in (
            ("responsible", True, False),
            ("executor", True, False),
            ("reviewer", False, True),
        ):
            field = f"{role}Actor"
            if role != "reviewer" and field not in task:
                issues.append(DraftValidationIssue("actor_required", f"{path}.{field}", f"{field} is required"))
                actors[role] = None
                continue
            if role == "reviewer" and task.get(field) and not reviewer_assignment_confirmed:
                issues.append(DraftValidationIssue(
                    "reviewer_not_user_confirmed", f"{path}.{field}",
                    "Agent drafts may recommend but cannot assign a reviewer before user confirmation",
                ))
            try:
                actors[role] = validate_actor_reference(
                    task.get(field), role=role, lookup_agent=lookup_agent,
                    is_excluded_agent=is_excluded_agent, required=required,
                    agent_only=agent_only,
                )
            except ActorReferenceError as exc:
                issues.append(DraftValidationIssue(exc.code, f"{path}.{field}", exc.message, exc.actor_id))
                actors[role] = None
        item["responsibleActor"] = actors.get("responsible")
        item["executorActor"] = actors.get("executor")
        item["reviewerActor"] = actors.get("reviewer") if reviewer_assignment_confirmed else None
        item.update(legacy_task_role_fields(actors))
        item["reviewerRecommendation"] = _validate_reviewer_recommendation(
            task.get("reviewerRecommendation"), task_path=path,
            lookup_agent=lookup_agent, is_excluded_agent=is_excluded_agent,
            issues=issues,
        )
        normalized_tasks.append(item)
    normalized["tasks"] = normalized_tasks
    normalized["template"] = _validate_template(
        draft.get("template"), project_type=project_type, issues=issues,
    )
    normalized["recurrence"] = _validate_recurrence(
        draft.get("recurrence"), project_type=project_type, issues=issues,
    )
    normalized["validatedAt"] = datetime.now().astimezone().isoformat()
    if issues:
        raise DraftValidationError(tuple(issues))
    return normalized
