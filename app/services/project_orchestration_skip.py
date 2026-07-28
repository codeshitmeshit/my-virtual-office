"""Repository-backed orchestration skip requests and decisions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_execution import ServiceResult
from .project_orchestration import (
    SKIP_APPROVED,
    SKIP_REJECTED,
    SKIP_REQUESTED,
    default_skip_state,
    is_marked_project,
    orchestration_state,
    task_skip_state,
)
from .project_orchestration_observability import append_project_audit, skip_decision_diagnostics
from .project_repository import ProjectConflictError, ProjectNotFoundError, ProjectRepository
from .project_stage_dispatch import StageReconciliationOutcome, reconcile_stage
from .project_task_final_result import ensure_task_final_result


@dataclass(frozen=True)
class SkipCommandOutcome:
    result: ServiceResult
    post_commit: Mapping[str, Any] | None = None
    reconciliation: StageReconciliationOutcome | None = None


@dataclass(frozen=True)
class SkipPorts:
    now: Callable[[], str]
    management_authorize: Callable[[dict[str, Any], Mapping[str, Any]], dict[str, Any]]
    new_run_id: Callable[[], str]
    on_project_completed: Callable[[dict[str, Any], str], Any] | None = None


class _SkipCommandRejected(RuntimeError):
    def __init__(self, status: int, payload: Mapping[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload.get("code") or "skip command rejected"))
        self.status = status
        self.payload = dict(payload)


def request_task_skip(
    project_id: str,
    task_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    ports: SkipPorts,
) -> SkipCommandOutcome:
    """Record a responsible actor's request to skip one orchestration task."""

    body = body or {}
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return SkipCommandOutcome(ServiceResult(400, {
            "ok": False,
            "code": "skip_reason_required",
            "error": "Skip request requires a reason",
        }))
    actor = _actor(body)
    outcome: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> None:
        task = _task(project, task_id)
        _validate_marked_project_task(project, task)
        if not _responsible_actor_matches(task, actor):
            _reject(403, ok=False, code="skip_request_forbidden", error="Only the responsible task actor may request a skip")
        skip = task_skip_state(task)
        if skip.get("status") == SKIP_APPROVED:
            _reject(409, ok=False, code="skip_already_approved", error="Task skip is already approved")
        timestamp = ports.now()
        if skip.get("status") == SKIP_REQUESTED:
            skip.update({
                "requestedBy": actor,
                "requestedAt": skip.get("requestedAt") or timestamp,
                "reason": reason,
            })
            idempotent = True
        else:
            skip = default_skip_state()
            skip.update({
                "status": SKIP_REQUESTED,
                "requestedBy": actor,
                "requestedAt": timestamp,
                "reason": reason,
            })
            idempotent = False
        _append_history(task, {
            "action": "requested",
            "by": actor,
            "at": timestamp,
            "reason": reason,
            "idempotent": idempotent,
        })
        task["orchestrationSkip"] = skip
        task["updatedAt"] = timestamp
        project["updatedAt"] = timestamp
        outcome.update({"project": copy.deepcopy(project), "task": copy.deepcopy(task), "skip": copy.deepcopy(skip), "idempotent": idempotent})

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return SkipCommandOutcome(ServiceResult(404, {"ok": False, "error": "Project or task not found"}))
    except _SkipCommandRejected as exc:
        return SkipCommandOutcome(ServiceResult(exc.status, exc.payload))
    except ProjectConflictError:
        return SkipCommandOutcome(ServiceResult(409, {
            "ok": False,
            "code": "skip_request_commit_conflict",
            "error": "Project changed during skip request",
        }))
    return SkipCommandOutcome(ServiceResult(200, {
        "ok": True,
        "status": "skip_requested",
        "taskId": task_id,
        "orchestrationSkip": outcome["skip"],
        "idempotent": outcome["idempotent"],
    }), outcome)


def decide_task_skip(
    project_id: str,
    task_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    ports: SkipPorts,
) -> SkipCommandOutcome:
    """Approve or reject one pending orchestration skip request."""

    body = body or {}
    decision = str(body.get("decision") or body.get("action") or "").strip().lower()
    if decision not in {"approve", "approved", "reject", "rejected"}:
        return SkipCommandOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_skip_decision",
            "error": "Skip decision must be approve or reject",
        }))
    approved = decision in {"approve", "approved"}
    actor = _actor(body)
    reason = str(body.get("reason") or body.get("decisionReason") or "").strip()
    outcome: dict[str, Any] = {}
    run_id_box: dict[str, str] = {}

    def mutate(project: dict[str, Any]) -> None:
        task = _task(project, task_id)
        _validate_marked_project_task(project, task)
        authorization = ports.management_authorize(project, actor)
        if not authorization.get("ok"):
            _reject(
                403,
                ok=False,
                code=str(authorization.get("code") or "skip_decision_forbidden"),
                error=str(authorization.get("error") or "Skip decisions require orchestration authority"),
            )
        skip = task_skip_state(task)
        timestamp = ports.now()
        current_status = skip.get("status")
        target_status = SKIP_APPROVED if approved else SKIP_REJECTED
        if current_status == target_status:
            outcome.update({"idempotent": True})
        elif current_status != SKIP_REQUESTED:
            _reject(409, ok=False, code="skip_request_not_pending", error="Skip decision requires a pending skip request")
        else:
            outcome.update({"idempotent": False})
        skip.update({
            "status": target_status,
            "decidedBy": actor,
            "decidedAt": skip.get("decidedAt") if outcome.get("idempotent") else timestamp,
        })
        if reason:
            skip["decisionReason"] = reason
        _append_history(task, {
            "action": "approved" if approved else "rejected",
            "by": actor,
            "at": timestamp,
            "reason": reason,
            "idempotent": bool(outcome.get("idempotent")),
        })
        task["orchestrationSkip"] = skip
        if approved:
            ensure_task_final_result(project, task, status="skipped", now=timestamp)
        task["updatedAt"] = timestamp
        project["updatedAt"] = timestamp
        if approved:
            run_id = str(orchestration_state(project).get("currentRunId") or "")
            if run_id and _same_current_stage(project, task):
                run_id_box["runId"] = run_id
        state = orchestration_state(project)
        diagnostics = skip_decision_diagnostics(
            project_id=str(project.get("id") or project_id),
            task_id=str(task.get("id") or task_id),
            stage=_int_or_none(task.get("executionStage")),
            run_id=str(state.get("currentRunId") or "") or None,
            attempt_id=str(task.get("activeAttemptId") or "") or None,
            revision=int(state.get("revision") or 0),
            status=target_status,
            approved=approved,
        )
        append_project_audit(project, diagnostics, at=timestamp)
        outcome.update({"project": copy.deepcopy(project), "task": copy.deepcopy(task), "skip": copy.deepcopy(skip), "diagnostics": diagnostics})

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return SkipCommandOutcome(ServiceResult(404, {"ok": False, "error": "Project or task not found"}))
    except _SkipCommandRejected as exc:
        return SkipCommandOutcome(ServiceResult(exc.status, exc.payload))
    except ProjectConflictError:
        return SkipCommandOutcome(ServiceResult(409, {
            "ok": False,
            "code": "skip_decision_commit_conflict",
            "error": "Project changed during skip decision",
        }))

    reconciliation = None
    if approved and run_id_box.get("runId"):
        reconciliation = reconcile_stage(
            project_id,
            run_id_box["runId"],
            repository=repository,
            now=ports.now,
            new_run_id=ports.new_run_id,
            on_project_completed=ports.on_project_completed,
        )
    return SkipCommandOutcome(ServiceResult(200, {
        "ok": True,
        "status": "skip_approved" if approved else "skip_rejected",
        "taskId": task_id,
        "orchestrationSkip": outcome["skip"],
        "idempotent": bool(outcome.get("idempotent")),
        "reconciliation": dict(reconciliation.result.payload) if reconciliation else None,
        "diagnostics": outcome["diagnostics"],
    }), outcome, reconciliation)


def _task(project: Mapping[str, Any], task_id: str) -> dict[str, Any] | None:
    return next((task for task in project.get("tasks") or [] if isinstance(task, dict) and str(task.get("id") or "") == str(task_id)), None)


def _validate_marked_project_task(project: Mapping[str, Any], task: Mapping[str, Any] | None) -> None:
    if task is None:
        _reject(404, ok=False, error="Project or task not found")
    if not is_marked_project(project):
        _reject(409, ok=False, code="missing_execution_model", error="Project is not marked for stage-pipeline orchestration")


def _actor(body: Mapping[str, Any]) -> dict[str, Any]:
    raw = body.get("actor")
    if isinstance(raw, Mapping):
        return {"type": str(raw.get("type") or ""), "id": str(raw.get("id") or "")}
    return {"type": str(body.get("actorType") or ""), "id": str(body.get("by") or body.get("actorId") or "")}


def _responsible_actor_matches(task: Mapping[str, Any], actor: Mapping[str, Any]) -> bool:
    actor_id = str(actor.get("id") or "")
    if not actor_id:
        return False
    candidates = [
        task.get("responsibleAgentId"),
        task.get("executorAgentId"),
        task.get("assignee"),
    ]
    for key in ("responsibleActor", "executorActor"):
        raw = task.get(key)
        if isinstance(raw, Mapping):
            candidates.append(raw.get("id"))
    return actor_id in {str(item) for item in candidates if item}


def _same_current_stage(project: Mapping[str, Any], task: Mapping[str, Any]) -> bool:
    try:
        return int(task.get("executionStage") or 0) == int(orchestration_state(project).get("currentStage") or 0)
    except (TypeError, ValueError):
        return False


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _append_history(task: dict[str, Any], entry: Mapping[str, Any]) -> None:
    task.setdefault("orchestrationSkipHistory", []).append(dict(entry))
    task["orchestrationSkipHistory"] = task["orchestrationSkipHistory"][-50:]


def _reject(status: int, **payload: Any) -> None:
    raise _SkipCommandRejected(status, payload)


__all__ = [
    "SkipCommandOutcome",
    "SkipPorts",
    "decide_task_skip",
    "request_task_skip",
]
