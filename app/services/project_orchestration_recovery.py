"""Startup recovery for marked stage-pipeline project runs."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping

from .project_execution import ServiceResult
from .project_orchestration import (
    STATE_BLOCKED,
    STATE_PAUSING,
    STATE_RUNNING,
    STATE_STARTING,
    is_marked_project,
    orchestration_state,
    task_is_accepted_terminal,
    task_stage,
    tasks_by_stage,
    validate_stage_invariants,
)
from .project_orchestration_observability import (
    combine_diagnostics,
    elapsed_ms,
    monotonic_ms,
    recovery_diagnostics,
    stuck_state_diagnostics,
)
from .project_repository import ProjectConflictError, ProjectNotFoundError, ProjectRepository


RECOVERABLE_STATES = frozenset({STATE_STARTING, STATE_RUNNING, STATE_PAUSING})
ACTIVE_ATTEMPT_STATUSES = frozenset({
    "validating",
    "executing",
    "retrying",
    "reviewing",
    "reworking",
    "meeting_action_items",
    "cancelling",
})
NON_RESUMABLE_REASON = "stage_attempt_not_resumable_after_restart"


@dataclass(frozen=True)
class RecoveryPreparedAttempt:
    task_id: str
    attempt_id: str
    run_id: str
    idempotent: bool = False


@dataclass(frozen=True)
class RecoverySubmission:
    task_id: str
    attempt_id: str
    run_id: str
    accepted: bool
    code: str


@dataclass(frozen=True)
class RecoveryProjectResult:
    project_id: str
    status: str
    orchestration_state: str | None = None
    current_stage: int | None = None
    current_run_id: str | None = None
    preserved_attempt_ids: tuple[str, ...] = ()
    prepared_attempts: tuple[RecoveryPreparedAttempt, ...] = ()
    submissions: tuple[RecoverySubmission, ...] = ()
    blocked_task_ids: tuple[str, ...] = ()
    reconcile_status: str | None = None
    pause_status: str | None = None
    error: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryReport:
    result: ServiceResult
    projects: tuple[RecoveryProjectResult, ...] = ()


@dataclass(frozen=True)
class RecoveryPorts:
    now: Callable[[], str]
    is_live_attempt: Callable[[str], bool]
    prepare_reserved_task: Callable[[str, str, str], Mapping[str, Any]]
    submit_reserved_task: Callable[[str, str, str, str], Mapping[str, Any]]
    reconcile_stage_run: Callable[[str, str], Mapping[str, Any]]
    complete_pausing_project: Callable[[str], Mapping[str, Any]]
    transition: Callable[[dict[str, Any], dict[str, Any], str, str, str, str | None], Any]


class _RecoveryRejected(RuntimeError):
    def __init__(self, status: int, payload: Mapping[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload.get("code") or "recovery rejected"))
        self.status = status
        self.payload = dict(payload)


def recover_marked_projects(
    *,
    repository: ProjectRepository,
    ports: RecoveryPorts,
) -> RecoveryReport:
    """Recover every marked project left in an active orchestration state."""

    started_ms = monotonic_ms()
    data = repository.load_all()
    project_ids = tuple(
        str(project.get("id") or "")
        for project in data.get("projects", [])
        if isinstance(project, Mapping)
        and project.get("id")
        and is_marked_project(project)
        and str(orchestration_state(project).get("state") or "") in RECOVERABLE_STATES
    )
    results = tuple(
        _decorate_recovery_result(
            _recover_one(project_id, repository=repository, ports=ports),
            repository=repository,
            duration_ms=elapsed_ms(started_ms),
        )
        for project_id in project_ids
    )
    return RecoveryReport(ServiceResult(200, {
        "ok": True,
        "status": "recovered",
        "projectCount": len(results),
        "projects": [_project_result_payload(item) for item in results],
    }), results)


def _recover_one(
    project_id: str,
    *,
    repository: ProjectRepository,
    ports: RecoveryPorts,
) -> RecoveryProjectResult:
    snapshot = repository.get(project_id)
    if snapshot is None:
        return RecoveryProjectResult(project_id=project_id, status="not_found", error="Project not found")
    state = orchestration_state(snapshot)
    current_state = str(state.get("state") or "")
    if current_state == STATE_PAUSING:
        pause = dict(ports.complete_pausing_project(project_id) or {})
        return RecoveryProjectResult(
            project_id=project_id,
            status=str(pause.get("status") or ("pausing" if not pause.get("ok") else "paused")),
            orchestration_state=current_state,
            current_stage=_int_or_none(state.get("currentStage")),
            current_run_id=str(state.get("currentRunId") or "") or None,
            pause_status=str(pause.get("status") or pause.get("code") or ""),
            error=None if pause.get("ok") else str(pause.get("error") or pause.get("code") or "pause recovery failed"),
        )
    if current_state not in {STATE_STARTING, STATE_RUNNING}:
        return RecoveryProjectResult(
            project_id=project_id,
            status="ignored",
            orchestration_state=current_state,
        )

    current_run_id = str(state.get("currentRunId") or "").strip()
    current_stage = _int_or_none(state.get("currentStage"))
    if not current_run_id or current_stage is None:
        blocked = _block_project(project_id, repository=repository, ports=ports, reason="current_stage_run_required")
        return RecoveryProjectResult(
            project_id=project_id,
            status="blocked",
            orchestration_state=STATE_BLOCKED if blocked else current_state,
            current_stage=current_stage,
            current_run_id=current_run_id or None,
            error="current_stage_run_required",
        )

    restore = _restore_or_block_active_attempts(
        project_id,
        current_stage,
        current_run_id,
        repository=repository,
        ports=ports,
    )
    if restore.result.status != 200:
        payload = restore.result.payload
        return RecoveryProjectResult(
            project_id=project_id,
            status="blocked" if payload.get("code") == NON_RESUMABLE_REASON else "failed",
            orchestration_state=STATE_BLOCKED if payload.get("code") == NON_RESUMABLE_REASON else current_state,
            current_stage=current_stage,
            current_run_id=current_run_id,
            blocked_task_ids=tuple(payload.get("blockedTaskIds") or ()),
            error=str(payload.get("error") or payload.get("code") or "recovery failed"),
        )

    reconcile = dict(ports.reconcile_stage_run(project_id, current_run_id) or {})
    reconcile_status = str(reconcile.get("status") or reconcile.get("code") or "")
    if reconcile.get("ok") and reconcile_status in {"stage_advanced", "project_completed", "stale_run_ignored"}:
        return RecoveryProjectResult(
            project_id=project_id,
            status=reconcile_status,
            orchestration_state=current_state,
            current_stage=current_stage,
            current_run_id=current_run_id,
            preserved_attempt_ids=tuple(restore.result.payload.get("preservedAttemptIds") or ()),
            reconcile_status=reconcile_status,
        )

    latest = repository.get(project_id) or {}
    latest_state = orchestration_state(latest)
    latest_run_id = str(latest_state.get("currentRunId") or "").strip()
    latest_stage = _int_or_none(latest_state.get("currentStage"))
    if latest_run_id != current_run_id or latest_stage != current_stage:
        return RecoveryProjectResult(
            project_id=project_id,
            status="run_changed",
            orchestration_state=str(latest_state.get("state") or ""),
            current_stage=latest_stage,
            current_run_id=latest_run_id or None,
            preserved_attempt_ids=tuple(restore.result.payload.get("preservedAttemptIds") or ()),
            reconcile_status=reconcile_status,
        )

    prepared: list[RecoveryPreparedAttempt] = []
    submissions: list[RecoverySubmission] = []
    for task_id in _reserved_tasks_without_attempts(latest, current_stage, current_run_id):
        prepare = dict(ports.prepare_reserved_task(project_id, task_id, current_run_id) or {})
        if not prepare.get("ok"):
            return RecoveryProjectResult(
                project_id=project_id,
                status="prepare_failed",
                orchestration_state=str(latest_state.get("state") or ""),
                current_stage=current_stage,
                current_run_id=current_run_id,
                preserved_attempt_ids=tuple(restore.result.payload.get("preservedAttemptIds") or ()),
                prepared_attempts=tuple(prepared),
                submissions=tuple(submissions),
                reconcile_status=reconcile_status,
                error=str(prepare.get("error") or prepare.get("code") or "attempt preparation failed"),
            )
        attempt_id = str(prepare.get("attemptId") or "")
        prepared.append(RecoveryPreparedAttempt(
            task_id=task_id,
            attempt_id=attempt_id,
            run_id=current_run_id,
            idempotent=bool(prepare.get("idempotent")),
        ))
        submission = dict(ports.submit_reserved_task(project_id, task_id, current_run_id, attempt_id) or {})
        submissions.append(RecoverySubmission(
            task_id=task_id,
            attempt_id=attempt_id,
            run_id=current_run_id,
            accepted=bool(submission.get("accepted", submission.get("ok"))),
            code=str(submission.get("code") or submission.get("status") or ""),
        ))
        if not submissions[-1].accepted:
            return RecoveryProjectResult(
                project_id=project_id,
                status="submission_rejected",
                orchestration_state=str(latest_state.get("state") or ""),
                current_stage=current_stage,
                current_run_id=current_run_id,
                preserved_attempt_ids=tuple(restore.result.payload.get("preservedAttemptIds") or ()),
                prepared_attempts=tuple(prepared),
                submissions=tuple(submissions),
                reconcile_status=reconcile_status,
                error=submissions[-1].code or "submission_rejected",
            )

    return RecoveryProjectResult(
        project_id=project_id,
        status="resubmitted" if submissions else "preserved",
        orchestration_state=str(latest_state.get("state") or ""),
        current_stage=current_stage,
        current_run_id=current_run_id,
        preserved_attempt_ids=tuple(restore.result.payload.get("preservedAttemptIds") or ()),
        prepared_attempts=tuple(prepared),
        submissions=tuple(submissions),
        reconcile_status=reconcile_status,
    )


def _restore_or_block_active_attempts(
    project_id: str,
    current_stage: int,
    current_run_id: str,
    *,
    repository: ProjectRepository,
    ports: RecoveryPorts,
) -> RecoveryReport:
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
        state = orchestration_state(project)
        if state.get("currentRunId") != current_run_id or _int_or_none(state.get("currentStage")) != current_stage:
            _reject(
                409,
                ok=False,
                code="stage_run_changed",
                error="Stage run changed during recovery",
                currentRunId=state.get("currentRunId"),
                currentStage=state.get("currentStage"),
            )
        if state.get("state") not in {STATE_STARTING, STATE_RUNNING}:
            _reject(
                409,
                ok=False,
                code="orchestration_not_recoverable",
                error="Only starting or running orchestration can be recovered",
                orchestrationState=state.get("state"),
            )

        timestamp = ports.now()
        preserved: list[str] = []
        blocked: list[str] = []
        for task in tasks_by_stage(project).get(current_stage, []):
            if task_is_accepted_terminal(task) or str(task.get("stageRunId") or "") != current_run_id:
                continue
            active_attempt_id = str(task.get("activeAttemptId") or "")
            active_attempt = _attempt(task, active_attempt_id) if active_attempt_id else _first_active_stage_attempt(task, current_run_id)
            if active_attempt is None:
                continue
            attempt_id = str(active_attempt.get("id") or "")
            if ports.is_live_attempt(attempt_id):
                preserved.append(attempt_id)
                if task.get("activeAttemptId") != attempt_id:
                    task["activeAttemptId"] = attempt_id
                    task["updatedAt"] = timestamp
                continue
            blocked.append(str(task.get("id") or ""))
            active_attempt.update({
                "status": "blocked",
                "blockedAt": timestamp,
                "finishedAt": active_attempt.get("finishedAt") or timestamp,
                "blockedReason": NON_RESUMABLE_REASON,
            })
            task["activeAttemptId"] = None
            task["blockedReason"] = NON_RESUMABLE_REASON
            task["lastError"] = NON_RESUMABLE_REASON
            task["updatedAt"] = timestamp
            ports.transition(
                project,
                task,
                "blocked",
                "startup-recovery",
                "Previous stage attempt was not resumable after process restart.",
                attempt_id,
            )
            task["executionState"] = "blocked"

        if blocked:
            state["state"] = STATE_BLOCKED
            state["pauseReason"] = NON_RESUMABLE_REASON
            state["revision"] = int(state.get("revision") or 0) + 1
            project["orchestration"] = state
            project["updatedAt"] = timestamp
            outcome.update({
                "blocked": tuple(blocked),
                "preserved": tuple(preserved),
            })
            return

        if preserved:
            project["updatedAt"] = timestamp
        outcome.update({
            "blocked": (),
            "preserved": tuple(preserved),
        })

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return RecoveryReport(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    except _RecoveryRejected as exc:
        return RecoveryReport(ServiceResult(exc.status, exc.payload))
    except ProjectConflictError:
        return RecoveryReport(ServiceResult(409, {
            "ok": False,
            "code": "recovery_commit_conflict",
            "error": "Project changed during startup recovery",
        }))
    if outcome.get("blocked"):
        return RecoveryReport(ServiceResult(409, {
            "ok": False,
            "code": NON_RESUMABLE_REASON,
            "error": "One or more active attempts cannot be resumed after restart",
            "blockedTaskIds": list(outcome.get("blocked") or ()),
            "preservedAttemptIds": list(outcome.get("preserved") or ()),
        }))
    return RecoveryReport(ServiceResult(200, {
        "ok": True,
        "status": "active_attempts_checked",
        "preservedAttemptIds": list(outcome.get("preserved") or ()),
    }))


def _block_project(
    project_id: str,
    *,
    repository: ProjectRepository,
    ports: RecoveryPorts,
    reason: str,
) -> bool:
    try:
        repository.update(project_id, lambda project: _set_project_blocked(project, ports, reason))
    except (ProjectNotFoundError, ProjectConflictError, _RecoveryRejected):
        return False
    return True


def _set_project_blocked(project: dict[str, Any], ports: RecoveryPorts, reason: str) -> None:
    state = orchestration_state(project)
    state["state"] = STATE_BLOCKED
    state["pauseReason"] = reason
    state["revision"] = int(state.get("revision") or 0) + 1
    project["orchestration"] = state
    project["updatedAt"] = ports.now()


def _reserved_tasks_without_attempts(project: Mapping[str, Any], current_stage: int, current_run_id: str) -> tuple[str, ...]:
    task_ids: list[str] = []
    for task in project.get("tasks") or []:
        if not isinstance(task, Mapping):
            continue
        if task_stage(task) != current_stage:
            continue
        if task_is_accepted_terminal(task):
            continue
        if str(task.get("stageRunId") or "") != current_run_id:
            continue
        active_attempt_id = str(task.get("activeAttemptId") or "")
        if active_attempt_id:
            continue
        if _first_active_stage_attempt(task, current_run_id) is not None:
            continue
        if _matching_stage_attempt(task, current_run_id) is not None:
            continue
        task_id = str(task.get("id") or "")
        if task_id:
            task_ids.append(task_id)
    return tuple(task_ids)


def _matching_stage_attempt(task: Mapping[str, Any], run_id: str) -> Mapping[str, Any] | None:
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and str(attempt.get("stageRunId") or "") == run_id:
            return attempt
    return None


def _first_active_stage_attempt(task: Mapping[str, Any], run_id: str) -> Mapping[str, Any] | None:
    for attempt in task.get("attempts") or []:
        if (
            isinstance(attempt, Mapping)
            and str(attempt.get("stageRunId") or "") == run_id
            and str(attempt.get("status") or "") in ACTIVE_ATTEMPT_STATUSES
        ):
            return attempt
    return None


def _attempt(task: Mapping[str, Any], attempt_id: str) -> Mapping[str, Any] | None:
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and str(attempt.get("id") or "") == attempt_id:
            return attempt
    return None


def _project_result_payload(result: RecoveryProjectResult) -> dict[str, Any]:
    return {
        "projectId": result.project_id,
        "status": result.status,
        "orchestrationState": result.orchestration_state,
        "currentStage": result.current_stage,
        "currentRunId": result.current_run_id,
        "preservedAttemptIds": list(result.preserved_attempt_ids),
        "preparedAttempts": [copy.deepcopy(item.__dict__) for item in result.prepared_attempts],
        "submissions": [copy.deepcopy(item.__dict__) for item in result.submissions],
        "blockedTaskIds": list(result.blocked_task_ids),
        "reconcileStatus": result.reconcile_status,
        "pauseStatus": result.pause_status,
        "error": result.error,
        "diagnostics": copy.deepcopy(dict(result.diagnostics)),
    }


def _decorate_recovery_result(
    result: RecoveryProjectResult,
    *,
    repository: ProjectRepository,
    duration_ms: int,
) -> RecoveryProjectResult:
    latest = repository.get(result.project_id) or {}
    state = orchestration_state(latest)
    revision = int(state.get("revision") or 0) if latest else None
    prepared_attempt_ids = [item.attempt_id for item in result.prepared_attempts]
    diagnostics = recovery_diagnostics(
        project_id=result.project_id,
        stage=result.current_stage,
        run_id=result.current_run_id,
        revision=revision,
        status=result.status,
        preserved_attempt_ids=result.preserved_attempt_ids,
        prepared_attempt_ids=prepared_attempt_ids,
        blocked_task_ids=result.blocked_task_ids,
        duration_ms=duration_ms,
    )
    if result.blocked_task_ids:
        diagnostics = combine_diagnostics(
            diagnostics,
            stuck_state_diagnostics(
                project_id=result.project_id,
                stage=result.current_stage,
                run_id=result.current_run_id,
                revision=revision,
                status="blocked",
                blocked_task_ids=result.blocked_task_ids,
                code=result.error or NON_RESUMABLE_REASON,
            ),
        )
    return replace(result, diagnostics=diagnostics)


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _reject(status: int, **payload: Any) -> None:
    raise _RecoveryRejected(status, payload)
