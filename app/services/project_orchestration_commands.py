"""Repository-backed commands for project task orchestration edits."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_execution import ServiceResult
from .project_orchestration import (
    STATE_DRAFT,
    STATE_PAUSED,
    is_marked_project,
    last_completed_stage,
    normalize_assignments,
    orchestration_state,
    task_is_accepted_terminal,
    task_stage,
    validate_completed_stage_locks,
)
from .project_orchestration_observability import (
    append_project_audit,
    autosave_conflict_diagnostics,
    elapsed_ms,
    monotonic_ms,
    operation_diagnostics,
)
from .project_repository import ProjectConflictError, ProjectNotFoundError, ProjectRepository


EDITABLE_ORCHESTRATION_STATES = frozenset({STATE_DRAFT, STATE_PAUSED})


@dataclass(frozen=True)
class OrchestrationCommandOutcome:
    result: ServiceResult
    post_commit: Mapping[str, Any] | None = None


class _OrchestrationCommandRejected(RuntimeError):
    def __init__(self, status: int, payload: Mapping[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload.get("code") or "orchestration rejected"))
        self.status = status
        self.payload = dict(payload)


def _current_assignments(project: Mapping[str, Any]) -> list[dict[str, Any]]:
    assignments = []
    for task in project.get("tasks") or []:
        if not isinstance(task, Mapping) or not task.get("id"):
            continue
        stage = task_stage(task)
        if stage is not None:
            assignments.append({"taskId": str(task["id"]), "executionStage": stage})
    normalized = normalize_assignments(assignments)
    if not normalized.ok:
        return assignments
    by_task = {task_id: stage for task_id, stage in normalized.assignments}
    return [
        {"taskId": str(task["id"]), "executionStage": by_task[str(task["id"])]}
        for task in project.get("tasks") or []
        if isinstance(task, Mapping) and task.get("id") and str(task["id"]) in by_task
    ]


def _assignment_error_payload(project: Mapping[str, Any], received: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    task_ids = [
        str(task.get("id") or "")
        for task in project.get("tasks") or []
        if isinstance(task, Mapping) and task.get("id")
    ]
    expected = set(task_ids)
    seen: set[str] = set()
    duplicate: set[str] = set()
    provided: set[str] = set()
    for assignment in received:
        task_id = str(assignment.get("taskId") or assignment.get("id") or "")
        if task_id in seen:
            duplicate.add(task_id)
        seen.add(task_id)
        if task_id:
            provided.add(task_id)
    missing = sorted(expected - provided)
    unknown = sorted(provided - expected)
    if duplicate:
        return {
            "ok": False,
            "code": "duplicate_orchestration_assignment",
            "error": "Each task may appear only once in orchestration assignments",
            "duplicateTaskIds": sorted(duplicate),
        }
    if missing or unknown or len(provided) != len(received):
        return {
            "ok": False,
            "code": "incomplete_orchestration_assignment",
            "error": "Orchestration auto-save requires one assignment for every project task",
            "missingTaskIds": missing,
            "unknownTaskIds": unknown,
        }
    return None


def _validate_revision(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        revision = int(value)
    except (TypeError, ValueError):
        return None
    return revision if revision >= 0 else None


def _reject(status: int, **payload: Any) -> None:
    raise _OrchestrationCommandRejected(status, payload)


def _normalized_assignments_for_project(
    project: Mapping[str, Any],
    received: list[Mapping[str, Any]],
    *,
    paused: bool,
) -> tuple[tuple[str, int], ...]:
    if not paused:
        normalized = normalize_assignments(received)
        if not normalized.ok:
            _reject(
                400,
                ok=False,
                code="invalid_orchestration_assignment",
                error="Assignments must contain positive executionStage values and valid task ids",
                issues=[issue.__dict__ for issue in normalized.issues],
            )
        return normalized.assignments

    locked_floor = last_completed_stage(project)
    locked_assignments: list[tuple[str, int]] = []
    unfinished_received: list[Mapping[str, Any]] = []
    tasks_by_id = {
        str(task.get("id") or ""): task
        for task in project.get("tasks") or []
        if isinstance(task, Mapping) and task.get("id")
    }
    for assignment in received:
        task_id = str(assignment.get("taskId") or assignment.get("id") or "")
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        current_stage = task_stage(task)
        if task_is_accepted_terminal(task) and current_stage is not None and current_stage <= locked_floor:
            locked_assignments.append((task_id, current_stage))
            continue
        unfinished_received.append(assignment)

    normalized_unfinished = normalize_assignments(unfinished_received)
    if not normalized_unfinished.ok:
        _reject(
            400,
            ok=False,
            code="invalid_orchestration_assignment",
            error="Assignments must contain positive executionStage values and valid task ids",
            issues=[issue.__dict__ for issue in normalized_unfinished.issues],
        )
    unfinished_by_task = {
        task_id: stage + locked_floor
        for task_id, stage in normalized_unfinished.assignments
    }
    locked_by_task = dict(locked_assignments)
    ordered: list[tuple[str, int]] = []
    for task in project.get("tasks") or []:
        if not isinstance(task, Mapping) or not task.get("id"):
            continue
        task_id = str(task["id"])
        if task_id in locked_by_task:
            ordered.append((task_id, locked_by_task[task_id]))
        elif task_id in unfinished_by_task:
            ordered.append((task_id, unfinished_by_task[task_id]))
    return tuple(ordered)


def autosave_orchestration(
    project_id: str,
    body: Mapping[str, Any],
    *,
    repository: ProjectRepository,
    now: Callable[[], str],
) -> OrchestrationCommandOutcome:
    """Persist one complete task-stage assignment with optimistic revision checks."""

    started_ms = monotonic_ms()
    expected_revision = _validate_revision(body.get("revision"))
    if expected_revision is None:
        return OrchestrationCommandOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_orchestration_revision",
            "error": "revision must be a non-negative integer",
        }))
    raw_assignments = body.get("assignments")
    if not isinstance(raw_assignments, list):
        return OrchestrationCommandOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_orchestration_assignments",
            "error": "assignments must be an array",
        }))
    received = [
        copy.deepcopy(dict(item))
        for item in raw_assignments
        if isinstance(item, Mapping)
    ]
    if len(received) != len(raw_assignments):
        return OrchestrationCommandOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_orchestration_assignments",
            "error": "Every assignment must be an object",
        }))

    outcome: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> None:
        if not is_marked_project(project):
            _reject(400, ok=False, code="missing_execution_model", error="Project is not marked for stage-pipeline orchestration")
        state = orchestration_state(project)
        current_revision = int(state.get("revision") or 0)
        if current_revision != expected_revision:
            diagnostics = autosave_conflict_diagnostics(
                project_id=str(project.get("id") or project_id),
                revision=expected_revision,
                current_revision=current_revision,
            )
            _reject(
                409,
                ok=False,
                code="orchestration_revision_conflict",
                error="Orchestration revision changed",
                expectedRevision=expected_revision,
                currentRevision=current_revision,
                orchestration=state,
                assignments=_current_assignments(project),
                diagnostics=diagnostics,
            )
        if state.get("state") not in EDITABLE_ORCHESTRATION_STATES:
            _reject(
                409,
                ok=False,
                code="orchestration_not_editable",
                error="Orchestration can only be edited while draft or paused",
                orchestrationState=state.get("state"),
                currentRevision=current_revision,
                assignments=_current_assignments(project),
            )
        if coverage_error := _assignment_error_payload(project, received):
            _reject(400, **coverage_error)

        lock_issues = validate_completed_stage_locks(project, received)
        if lock_issues:
            _reject(
                409,
                ok=False,
                code="completed_stage_locked",
                error="Completed stage tasks cannot be reassigned",
                issues=[issue.__dict__ for issue in lock_issues],
                currentRevision=current_revision,
                assignments=_current_assignments(project),
            )
        normalized_assignments = _normalized_assignments_for_project(
            project,
            received,
            paused=state.get("state") == STATE_PAUSED,
        )
        by_task_id = {task_id: stage for task_id, stage in normalized_assignments}
        timestamp = now()
        for task in project.get("tasks") or []:
            if not isinstance(task, dict) or not task.get("id"):
                continue
            task_id = str(task["id"])
            task["executionStage"] = by_task_id[task_id]
            task["updatedAt"] = timestamp
        state["revision"] = current_revision + 1
        project["orchestration"] = state
        project["updatedAt"] = timestamp
        saved_assignments = _current_assignments(project)
        diagnostics = operation_diagnostics(
            "autoSave",
            "saved",
            project_id=str(project.get("id") or project_id),
            revision=int(state.get("revision") or 0),
            counters={"autoSaves": 1},
            timings={"autoSaveMs": elapsed_ms(started_ms)},
            fields={"assignmentCount": len(saved_assignments)},
        )
        append_project_audit(project, diagnostics, at=timestamp)
        outcome.update({
            "project": copy.deepcopy(project),
            "orchestration": copy.deepcopy(state),
            "assignments": saved_assignments,
            "diagnostics": diagnostics,
        })

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return OrchestrationCommandOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    except _OrchestrationCommandRejected as exc:
        return OrchestrationCommandOutcome(ServiceResult(exc.status, exc.payload))
    except ProjectConflictError:
        return OrchestrationCommandOutcome(ServiceResult(409, {
            "ok": False,
            "code": "orchestration_commit_conflict",
            "error": "Project changed during orchestration auto-save",
        }))
    return OrchestrationCommandOutcome(ServiceResult(200, {
        "ok": True,
        "project": outcome["project"],
        "orchestration": outcome["orchestration"],
        "assignments": outcome["assignments"],
        "diagnostics": outcome["diagnostics"],
    }), outcome)
