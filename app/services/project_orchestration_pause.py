"""Repository-backed pause commands for stage-pipeline projects."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_execution import ServiceResult
from .project_orchestration import (
    STATE_BLOCKED,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_RUNNING,
    STATE_STARTING,
    task_is_accepted_terminal,
    is_marked_project,
    orchestration_state,
    task_has_active_attempt,
    task_stage,
    validate_stage_invariants,
)
from .project_orchestration_observability import append_project_audit, elapsed_ms, monotonic_ms, pause_diagnostics
from .project_repository import ProjectConflictError, ProjectNotFoundError, ProjectRepository


PAUSE_ALLOWED_STATES = frozenset({STATE_STARTING, STATE_RUNNING, STATE_BLOCKED})
PAUSE_ACTIVE_ATTEMPT_STATUSES = frozenset({
    "validating",
    "executing",
    "retrying",
    "reviewing",
    "reworking",
    "meeting_action_items",
    "cancelling",
})


@dataclass(frozen=True)
class PausePorts:
    now: Callable[[], str]
    authorize: Callable[[dict[str, Any], Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class PauseCancellationPorts:
    now: Callable[[], str]
    cancel_attempt: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    transition: Callable[[dict[str, Any], dict[str, Any], str, str, str, str | None], Any]


@dataclass(frozen=True)
class PauseCommandOutcome:
    result: ServiceResult
    post_commit: Mapping[str, Any] | None = None


class _PauseCommandRejected(RuntimeError):
    def __init__(self, status: int, payload: Mapping[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload.get("code") or "pause rejected"))
        self.status = status
        self.payload = dict(payload)


def request_phase_one_pause(
    project_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    ports: PausePorts,
) -> PauseCommandOutcome:
    """Atomically enter pausing and snapshot active attempts before cancellation."""

    started_ms = monotonic_ms()
    body = body or {}
    if not _confirmed(body):
        return PauseCommandOutcome(ServiceResult(400, {
            "ok": False,
            "code": "pause_confirmation_required",
            "error": "Pause and re-orchestration requires explicit confirmation",
        }))
    actor = _actor(body)
    reason = str(body.get("reason") or "pause_reorchestration_requested").strip() or "pause_reorchestration_requested"
    outcome: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> None:
        if not is_marked_project(project):
            _reject(409, ok=False, code="missing_execution_model", error="Project is not marked for stage-pipeline orchestration")
        validation = validate_stage_invariants(project)
        if not validation.ok:
            _reject(
                409,
                ok=False,
                code=validation.issues[0].code if validation.issues else "invalid_orchestration",
                error="Project orchestration invariants are invalid",
                issues=[issue.__dict__ for issue in validation.issues],
            )
        authorization = ports.authorize(project, actor)
        if not authorization.get("ok"):
            _reject(
                403,
                ok=False,
                code=str(authorization.get("code") or "pause_forbidden"),
                error=str(authorization.get("error") or "Pause requires project orchestration authority"),
            )

        state = orchestration_state(project)
        current_state = str(state.get("state") or "")
        if current_state == STATE_PAUSING:
            snapshot = _existing_pause_snapshot(state)
            diagnostics = pause_diagnostics(
                project_id=str(project.get("id") or project_id),
                stage=_int_or_none(state.get("currentStage")),
                run_id=str(state.get("currentRunId") or "") or None,
                revision=int(state.get("revision") or 0),
                status="already_pausing",
                attempt_ids=snapshot.get("activeAttemptIds") or [],
                duration_ms=elapsed_ms(started_ms),
            )
            outcome.update({
                "project": copy.deepcopy(project),
                "orchestration": copy.deepcopy(state),
                "snapshot": copy.deepcopy(snapshot),
                "idempotent": True,
                "diagnostics": diagnostics,
            })
            return
        if current_state not in PAUSE_ALLOWED_STATES:
            _reject(
                409,
                ok=False,
                code="orchestration_not_pausable",
                error="Only starting, running, or blocked orchestration can enter pausing",
                orchestrationState=current_state,
            )

        timestamp = ports.now()
        snapshot = _build_pause_snapshot(project, state, actor=actor, reason=reason, requested_at=timestamp)
        state.update({
            "state": STATE_PAUSING,
            "pauseReason": reason,
            "pauseSnapshot": snapshot,
            "revision": int(state.get("revision") or 0) + 1,
        })
        project["orchestration"] = state
        project["updatedAt"] = timestamp
        diagnostics = pause_diagnostics(
            project_id=str(project.get("id") or project_id),
            stage=_int_or_none(state.get("currentStage")),
            run_id=str(state.get("currentRunId") or "") or None,
            revision=int(state.get("revision") or 0),
            status="pausing",
            attempt_ids=snapshot.get("activeAttemptIds") or [],
            duration_ms=elapsed_ms(started_ms),
        )
        append_project_audit(project, diagnostics, at=timestamp)
        outcome.update({
            "project": copy.deepcopy(project),
            "orchestration": copy.deepcopy(state),
            "snapshot": copy.deepcopy(snapshot),
            "idempotent": False,
            "diagnostics": diagnostics,
        })

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return PauseCommandOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    except _PauseCommandRejected as exc:
        return PauseCommandOutcome(ServiceResult(exc.status, exc.payload))
    except ProjectConflictError:
        return PauseCommandOutcome(ServiceResult(409, {
            "ok": False,
            "code": "pause_commit_conflict",
            "error": "Project changed during phase-one pause",
        }))

    return PauseCommandOutcome(ServiceResult(200, {
        "ok": True,
        "status": "pausing",
        "project": outcome["project"],
        "orchestration": outcome["orchestration"],
        "pauseSnapshot": outcome["snapshot"],
        "activeAttemptIds": outcome["snapshot"].get("activeAttemptIds", []),
        "idempotent": bool(outcome["idempotent"]),
        "diagnostics": outcome["diagnostics"],
    }), outcome)


def complete_phase_two_pause(
    project_id: str,
    *,
    repository: ProjectRepository,
    ports: PauseCancellationPorts,
) -> PauseCommandOutcome:
    """Cancel captured attempts outside the lock, then atomically enter paused."""

    started_ms = monotonic_ms()
    snapshot_project = repository.get(project_id)
    if snapshot_project is None:
        return PauseCommandOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    state = orchestration_state(snapshot_project)
    current_state = str(state.get("state") or "")
    if current_state == STATE_PAUSED:
        snapshot = _existing_pause_snapshot(state)
        return PauseCommandOutcome(ServiceResult(200, {
            "ok": True,
            "status": "paused",
            "orchestration": state,
            "pauseSnapshot": snapshot,
            "cancelResults": list(snapshot.get("cancelResults") or []),
            "idempotent": True,
            "diagnostics": pause_diagnostics(
                project_id=project_id,
                stage=_int_or_none(state.get("currentStage")),
                run_id=str(state.get("currentRunId") or "") or None,
                revision=int(state.get("revision") or 0),
                status="already_paused",
                attempt_ids=snapshot.get("activeAttemptIds") or [],
                duration_ms=elapsed_ms(started_ms),
            ),
        }))
    if current_state != STATE_PAUSING:
        return PauseCommandOutcome(ServiceResult(409, {
            "ok": False,
            "code": "orchestration_not_pausing",
            "error": "Phase-two pause convergence requires a pausing project",
            "orchestrationState": current_state,
        }))

    snapshot = _existing_pause_snapshot(state)
    captured_attempts = _snapshot_attempts(snapshot)
    cancel_results = [_cancel_snapshot_attempt(item, ports) for item in captured_attempts]
    failed = [item for item in cancel_results if not item.get("ok")]
    if failed:
        return PauseCommandOutcome(ServiceResult(409, {
            "ok": False,
            "status": "pausing",
            "code": "pause_cancellation_failed",
            "error": "One or more active attempts could not be cancelled",
            "cancelResults": cancel_results,
            "diagnostics": pause_diagnostics(
                project_id=project_id,
                stage=_int_or_none(state.get("currentStage")),
                run_id=str(state.get("currentRunId") or "") or None,
                revision=int(state.get("revision") or 0),
                status="cancellation_failed",
                attempt_ids=[item.get("attemptId") for item in captured_attempts],
                duration_ms=elapsed_ms(started_ms),
            ),
        }), {"cancelResults": cancel_results})

    outcome: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> None:
        if not is_marked_project(project):
            _reject(409, ok=False, code="missing_execution_model", error="Project is not marked for stage-pipeline orchestration")
        latest_state = orchestration_state(project)
        if latest_state.get("state") == STATE_PAUSED:
            latest_snapshot = _existing_pause_snapshot(latest_state)
            diagnostics = pause_diagnostics(
                project_id=str(project.get("id") or project_id),
                stage=_int_or_none(latest_state.get("currentStage")),
                run_id=str(latest_state.get("currentRunId") or "") or None,
                revision=int(latest_state.get("revision") or 0),
                status="already_paused",
                attempt_ids=latest_snapshot.get("activeAttemptIds") or [],
                duration_ms=elapsed_ms(started_ms),
            )
            outcome.update({
                "project": copy.deepcopy(project),
                "orchestration": copy.deepcopy(latest_state),
                "snapshot": copy.deepcopy(latest_snapshot),
                "cancelResults": list(latest_snapshot.get("cancelResults") or cancel_results),
                "idempotent": True,
                "diagnostics": diagnostics,
            })
            return
        if latest_state.get("state") != STATE_PAUSING:
            _reject(
                409,
                ok=False,
                code="orchestration_not_pausing",
                error="Phase-two pause convergence requires a pausing project",
                orchestrationState=latest_state.get("state"),
            )
        latest_snapshot = _existing_pause_snapshot(latest_state)
        latest_captured = _snapshot_attempts(latest_snapshot)
        timestamp = ports.now()
        by_key = {(item["taskId"], item["attemptId"]): item for item in cancel_results}
        cancelled_attempts: list[dict[str, Any]] = []
        for captured in latest_captured:
            task = _find_task(project, captured["taskId"])
            if task is None:
                continue
            attempt = _attempt(task, captured["attemptId"])
            if attempt is not None:
                result = by_key.get((captured["taskId"], captured["attemptId"]), {"ok": True, "status": "stale"})
                attempt.update({
                    "status": "cancelled",
                    "cancelledAt": attempt.get("cancelledAt") or timestamp,
                    "finishedAt": attempt.get("finishedAt") or timestamp,
                    "cancelResult": copy.deepcopy(result),
                })
                cancelled_attempts.append({
                    "taskId": captured["taskId"],
                    "attemptId": captured["attemptId"],
                    "status": "cancelled",
                })
            if str(task.get("activeAttemptId") or "") == captured["attemptId"]:
                task["activeAttemptId"] = None
            if not task_is_accepted_terminal(task):
                task["stageRunId"] = None
                task["blockedReason"] = None
                task["lastError"] = None
                task["updatedAt"] = timestamp
                ports.transition(
                    project,
                    task,
                    "pending",
                    "stage-pause",
                    "Project pause cancelled active execution; task will restart from scratch on resume.",
                    captured["attemptId"],
                )
                task["executionState"] = "pending"
        latest_snapshot["cancelResults"] = cancel_results
        latest_snapshot["cancelledAttempts"] = cancelled_attempts
        latest_snapshot["convergedAt"] = timestamp
        latest_state.update({
            "state": STATE_PAUSED,
            "currentRunId": None,
            "pauseSnapshot": latest_snapshot,
            "revision": int(latest_state.get("revision") or 0) + 1,
        })
        project["orchestration"] = latest_state
        project["updatedAt"] = timestamp
        diagnostics = pause_diagnostics(
            project_id=str(project.get("id") or project_id),
            stage=_int_or_none(latest_state.get("currentStage")),
            run_id=str(latest_state.get("currentRunId") or "") or None,
            revision=int(latest_state.get("revision") or 0),
            status="paused",
            attempt_ids=[item.get("attemptId") for item in cancelled_attempts],
            duration_ms=elapsed_ms(started_ms),
        )
        append_project_audit(project, diagnostics, at=timestamp)
        outcome.update({
            "project": copy.deepcopy(project),
            "orchestration": copy.deepcopy(latest_state),
            "snapshot": copy.deepcopy(latest_snapshot),
            "cancelResults": cancel_results,
            "idempotent": False,
            "diagnostics": diagnostics,
        })

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return PauseCommandOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    except _PauseCommandRejected as exc:
        return PauseCommandOutcome(ServiceResult(exc.status, exc.payload))
    except ProjectConflictError:
        return PauseCommandOutcome(ServiceResult(409, {
            "ok": False,
            "code": "pause_convergence_commit_conflict",
            "error": "Project changed during phase-two pause convergence",
        }))

    return PauseCommandOutcome(ServiceResult(200, {
        "ok": True,
        "status": "paused",
        "project": outcome["project"],
        "orchestration": outcome["orchestration"],
        "pauseSnapshot": outcome["snapshot"],
        "cancelResults": outcome["cancelResults"],
        "idempotent": bool(outcome["idempotent"]),
        "diagnostics": outcome["diagnostics"],
    }), outcome)


def _confirmed(body: Mapping[str, Any]) -> bool:
    return body.get("confirm") is True or body.get("confirmed") is True or body.get("confirmPause") is True


def _actor(body: Mapping[str, Any]) -> dict[str, Any]:
    raw = body.get("actor")
    if isinstance(raw, Mapping):
        return {"type": str(raw.get("type") or ""), "id": str(raw.get("id") or "")}
    return {"type": str(body.get("actorType") or "management"), "id": str(body.get("by") or body.get("actorId") or "management")}


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _build_pause_snapshot(
    project: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    actor: Mapping[str, Any],
    reason: str,
    requested_at: str,
) -> dict[str, Any]:
    active_attempts = []
    for task in project.get("tasks") or []:
        if not isinstance(task, Mapping) or not task_has_active_attempt(task):
            continue
        attempt_id = str(task.get("activeAttemptId") or "")
        attempt = _attempt(task, attempt_id)
        if not attempt_id and attempt is not None:
            attempt_id = str(attempt.get("id") or "")
        if not attempt_id:
            continue
        active_attempts.append({
            "taskId": str(task.get("id") or ""),
            "attemptId": attempt_id,
            "executionStage": task_stage(task),
            "stageRunId": str(task.get("stageRunId") or (attempt or {}).get("stageRunId") or ""),
            "executionState": str(task.get("executionState") or ""),
            "attemptStatus": str((attempt or {}).get("status") or ""),
        })
    return {
        "requestedAt": requested_at,
        "requestedBy": dict(actor),
        "reason": reason,
        "currentStage": state.get("currentStage"),
        "currentRunId": state.get("currentRunId"),
        "activeAttemptIds": [item["attemptId"] for item in active_attempts],
        "activeAttempts": active_attempts,
    }


def _existing_pause_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    raw = state.get("pauseSnapshot")
    if isinstance(raw, Mapping):
        return copy.deepcopy(dict(raw))
    return {"activeAttemptIds": [], "activeAttempts": []}


def _attempt(task: Mapping[str, Any], attempt_id: str) -> Mapping[str, Any] | None:
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and str(attempt.get("id") or "") == attempt_id:
            return attempt
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and str(attempt.get("status") or "") in {
            *PAUSE_ACTIVE_ATTEMPT_STATUSES,
        }:
            return attempt
    return None


def _find_task(project: Mapping[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in project.get("tasks") or []:
        if isinstance(task, dict) and str(task.get("id") or "") == str(task_id):
            return task
    return None


def _snapshot_attempts(snapshot: Mapping[str, Any]) -> list[dict[str, str]]:
    attempts = []
    for item in snapshot.get("activeAttempts") or []:
        if not isinstance(item, Mapping):
            continue
        task_id = str(item.get("taskId") or "")
        attempt_id = str(item.get("attemptId") or "")
        if task_id and attempt_id:
            attempts.append({"taskId": task_id, "attemptId": attempt_id})
    if attempts:
        return attempts
    return [
        {"taskId": "", "attemptId": str(attempt_id)}
        for attempt_id in snapshot.get("activeAttemptIds") or []
        if str(attempt_id or "")
    ]


def _cancel_snapshot_attempt(item: Mapping[str, Any], ports: PauseCancellationPorts) -> dict[str, Any]:
    payload = {"taskId": str(item.get("taskId") or ""), "attemptId": str(item.get("attemptId") or "")}
    try:
        result = dict(ports.cancel_attempt(payload))
    except Exception as exc:
        result = {"ok": False, "status": "cancel_failed", "error": str(exc)}
    result.setdefault("ok", True)
    result.setdefault("status", "cancelled")
    return {**payload, **result}


def _reject(status: int, **payload: Any) -> None:
    raise _PauseCommandRejected(status, payload)
