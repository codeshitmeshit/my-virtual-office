"""Pure Project task orchestration model helpers.

This module owns stage-pipeline validation and projections. It intentionally has
no repository, HTTP, workspace, provider, or notification dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


Project = dict[str, Any]
Task = dict[str, Any]

EXECUTION_MODEL_STAGE_PIPELINE_V1 = "stage_pipeline_v1"
ORCHESTRATION_SCHEMA_VERSION = 1

STATE_DRAFT = "draft"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_PAUSING = "pausing"
STATE_PAUSED = "paused"
STATE_BLOCKED = "blocked"
STATE_COMPLETED = "completed"
ORCHESTRATION_STATES = frozenset({
    STATE_DRAFT,
    STATE_STARTING,
    STATE_RUNNING,
    STATE_PAUSING,
    STATE_PAUSED,
    STATE_BLOCKED,
    STATE_COMPLETED,
})

SKIP_NONE = "none"
SKIP_REQUESTED = "requested"
SKIP_APPROVED = "approved"
SKIP_REJECTED = "rejected"
SKIP_STATUSES = frozenset({SKIP_NONE, SKIP_REQUESTED, SKIP_APPROVED, SKIP_REJECTED})

ACTIVE_TASK_STATES = frozenset({
    "validating",
    "executing",
    "retrying",
    "reviewing",
    "reworking",
    "execution_complete",
    "awaiting_user_acceptance",
    "awaiting_meeting_resolution",
})

ACCEPTED_TASK_STATES = frozenset({"done", "completed"})


@dataclass(frozen=True)
class OrchestrationIssue:
    code: str
    message: str
    task_id: str | None = None
    stage: int | None = None


@dataclass(frozen=True)
class StageValidation:
    ok: bool
    assignments: tuple[tuple[str, int], ...]
    stages: tuple[int, ...]
    issues: tuple[OrchestrationIssue, ...]


def default_orchestration_state() -> dict[str, Any]:
    return {
        "schemaVersion": ORCHESTRATION_SCHEMA_VERSION,
        "revision": 0,
        "state": STATE_DRAFT,
        "currentStage": None,
        "currentRunId": None,
        "pauseReason": None,
        "startedAt": None,
        "completedAt": None,
    }


def default_skip_state() -> dict[str, Any]:
    return {
        "status": SKIP_NONE,
        "requestedBy": None,
        "requestedAt": None,
        "reason": None,
        "decidedBy": None,
        "decidedAt": None,
    }


def is_marked_project(project: Mapping[str, Any]) -> bool:
    return project.get("executionModel") == EXECUTION_MODEL_STAGE_PIPELINE_V1


def orchestration_state(project: Mapping[str, Any]) -> dict[str, Any]:
    raw = project.get("orchestration")
    state = dict(raw) if isinstance(raw, Mapping) else {}
    base = default_orchestration_state()
    base.update(state)
    if base["state"] not in ORCHESTRATION_STATES:
        base["state"] = STATE_DRAFT
    if base["schemaVersion"] != ORCHESTRATION_SCHEMA_VERSION:
        base["schemaVersion"] = ORCHESTRATION_SCHEMA_VERSION
    try:
        base["revision"] = max(0, int(base.get("revision") or 0))
    except (TypeError, ValueError):
        base["revision"] = 0
    return base


def task_stage(task: Mapping[str, Any]) -> int | None:
    try:
        stage = int(task.get("executionStage") or 0)
    except (TypeError, ValueError):
        return None
    return stage if stage > 0 else None


def task_skip_state(task: Mapping[str, Any]) -> dict[str, Any]:
    raw = task.get("orchestrationSkip")
    state = dict(raw) if isinstance(raw, Mapping) else {}
    base = default_skip_state()
    base.update({key: state.get(key) for key in base if key in state})
    if base["status"] not in SKIP_STATUSES:
        base["status"] = SKIP_NONE
    return base


def task_has_approved_skip(task: Mapping[str, Any]) -> bool:
    return task_skip_state(task).get("status") == SKIP_APPROVED


def task_has_unresolved_skip(task: Mapping[str, Any]) -> bool:
    return task_skip_state(task).get("status") == SKIP_REQUESTED


def task_has_active_attempt(task: Mapping[str, Any]) -> bool:
    if task.get("activeAttemptId"):
        return True
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and attempt.get("status") in {
            "validating",
            "executing",
            "retrying",
            "reviewing",
            "reworking",
            "meeting_action_items",
        }:
            return True
    return False


def task_is_active(task: Mapping[str, Any]) -> bool:
    return task_has_active_attempt(task) or str(task.get("executionState") or "") in ACTIVE_TASK_STATES


def task_is_accepted_terminal(task: Mapping[str, Any]) -> bool:
    if task_has_approved_skip(task):
        return True
    if task.get("completedAt"):
        return True
    return str(task.get("executionState") or "").strip().lower() in ACCEPTED_TASK_STATES


def task_is_failed_or_blocked(task: Mapping[str, Any]) -> bool:
    if task_has_unresolved_skip(task):
        return True
    state = str(task.get("executionState") or "").strip().lower()
    return state in {"failed", "blocked"} or bool(task.get("blockedReason") or task.get("lastError"))


def active_task_ids(project: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(task.get("id"))
        for task in project.get("tasks") or []
        if isinstance(task, Mapping) and task.get("id") and task_is_active(task)
    )


def active_task_count(project: Mapping[str, Any]) -> int:
    return len(active_task_ids(project))


def tasks_by_stage(project: Mapping[str, Any]) -> dict[int, list[Task]]:
    grouped: dict[int, list[Task]] = {}
    for task in project.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        stage = task_stage(task)
        if stage is None:
            continue
        grouped.setdefault(stage, []).append(task)
    return grouped


def current_stage_tasks(project: Mapping[str, Any]) -> tuple[Task, ...]:
    stage = orchestration_state(project).get("currentStage")
    try:
        current = int(stage)
    except (TypeError, ValueError):
        return ()
    return tuple(tasks_by_stage(project).get(current, []))


def _assignment_pairs(assignments: Iterable[Mapping[str, Any]]) -> tuple[tuple[str, int | None], ...]:
    pairs: list[tuple[str, int | None]] = []
    for item in assignments:
        task_id = str(item.get("taskId") or item.get("id") or "")
        try:
            stage = int(item.get("executionStage") or 0)
        except (TypeError, ValueError):
            stage = None
        pairs.append((task_id, stage if stage and stage > 0 else None))
    return tuple(pairs)


def normalize_assignments(assignments: Iterable[Mapping[str, Any]]) -> StageValidation:
    issues: list[OrchestrationIssue] = []
    seen: set[str] = set()
    valid: list[tuple[str, int]] = []
    for task_id, stage in _assignment_pairs(assignments):
        if not task_id:
            issues.append(OrchestrationIssue("missing_task_id", "Assignment is missing taskId"))
            continue
        if task_id in seen:
            issues.append(OrchestrationIssue("duplicate_task_id", "Task appears more than once", task_id=task_id))
            continue
        seen.add(task_id)
        if stage is None:
            issues.append(OrchestrationIssue("invalid_execution_stage", "executionStage must be a positive integer", task_id=task_id))
            continue
        valid.append((task_id, stage))
    ordered_stages = sorted({stage for _, stage in valid})
    stage_map = {stage: index + 1 for index, stage in enumerate(ordered_stages)}
    normalized = tuple((task_id, stage_map[stage]) for task_id, stage in valid)
    return StageValidation(
        ok=not issues,
        assignments=normalized,
        stages=tuple(sorted(stage_map.values())),
        issues=tuple(issues),
    )


def validate_stage_invariants(project: Mapping[str, Any], *, require_marker: bool = True) -> StageValidation:
    issues: list[OrchestrationIssue] = []
    if require_marker and not is_marked_project(project):
        issues.append(OrchestrationIssue("missing_execution_model", "Project is not marked for stage-pipeline orchestration"))
    orchestration = project.get("orchestration")
    if require_marker and not isinstance(orchestration, Mapping):
        issues.append(OrchestrationIssue("missing_orchestration", "Project is missing orchestration state"))
    elif isinstance(orchestration, Mapping):
        if orchestration.get("schemaVersion") != ORCHESTRATION_SCHEMA_VERSION:
            issues.append(OrchestrationIssue("invalid_orchestration_schema", "Unsupported orchestration schema version"))
        if orchestration.get("state") not in ORCHESTRATION_STATES:
            issues.append(OrchestrationIssue("invalid_orchestration_state", "Unsupported orchestration state"))

    tasks = [task for task in project.get("tasks") or [] if isinstance(task, Mapping)]
    seen: set[str] = set()
    assignments: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        if not task_id:
            issues.append(OrchestrationIssue("missing_task_id", "Task is missing id"))
            continue
        if task_id in seen:
            issues.append(OrchestrationIssue("duplicate_task_id", "Task id is duplicated", task_id=task_id))
        seen.add(task_id)
        stage = task_stage(task)
        if stage is None:
            issues.append(OrchestrationIssue("invalid_execution_stage", "Task is missing a positive executionStage", task_id=task_id))
        else:
            assignments.append({"taskId": task_id, "executionStage": stage})
        skip_status = task_skip_state(task).get("status")
        if skip_status not in SKIP_STATUSES:
            issues.append(OrchestrationIssue("invalid_skip_status", "Unsupported orchestration skip status", task_id=task_id))

    normalized = normalize_assignments(assignments)
    current_assignments = tuple((str(item["taskId"]), int(item["executionStage"])) for item in assignments)
    if normalized.assignments != current_assignments:
        issues.append(OrchestrationIssue("non_contiguous_stages", "Occupied execution stages must be contiguous from 1"))
    return StageValidation(
        ok=not issues,
        assignments=current_assignments,
        stages=tuple(sorted({stage for _, stage in current_assignments})),
        issues=tuple(issues),
    )


def last_completed_stage(project: Mapping[str, Any]) -> int:
    completed = 0
    for stage in sorted(tasks_by_stage(project)):
        tasks = tasks_by_stage(project)[stage]
        if tasks and all(task_is_accepted_terminal(task) for task in tasks):
            completed = stage
            continue
        break
    return completed


def validate_completed_stage_locks(
    project: Mapping[str, Any],
    proposed_assignments: Iterable[Mapping[str, Any]],
) -> tuple[OrchestrationIssue, ...]:
    proposed = {
        task_id: stage
        for task_id, stage in _assignment_pairs(proposed_assignments)
        if task_id and stage is not None
    }
    locked_floor = last_completed_stage(project)
    issues: list[OrchestrationIssue] = []
    for task in project.get("tasks") or []:
        if not isinstance(task, Mapping) or not task.get("id"):
            continue
        current_stage = task_stage(task)
        task_id = str(task.get("id"))
        proposed_stage = proposed.get(task_id)
        if current_stage is None or proposed_stage is None:
            continue
        if current_stage <= locked_floor and proposed_stage != current_stage:
            issues.append(
                OrchestrationIssue(
                    "completed_stage_locked",
                    "Completed stage tasks cannot be reassigned",
                    task_id=task_id,
                    stage=current_stage,
                )
            )
    return tuple(issues)


def compact_stages_after_removal(project: Mapping[str, Any], removed_task_id: str) -> tuple[tuple[str, int], ...]:
    """Return contiguous assignments for remaining tasks after one task is removed."""

    removed = str(removed_task_id or "")
    remaining = [
        task
        for task in project.get("tasks") or []
        if isinstance(task, Mapping) and str(task.get("id") or "") != removed
    ]
    assignments = [
        {"taskId": str(task.get("id")), "executionStage": task_stage(task)}
        for task in remaining
        if task.get("id") and task_stage(task) is not None
    ]
    return normalize_assignments(assignments).assignments


def next_unfinished_stage(project: Mapping[str, Any]) -> int | None:
    for stage in sorted(tasks_by_stage(project)):
        tasks = tasks_by_stage(project)[stage]
        if any(not task_is_accepted_terminal(task) for task in tasks):
            return stage
    return None


def stage_has_failed_or_blocked_task(project: Mapping[str, Any], stage: int) -> bool:
    return any(task_is_failed_or_blocked(task) for task in tasks_by_stage(project).get(stage, []))


def stage_has_accepted_terminal_outcomes(project: Mapping[str, Any], stage: int) -> bool:
    tasks = tasks_by_stage(project).get(stage, [])
    return bool(tasks) and all(task_is_accepted_terminal(task) for task in tasks)


def project_projection(project: Mapping[str, Any]) -> dict[str, Any]:
    state = orchestration_state(project)
    active_ids = active_task_ids(project)
    return {
        "executionModel": project.get("executionModel"),
        "orchestrationState": state["state"],
        "currentStage": state["currentStage"],
        "pauseReason": state["pauseReason"],
        "activeTaskIds": list(active_ids),
        "activeTaskCount": len(active_ids),
    }
