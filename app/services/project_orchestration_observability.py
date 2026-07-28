"""Structured diagnostics for stage-pipeline project orchestration."""

from __future__ import annotations

import copy
import time
from typing import Any, Iterable, Mapping


AUDIT_HISTORY_LIMIT = 100


def monotonic_ms() -> int:
    return int(time.perf_counter() * 1000)


def elapsed_ms(start_ms: int | None) -> int:
    if start_ms is None:
        return 0
    return max(0, monotonic_ms() - int(start_ms))


def reservation_diagnostics(
    *,
    status: str,
    project_id: str,
    stage: int | None,
    run_id: str | None,
    revision: int | None,
    task_ids: Iterable[str] = (),
    duration_ms: int = 0,
    code: str | None = None,
) -> dict[str, Any]:
    task_id_list = list(task_ids)
    return operation_diagnostics(
        "reservation",
        status,
        project_id=project_id,
        stage=stage,
        run_id=run_id,
        revision=revision,
        counters={"reservations": 1},
        timings={"reservationMs": duration_ms},
        fields={"taskIds": task_id_list, "taskCount": len(task_id_list), "code": code},
    )


def submission_diagnostics(
    *,
    status: str,
    project_id: str,
    task_id: str,
    run_id: str,
    attempt_id: str | None = None,
    stage: int | None = None,
    revision: int | None = None,
    queued: int,
    in_flight: int,
    worker_count: int,
    queue_capacity: int,
    code: str,
) -> dict[str, Any]:
    rejected = status == "rejected"
    return operation_diagnostics(
        "submission",
        status,
        project_id=project_id,
        task_id=task_id,
        stage=stage,
        run_id=run_id,
        attempt_id=attempt_id,
        revision=revision,
        counters={
            "submissions": 1,
            "acceptedSubmissions": 0 if rejected else 1,
            "queueRejections": 1 if rejected else 0,
        },
        fields={
            "code": code,
            "queued": queued,
            "inFlight": in_flight,
            "workerCount": worker_count,
            "queueCapacity": queue_capacity,
        },
    )


def duplicate_suppression_diagnostics(
    *,
    project_id: str,
    stage: int | None,
    run_id: str,
    revision: int | None,
    status: str,
    pending_task_ids: Iterable[str] = (),
) -> dict[str, Any]:
    return operation_diagnostics(
        "duplicateSuppression",
        status,
        project_id=project_id,
        stage=stage,
        run_id=run_id,
        revision=revision,
        counters={"duplicateSuppressions": 1},
        fields={"pendingTaskIds": list(pending_task_ids)},
    )


def stage_advancement_diagnostics(
    *,
    project_id: str,
    stage: int | None,
    run_id: str,
    revision: int | None,
    status: str,
    next_stage: int | None = None,
    next_run_id: str | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    return operation_diagnostics(
        "stageAdvancement",
        status,
        project_id=project_id,
        stage=stage,
        run_id=run_id,
        revision=revision,
        counters={"stageAdvancements": 1 if status == "stage_advanced" else 0, "projectCompletions": 1 if status == "project_completed" else 0},
        timings={"stageReconciliationMs": duration_ms},
        fields={"nextStage": next_stage, "nextRunId": next_run_id},
    )


def pause_diagnostics(
    *,
    project_id: str,
    stage: int | None,
    run_id: str | None,
    revision: int | None,
    status: str,
    attempt_ids: Iterable[str] = (),
    duration_ms: int = 0,
) -> dict[str, Any]:
    ids = list(attempt_ids)
    return operation_diagnostics(
        "pause",
        status,
        project_id=project_id,
        stage=stage,
        run_id=run_id,
        revision=revision,
        counters={"pauses": 1, "pauseAttempts": len(ids)},
        timings={"pauseMs": duration_ms},
        fields={"attemptIds": ids, "attemptCount": len(ids)},
    )


def skip_decision_diagnostics(
    *,
    project_id: str,
    task_id: str,
    stage: int | None,
    run_id: str | None,
    revision: int | None,
    attempt_id: str | None = None,
    status: str,
    approved: bool,
) -> dict[str, Any]:
    return operation_diagnostics(
        "skipDecision",
        status,
        project_id=project_id,
        task_id=task_id,
        stage=stage,
        run_id=run_id,
        attempt_id=attempt_id,
        revision=revision,
        counters={"skipDecisions": 1, "approvedSkips": 1 if approved else 0, "rejectedSkips": 0 if approved else 1},
    )


def recovery_diagnostics(
    *,
    project_id: str,
    stage: int | None,
    run_id: str | None,
    revision: int | None,
    status: str,
    preserved_attempt_ids: Iterable[str] = (),
    prepared_attempt_ids: Iterable[str] = (),
    blocked_task_ids: Iterable[str] = (),
    duration_ms: int = 0,
) -> dict[str, Any]:
    preserved = list(preserved_attempt_ids)
    prepared = list(prepared_attempt_ids)
    blocked = list(blocked_task_ids)
    return operation_diagnostics(
        "recovery",
        status,
        project_id=project_id,
        stage=stage,
        run_id=run_id,
        revision=revision,
        counters={
            "recoveries": 1,
            "preservedAttempts": len(preserved),
            "preparedAttempts": len(prepared),
        },
        timings={"recoveryMs": duration_ms},
        fields={"preservedAttemptIds": preserved, "preparedAttemptIds": prepared, "blockedTaskIds": blocked},
    )


def autosave_conflict_diagnostics(
    *,
    project_id: str,
    revision: int | None,
    current_revision: int | None,
) -> dict[str, Any]:
    return operation_diagnostics(
        "autoSaveConflict",
        "revision_conflict",
        project_id=project_id,
        revision=revision,
        counters={"autoSaveConflicts": 1},
        fields={"currentRevision": current_revision},
    )


def stuck_state_diagnostics(
    *,
    project_id: str,
    stage: int | None,
    run_id: str | None,
    revision: int | None,
    status: str,
    blocked_task_ids: Iterable[str],
    code: str,
) -> dict[str, Any]:
    blocked = list(blocked_task_ids)
    return operation_diagnostics(
        "stuckState",
        status,
        project_id=project_id,
        stage=stage,
        run_id=run_id,
        revision=revision,
        counters={"stuckStates": 1},
        fields={"blockedTaskIds": blocked, "blockedTaskCount": len(blocked), "code": code},
    )


def operation_diagnostics(
    operation: str,
    status: str,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    stage: int | None = None,
    run_id: str | None = None,
    attempt_id: str | None = None,
    revision: int | None = None,
    counters: Mapping[str, int] | None = None,
    timings: Mapping[str, int] | None = None,
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audit: dict[str, Any] = {
        "operation": operation,
        "status": status,
    }
    _put(audit, "projectId", project_id)
    _put(audit, "taskId", task_id)
    _put(audit, "stage", stage)
    _put(audit, "runId", run_id)
    _put(audit, "attemptId", attempt_id)
    _put(audit, "revision", revision)
    for key, value in (fields or {}).items():
        _put(audit, key, value)
    return {
        "operation": operation,
        "status": status,
        "counters": {key: int(value) for key, value in (counters or {}).items()},
        "timings": {key: max(0, int(value)) for key, value in (timings or {}).items()},
        "audit": audit,
    }


def append_project_audit(project: dict[str, Any], diagnostic: Mapping[str, Any], *, at: str | None = None) -> None:
    audit = copy.deepcopy(diagnostic.get("audit") if isinstance(diagnostic, Mapping) else None)
    if not isinstance(audit, dict):
        return
    if at:
        audit["at"] = at
    project.setdefault("orchestrationAudit", []).append(audit)
    project["orchestrationAudit"] = project["orchestrationAudit"][-AUDIT_HISTORY_LIMIT:]


def combine_diagnostics(*items: Mapping[str, Any] | None) -> dict[str, Any]:
    diagnostics = [copy.deepcopy(dict(item)) for item in items if isinstance(item, Mapping)]
    counters: dict[str, int] = {}
    timings: dict[str, int] = {}
    audit: list[dict[str, Any]] = []
    for item in diagnostics:
        for key, value in (item.get("counters") or {}).items():
            counters[key] = counters.get(key, 0) + int(value)
        for key, value in (item.get("timings") or {}).items():
            timings[key] = timings.get(key, 0) + int(value)
        if isinstance(item.get("audit"), Mapping):
            audit.append(copy.deepcopy(dict(item["audit"])))
    return {"counters": counters, "timings": timings, "audit": audit}


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None or value == "" or value == []:
        return
    target[key] = copy.deepcopy(value)
