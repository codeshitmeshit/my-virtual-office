"""Bounded dispatch infrastructure for stage-based project execution."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from .project_execution import ServiceResult
from .project_orchestration import (
    STATE_BLOCKED,
    STATE_COMPLETED,
    STATE_DRAFT,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_RUNNING,
    STATE_STARTING,
    is_marked_project,
    next_unfinished_stage,
    orchestration_state,
    task_has_active_attempt,
    task_is_accepted_terminal,
    task_stage,
    tasks_by_stage,
    validate_stage_invariants,
)
from .project_orchestration_observability import (
    append_project_audit,
    duplicate_suppression_diagnostics,
    elapsed_ms,
    reservation_diagnostics,
    stage_advancement_diagnostics,
    submission_diagnostics,
    monotonic_ms,
)
from .project_repository import ProjectConflictError, ProjectNotFoundError, ProjectRepository
from .project_task_final_result import record_stage_handoff


DEFAULT_STAGE_DISPATCH_WORKERS = 8
DEFAULT_STAGE_DISPATCH_QUEUE_CAPACITY = 100
QUEUE_FULL_CODE = "dispatch_queue_full"

TaskRunner = Callable[["StageDispatchWorkItem"], Any]


class StagePreflightPorts(Protocol):
    validate_workspace: Callable[[str], dict[str, Any]]
    git_snapshot: Callable[[str], dict[str, Any]]
    resolve_roles: Callable[[dict[str, Any], dict[str, Any], bool], dict[str, Any]]
    authorize: Callable[[dict[str, Any], Mapping[str, Any]], dict[str, Any]]
    now: Callable[[], str]
    new_run_id: Callable[[], str]


class StageAttemptPorts(Protocol):
    now: Callable[[], str]
    new_attempt_id: Callable[[], str]
    requires_acceptance: Callable[[dict[str, Any]], bool]
    seed_checklist: Callable[[dict[str, Any], str], Any]
    has_pending_meeting_actions: Callable[[dict[str, Any]], bool]
    transition: Callable[[dict[str, Any], dict[str, Any], str, str, str, str | None], Any]


@dataclass(frozen=True)
class StageDispatchWorkItem:
    project_id: str
    task_id: str
    run_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    submitted_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class StageDispatchSubmission:
    accepted: bool
    code: str
    project_id: str
    task_id: str
    run_id: str
    queued: int
    in_flight: int
    worker_count: int
    queue_capacity: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageDispatchResult:
    item: StageDispatchWorkItem
    ok: bool
    result: Any = None
    error: str | None = None


@dataclass(frozen=True)
class StagePreflightBlocker:
    code: str
    message: str
    task_id: str | None = None
    stage: int | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageReservation:
    project: dict[str, Any]
    orchestration: dict[str, Any]
    run_id: str
    stage: int
    task_ids: tuple[str, ...]
    workspace: dict[str, Any]
    git_state: dict[str, Any]
    roles_by_task_id: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class StageReservationOutcome:
    result: ServiceResult
    reservation: StageReservation | None = None


@dataclass(frozen=True)
class StageAttemptPreparation:
    project: dict[str, Any]
    task: dict[str, Any]
    attempt: dict[str, Any]
    idempotent: bool = False


@dataclass(frozen=True)
class StageAttemptOutcome:
    result: ServiceResult
    preparation: StageAttemptPreparation | None = None


@dataclass(frozen=True)
class MarkedProjectStartOutcome:
    result: ServiceResult
    reservation: StageReservation | None = None
    attempts: tuple[StageAttemptPreparation, ...] = ()
    submissions: tuple[StageDispatchSubmission, ...] = ()


@dataclass(frozen=True)
class StageReconciliation:
    project: dict[str, Any]
    orchestration: dict[str, Any]
    status: str
    run_id: str
    current_stage: int | None = None
    next_stage: int | None = None
    next_run_id: str | None = None
    pending_task_ids: tuple[str, ...] = ()
    task_ids: tuple[str, ...] = ()
    idempotent: bool = False


@dataclass(frozen=True)
class StageReconciliationOutcome:
    result: ServiceResult
    reconciliation: StageReconciliation | None = None


class BoundedProjectExecutionDispatcher:
    """Run reserved project tasks through a bounded process-level queue."""

    def __init__(
        self,
        runner: TaskRunner,
        *,
        worker_count: int = DEFAULT_STAGE_DISPATCH_WORKERS,
        queue_capacity: int = DEFAULT_STAGE_DISPATCH_QUEUE_CAPACITY,
        thread_name_prefix: str = "project-stage-dispatch",
        autostart: bool = True,
    ) -> None:
        if not callable(runner):
            raise TypeError("runner must be callable")
        if isinstance(worker_count, bool) or worker_count < 1:
            raise ValueError("worker_count must be a positive integer")
        if isinstance(queue_capacity, bool) or queue_capacity < 1:
            raise ValueError("queue_capacity must be a positive integer")
        self._runner = runner
        self._worker_count = int(worker_count)
        self._queue_capacity = int(queue_capacity)
        self._thread_name_prefix = thread_name_prefix
        self._queue: queue.Queue[StageDispatchWorkItem | None] = queue.Queue(maxsize=self._queue_capacity)
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._shutdown = False
        self._started = False
        self._threads: list[threading.Thread] = []
        self._in_flight = 0
        self._submitted = 0
        self._accepted = 0
        self._rejected = 0
        self._completed = 0
        self._failed = 0
        if autostart:
            self.start()

    @property
    def worker_count(self) -> int:
        return self._worker_count

    @property
    def queue_capacity(self) -> int:
        return self._queue_capacity

    def start(self) -> None:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("dispatcher is shut down")
            if self._started:
                return
            self._started = True
            for index in range(self._worker_count):
                thread = threading.Thread(
                    target=self._worker_loop,
                    name=f"{self._thread_name_prefix}-{index + 1}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

    def submit(
        self,
        *,
        project_id: str,
        task_id: str,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> StageDispatchSubmission:
        project_id = str(project_id or "").strip()
        task_id = str(task_id or "").strip()
        run_id = str(run_id or "").strip()
        if not project_id or not task_id or not run_id:
            raise ValueError("project_id, task_id, and run_id are required")
        payload_map = dict(payload or {})
        with self._lock:
            self._submitted += 1
            if self._shutdown:
                self._rejected += 1
                return self._submission(False, "dispatcher_shutdown", project_id, task_id, run_id, payload_map)
        item = StageDispatchWorkItem(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            payload=payload_map,
        )
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            with self._lock:
                self._rejected += 1
                return self._submission(False, QUEUE_FULL_CODE, project_id, task_id, run_id, payload_map)
        with self._lock:
            self._accepted += 1
            self._idle.notify_all()
            return self._submission(True, "accepted", project_id, task_id, run_id, payload_map)

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "workerCount": self._worker_count,
                "queueCapacity": self._queue_capacity,
                "queued": self._queue.qsize(),
                "inFlight": self._in_flight,
                "submitted": self._submitted,
                "accepted": self._accepted,
                "rejected": self._rejected,
                "completed": self._completed,
                "failed": self._failed,
                "shutdown": self._shutdown,
            }

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle:
            while self._queue.unfinished_tasks > 0 or self._in_flight > 0:
                if deadline is None:
                    self._idle.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(remaining)
            return True

    def run_next_for_tests(self) -> StageDispatchResult | None:
        try:
            item = self._queue.get_nowait()
        except queue.Empty:
            return None
        if item is None:
            self._queue.task_done()
            return None
        return self._run_item(item)

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            thread_count = len(self._threads)
        for _ in range(thread_count):
            while True:
                try:
                    self._queue.put_nowait(None)
                    break
                except queue.Full:
                    if wait:
                        time.sleep(0.01)
                        continue
                    break
        if wait:
            for thread in list(self._threads):
                thread.join()

    def _submission(
        self,
        accepted: bool,
        code: str,
        project_id: str,
        task_id: str,
        run_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> StageDispatchSubmission:
        queued = self._queue.qsize()
        payload = payload or {}
        try:
            stage = int(payload.get("stage")) if payload.get("stage") is not None else None
        except (TypeError, ValueError):
            stage = None
        try:
            revision = int(payload.get("revision")) if payload.get("revision") is not None else None
        except (TypeError, ValueError):
            revision = None
        diagnostics = submission_diagnostics(
            status="accepted" if accepted else "rejected",
            project_id=project_id,
            task_id=task_id,
            stage=stage,
            run_id=run_id,
            attempt_id=str(payload.get("attemptId") or "") or None,
            revision=revision,
            queued=queued,
            in_flight=self._in_flight,
            worker_count=self._worker_count,
            queue_capacity=self._queue_capacity,
            code=code,
        )
        return StageDispatchSubmission(
            accepted=accepted,
            code=code,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            queued=queued,
            in_flight=self._in_flight,
            worker_count=self._worker_count,
            queue_capacity=self._queue_capacity,
            diagnostics=diagnostics,
        )

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            self._run_item(item)

    def _run_item(self, item: StageDispatchWorkItem) -> StageDispatchResult:
        with self._lock:
            self._in_flight += 1
            self._idle.notify_all()
        try:
            result = self._runner(item)
        except Exception as exc:  # pragma: no cover - exercised through tests
            with self._lock:
                self._failed += 1
            dispatch_result = StageDispatchResult(item=item, ok=False, error=str(exc))
        else:
            with self._lock:
                self._completed += 1
            dispatch_result = StageDispatchResult(item=item, ok=True, result=result)
        finally:
            with self._idle:
                self._in_flight -= 1
                self._idle.notify_all()
            self._queue.task_done()
        return dispatch_result


def reserve_stage_run(
    project_id: str,
    body: Mapping[str, Any],
    *,
    repository: ProjectRepository,
    ports: StagePreflightPorts,
) -> StageReservationOutcome:
    """Preflight and atomically reserve all tasks in one execution stage."""

    started_ms = monotonic_ms()
    expected_revision = _revision(body.get("revision"))
    if expected_revision is None:
        return StageReservationOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_orchestration_revision",
            "error": "revision must be a non-negative integer",
        }))
    snapshot = repository.get(project_id)
    if snapshot is None:
        return StageReservationOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))

    actor = _actor(body)
    stage = _requested_stage(snapshot, body)
    blockers, context = _preflight(snapshot, stage, expected_revision, actor, body, ports)
    if blockers:
        return StageReservationOutcome(_blocker_result(blockers, context, 409))

    run_id = str(body.get("runId") or "").strip() or ports.new_run_id()
    if not run_id:
        return StageReservationOutcome(ServiceResult(500, {
            "ok": False,
            "code": "missing_stage_run_id",
            "error": "Unable to allocate stage run id",
        }))

    reservation_box: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> None:
        latest_blockers, latest_context = _preflight(
            project,
            stage,
            expected_revision,
            actor,
            body,
            ports,
            include_external=False,
            expected_workspace_path=context.get("workspacePath") or str(project.get("workspacePath") or ""),
        )
        if latest_blockers:
            raise _StageReservationRejected(_blocker_result(latest_blockers, latest_context, 409))
        state = orchestration_state(project)
        now = ports.now()
        stage_tasks = _stage_tasks(project, stage)
        state.update({
            "state": STATE_STARTING,
            "currentStage": stage,
            "currentRunId": run_id,
            "pauseReason": None,
            "revision": int(state.get("revision") or 0) + 1,
        })
        if not state.get("startedAt"):
            state["startedAt"] = now
        project["orchestration"] = state
        project["updatedAt"] = now
        for task in stage_tasks:
            task["stageRunId"] = run_id
            task["updatedAt"] = now
        diagnostics = reservation_diagnostics(
            status="reserved",
            project_id=str(project.get("id") or project_id),
            stage=stage,
            run_id=run_id,
            revision=int(state.get("revision") or 0),
            task_ids=(str(task.get("id") or "") for task in stage_tasks),
            duration_ms=elapsed_ms(started_ms),
        )
        append_project_audit(project, diagnostics, at=now)
        reservation_box.update({
            "project": _copy_project(project),
            "orchestration": dict(state),
            "taskIds": tuple(str(task.get("id")) for task in stage_tasks),
            "diagnostics": diagnostics,
        })

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return StageReservationOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    except _StageReservationRejected as exc:
        return StageReservationOutcome(exc.result)
    except ProjectConflictError:
        return StageReservationOutcome(ServiceResult(409, {
            "ok": False,
            "code": "stage_reservation_commit_conflict",
            "error": "Project changed during stage reservation",
        }))

    reservation = StageReservation(
        project=reservation_box["project"],
        orchestration=reservation_box["orchestration"],
        run_id=run_id,
        stage=stage,
        task_ids=reservation_box["taskIds"],
        workspace=context["workspace"],
        git_state=context["gitState"],
        roles_by_task_id=context["rolesByTaskId"],
    )
    return StageReservationOutcome(ServiceResult(200, {
        "ok": True,
        "project": reservation.project,
        "orchestration": reservation.orchestration,
        "runId": reservation.run_id,
        "currentRunId": reservation.run_id,
        "currentStage": reservation.stage,
        "taskIds": list(reservation.task_ids),
        "workspace": reservation.workspace,
        "diagnostics": reservation_box["diagnostics"],
    }), reservation)


def prepare_reserved_task_attempt(
    project_id: str,
    task_id: str,
    run_id: str,
    *,
    repository: ProjectRepository,
    ports: StageAttemptPorts,
    workspace: Mapping[str, Any],
    git_state: Mapping[str, Any],
    roles: Mapping[str, Any],
    body: Mapping[str, Any] | None = None,
) -> StageAttemptOutcome:
    """Create or return the task attempt for one already reserved stage task."""

    body = body or {}
    project_id = str(project_id or "").strip()
    task_id = str(task_id or "").strip()
    run_id = str(run_id or "").strip()
    if not project_id or not task_id or not run_id:
        return StageAttemptOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_stage_attempt_request",
            "error": "project_id, task_id, and run_id are required",
        }))
    if not roles.get("executor"):
        return StageAttemptOutcome(ServiceResult(400, {
            "ok": False,
            "code": "executor_required",
            "error": "Reserved task attempt requires an executor role",
            "taskId": task_id,
        }))

    attempt_id = str(body.get("attemptId") or "").strip() or ports.new_attempt_id()
    if not attempt_id:
        return StageAttemptOutcome(ServiceResult(500, {
            "ok": False,
            "code": "missing_attempt_id",
            "error": "Unable to allocate task attempt id",
            "taskId": task_id,
        }))

    prepared: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> dict[str, Any]:
        task = _find_task(project, task_id)
        state = orchestration_state(project)
        if task is None:
            _reject_attempt(404, ok=False, error="Project or task not found")
        if not is_marked_project(project):
            _reject_attempt(409, ok=False, code="missing_execution_model", error="Project is not marked for stage-pipeline orchestration")
        if state.get("currentRunId") != run_id:
            _reject_attempt(
                409,
                ok=False,
                code="stage_run_mismatch",
                error="Task is not reserved for the current stage run",
                currentRunId=state.get("currentRunId"),
                runId=run_id,
                taskId=task_id,
            )
        if state.get("state") not in {STATE_STARTING, STATE_RUNNING}:
            _reject_attempt(
                409,
                ok=False,
                code="orchestration_not_dispatching",
                error="Reserved task attempts can only be prepared while starting or running",
                orchestrationState=state.get("state"),
            )
        if task_stage(task) != state.get("currentStage"):
            _reject_attempt(
                409,
                ok=False,
                code="task_not_in_current_stage",
                error="Task does not belong to the current orchestration stage",
                taskId=task_id,
                currentStage=state.get("currentStage"),
            )
        if str(task.get("stageRunId") or "") != run_id:
            _reject_attempt(
                409,
                ok=False,
                code="task_not_reserved_for_run",
                error="Task is not reserved for this stage run",
                taskId=task_id,
                stageRunId=task.get("stageRunId"),
                runId=run_id,
            )

        existing = _matching_stage_attempt(task, run_id)
        if existing is not None and task.get("activeAttemptId") == existing.get("id"):
            prepared.update({
                "project": _copy_project(project),
                "task": _copy_project(task),
                "attempt": _copy_project(existing),
                "idempotent": True,
            })
            return _service_payload(
                200,
                ok=True,
                status="already_started",
                taskId=task_id,
                attemptId=existing.get("id"),
                runId=run_id,
                idempotent=True,
            )
        if task.get("activeAttemptId"):
            _reject_attempt(
                409,
                ok=False,
                code="active_attempt_exists",
                error="Task already has an active attempt for another run",
                taskId=task_id,
                activeAttemptId=task.get("activeAttemptId"),
            )

        ports.seed_checklist(task, str(body.get("by") or "system"))
        if git_state.get("dirty"):
            project.setdefault("executionDirtyConfirmations", []).append(git_state.get("fingerprint"))
            project["executionDirtyConfirmations"] = project["executionDirtyConfirmations"][-100:]
        meeting_phase = ports.has_pending_meeting_actions(task)
        now = ports.now()
        attempt = {
            "id": attempt_id,
            "status": "meeting_action_items" if meeting_phase else "executing",
            "startedAt": now,
            "workspacePath": workspace.get("path") or "",
            "workspaceKind": workspace.get("kind") or "",
            "dirtyConfirmed": bool(git_state.get("dirty")),
            "dirtyFingerprint": git_state.get("fingerprint") if git_state.get("dirty") else "",
            "executor": dict(roles.get("executor") or {}),
            "reviewer": dict(roles.get("reviewer") or {}) if roles.get("reviewer") else None,
            "skipReview": bool(roles.get("skipReview")),
            "skipReviewReason": roles.get("skipReviewReason"),
            "baseline": dict(git_state),
            "startMode": "stage",
            "projectFlow": True,
            "stageRunId": run_id,
            "requiresUserAcceptance": ports.requires_acceptance(task),
            "autoReviewAfterExecution": bool(body.get("autoReviewAfterExecution")) and not roles.get("skipReview"),
            "meetingActionPhase": meeting_phase,
        }
        task.setdefault("attempts", []).append(attempt)
        task["attempts"] = task["attempts"][-20:]
        executor_id = str((roles.get("executor") or {}).get("id") or "")
        if executor_id and not task.get("assignee"):
            task["assignee"] = executor_id
        task.update({
            "activeAttemptId": attempt_id,
            "executorAgentId": executor_id or task.get("executorAgentId"),
            "reviewerAgentId": ((roles.get("reviewer") or {}).get("id") if roles.get("reviewer") else None),
            "blockedReason": None,
            "lastError": None,
            "updatedAt": now,
        })
        state["state"] = STATE_RUNNING
        project["orchestration"] = state
        project["workspaceStatus"] = dict(workspace)
        project["updatedAt"] = now
        reason = "Meeting action item phase started" if meeting_phase else "Project Execution task started"
        ports.transition(project, task, "executing", str(body.get("by") or "system"), reason, attempt_id)
        prepared.update({
            "project": _copy_project(project),
            "task": _copy_project(task),
            "attempt": _copy_project(attempt),
            "idempotent": False,
        })
        return _service_payload(
            200,
            ok=True,
            status="started",
            taskId=task_id,
            attemptId=attempt_id,
            runId=run_id,
            requiresUserAcceptance=attempt["requiresUserAcceptance"],
            idempotent=False,
        )

    try:
        result = repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return StageAttemptOutcome(ServiceResult(404, {"ok": False, "error": "Project or task not found"}))
    except _StageAttemptRejected as exc:
        return StageAttemptOutcome(exc.result)
    except ProjectConflictError:
        return StageAttemptOutcome(ServiceResult(409, {
            "ok": False,
            "code": "stage_attempt_commit_conflict",
            "error": "Project changed during reserved task attempt preparation",
            "taskId": task_id,
            "runId": run_id,
        }))
    service_result = ServiceResult(int(result.pop("_status", 200)), result)
    if service_result.status != 200:
        return StageAttemptOutcome(service_result)
    return StageAttemptOutcome(
        service_result,
        StageAttemptPreparation(
            project=prepared["project"],
            task=prepared["task"],
            attempt=prepared["attempt"],
            idempotent=bool(prepared.get("idempotent")),
        ),
    )


def start_marked_project(
    project_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    preflight_ports: StagePreflightPorts,
    attempt_ports: StageAttemptPorts,
    dispatcher: BoundedProjectExecutionDispatcher,
    create_cancel_flag: Callable[[str], Any],
) -> MarkedProjectStartOutcome:
    """Reserve and submit the current stage for a marked project start."""

    body = dict(body or {})
    legacy_keys = [key for key in ("mode", "startMode", "restartPipeline") if key in body]
    if legacy_keys:
        return MarkedProjectStartOutcome(ServiceResult(400, {
            "ok": False,
            "code": "marked_project_legacy_start_payload_forbidden",
            "error": "Marked stage-pipeline projects do not accept legacy start mode or restart payload fields",
            "fields": legacy_keys,
        }))
    snapshot = repository.get(project_id)
    if snapshot is None:
        return MarkedProjectStartOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    if not is_marked_project(snapshot):
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "missing_execution_model",
            "error": "Project is not marked for stage-pipeline orchestration",
        }))
    state = orchestration_state(snapshot)
    reserve_body = {
        **body,
        "revision": body.get("revision", state.get("revision")),
        "stage": body.get("stage", body.get("currentStage", state.get("currentStage") or 1)),
        "allowSkipReviewer": body.get("allowSkipReviewer", bool(body.get("skipReviewConfirmed"))),
    }
    reservation_outcome = reserve_stage_run(
        project_id,
        reserve_body,
        repository=repository,
        ports=preflight_ports,
    )
    if reservation_outcome.result.status != 200 or reservation_outcome.reservation is None:
        return MarkedProjectStartOutcome(reservation_outcome.result)

    reservation = reservation_outcome.reservation
    attempts: list[StageAttemptPreparation] = []
    submissions: list[StageDispatchSubmission] = []
    start_diagnostics = [reservation_outcome.result.payload.get("diagnostics")]
    for task_id in reservation.task_ids:
        roles = reservation.roles_by_task_id.get(task_id) or {}
        attempt_outcome = prepare_reserved_task_attempt(
            project_id,
            task_id,
            reservation.run_id,
            repository=repository,
            ports=attempt_ports,
            workspace=reservation.workspace,
            git_state=reservation.git_state,
            roles=roles,
            body={**body, "by": body.get("by") or "stage-dispatch", "autoReviewAfterExecution": body.get("autoReviewAfterExecution", True)},
        )
        if attempt_outcome.result.status != 200 or attempt_outcome.preparation is None:
            payload = dict(attempt_outcome.result.payload)
            payload.setdefault("ok", False)
            payload.setdefault("code", "stage_attempt_prepare_failed")
            payload["preparedTaskIds"] = [attempt.task.get("id") for attempt in attempts]
            return MarkedProjectStartOutcome(ServiceResult(attempt_outcome.result.status, payload), reservation, tuple(attempts), tuple(submissions))
        attempts.append(attempt_outcome.preparation)
        attempt_id = str(attempt_outcome.preparation.attempt.get("id") or "")
        cancel_flag = create_cancel_flag(attempt_id)
        submission = dispatcher.submit(
            project_id=project_id,
            task_id=task_id,
            run_id=reservation.run_id,
            payload={
                "attemptId": attempt_id,
                "cancelFlag": cancel_flag,
                "stage": reservation.stage,
                "revision": reservation.orchestration.get("revision"),
            },
        )
        submissions.append(submission)
        start_diagnostics.append(submission.diagnostics)
        if not submission.accepted:
            block_result = _persist_dispatch_rejection(
                project_id,
                task_id,
                reservation.run_id,
                submission,
                repository=repository,
                ports=attempt_ports,
            )
            if block_result.status != 200:
                payload = dict(block_result.payload)
                payload["preparedTaskIds"] = [attempt.task.get("id") for attempt in attempts]
                payload["submissions"] = [_submission_payload(item) for item in submissions]
                return MarkedProjectStartOutcome(block_result, reservation, tuple(attempts), tuple(submissions))
            return MarkedProjectStartOutcome(ServiceResult(409, {
                "ok": False,
                "code": submission.code,
                "error": "Stage task dispatch was rejected",
                "runId": reservation.run_id,
                "taskId": task_id,
                "currentStage": reservation.stage,
                "preparedTaskIds": [attempt.task.get("id") for attempt in attempts],
                "submittedTaskIds": [item.task_id for item in submissions if item.accepted],
                "submissions": [_submission_payload(item) for item in submissions],
                "diagnostics": _combine_diagnostics(start_diagnostics),
            }), reservation, tuple(attempts), tuple(submissions))

    return MarkedProjectStartOutcome(ServiceResult(200, {
        "ok": True,
        "status": "stage_started",
        "runId": reservation.run_id,
        "currentRunId": reservation.run_id,
        "currentStage": reservation.stage,
        "taskIds": list(reservation.task_ids),
        "attempts": [
            {
                "taskId": attempt.task.get("id"),
                "attemptId": attempt.attempt.get("id"),
                "idempotent": attempt.idempotent,
            }
            for attempt in attempts
        ],
        "submissions": [_submission_payload(item) for item in submissions],
        "diagnostics": _combine_diagnostics(start_diagnostics),
    }), reservation, tuple(attempts), tuple(submissions))


def resume_paused_project(
    project_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    preflight_ports: StagePreflightPorts,
    attempt_ports: StageAttemptPorts,
    dispatcher: BoundedProjectExecutionDispatcher,
    create_cancel_flag: Callable[[str], Any],
) -> MarkedProjectStartOutcome:
    """Explicitly resume a paused project at its first unfinished stage."""

    body = dict(body or {})
    snapshot = repository.get(project_id)
    if snapshot is None:
        return MarkedProjectStartOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    if not is_marked_project(snapshot):
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "missing_execution_model",
            "error": "Project is not marked for stage-pipeline orchestration",
        }))
    state = orchestration_state(snapshot)
    if state.get("state") != STATE_PAUSED:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "orchestration_not_resumable",
            "error": "Only paused orchestration can be resumed",
            "orchestrationState": state.get("state"),
        }))
    stage = next_unfinished_stage(snapshot)
    if stage is None:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "no_unfinished_stage",
            "error": "Paused project has no unfinished stage to resume",
            "orchestrationState": state.get("state"),
        }))
    return start_marked_project(
        project_id,
        {
            **body,
            "revision": body.get("revision", state.get("revision")),
            "stage": stage,
            "currentStage": stage,
        },
        repository=repository,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=create_cancel_flag,
    )


def submit_reserved_stage(
    project_id: str,
    run_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    preflight_ports: StagePreflightPorts,
    attempt_ports: StageAttemptPorts,
    dispatcher: BoundedProjectExecutionDispatcher,
    create_cancel_flag: Callable[[str], Any],
) -> MarkedProjectStartOutcome:
    """Prepare and submit tasks for a stage that reconciliation already reserved."""

    body = dict(body or {})
    project_id = str(project_id or "").strip()
    run_id = str(run_id or "").strip()
    if not project_id or not run_id:
        return MarkedProjectStartOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_reserved_stage_submit_request",
            "error": "project_id and run_id are required",
        }))
    snapshot = repository.get(project_id)
    if snapshot is None:
        return MarkedProjectStartOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    if not is_marked_project(snapshot):
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "missing_execution_model",
            "error": "Project is not marked for stage-pipeline orchestration",
        }))
    state = orchestration_state(snapshot)
    if str(state.get("currentRunId") or "") != run_id:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "stage_run_mismatch",
            "error": "Reserved stage run no longer matches the current orchestration run",
            "currentRunId": state.get("currentRunId"),
            "runId": run_id,
        }))
    if state.get("state") != STATE_STARTING:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "orchestration_not_starting",
            "error": "Reserved stage tasks can only be submitted while orchestration is starting",
            "orchestrationState": state.get("state"),
            "runId": run_id,
        }))
    stage = _int_or_none(state.get("currentStage"))
    if stage is None:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "current_stage_required",
            "error": "Cannot submit a reserved stage without currentStage",
            "runId": run_id,
        }))
    stage_tasks = _stage_tasks(snapshot, stage)
    task_ids = tuple(str(task.get("id") or "") for task in stage_tasks if task.get("id"))
    if not task_ids:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "empty_stage",
            "error": "No tasks are assigned to the reserved stage",
            "runId": run_id,
            "currentStage": stage,
        }))
    mismatched = [
        str(task.get("id") or "")
        for task in stage_tasks
        if str(task.get("stageRunId") or "") != run_id
    ]
    if mismatched:
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": "task_not_reserved_for_run",
            "error": "One or more stage tasks are not reserved for this run",
            "taskIds": mismatched,
            "runId": run_id,
            "currentStage": stage,
        }))

    workspace_path = str(snapshot.get("workspacePath") or "").strip()
    workspace = preflight_ports.validate_workspace(workspace_path) if workspace_path else {}
    if not workspace.get("ok"):
        return MarkedProjectStartOutcome(ServiceResult(409, {
            "ok": False,
            "code": str(workspace.get("code") or "workspace_invalid"),
            "error": str(workspace.get("error") or "Project workspace is not ready"),
            "runId": run_id,
            "currentStage": stage,
        }))
    if workspace.get("virtual"):
        git_state = {"ok": True, "dirty": False, "files": [], "fingerprint": "", "truncated": False, "virtual": True}
    else:
        git_state = preflight_ports.git_snapshot(str(workspace.get("path") or workspace_path))
        if git_state.get("error"):
            return MarkedProjectStartOutcome(ServiceResult(409, {
                "ok": False,
                "code": "workspace_git_snapshot_failed",
                "error": "Unable to verify the Git workspace state",
                "runId": run_id,
                "currentStage": stage,
            }))

    roles_by_task_id: dict[str, Mapping[str, Any]] = {}
    for task in stage_tasks:
        task_id = str(task.get("id") or "")
        if task.get("activeAttemptId"):
            return MarkedProjectStartOutcome(ServiceResult(409, {
                "ok": False,
                "code": "active_attempt_exists",
                "error": "Task already has an active attempt",
                "taskId": task_id,
                "runId": run_id,
                "currentStage": stage,
            }))
        roles = preflight_ports.resolve_roles(dict(snapshot), dict(task), bool(body.get("allowSkipReviewer") or body.get("skipReviewConfirmed")))
        if not roles.get("ok"):
            return MarkedProjectStartOutcome(ServiceResult(409, {
                "ok": False,
                "code": str(roles.get("code") or "role_resolution_failed"),
                "error": str(roles.get("error") or "Unable to resolve task execution roles"),
                "taskId": task_id,
                "runId": run_id,
                "currentStage": stage,
            }))
        roles_by_task_id[task_id] = roles

    reservation = StageReservation(
        project=_copy_project(snapshot),
        orchestration=dict(state),
        run_id=run_id,
        stage=stage,
        task_ids=task_ids,
        workspace=dict(workspace),
        git_state=dict(git_state),
        roles_by_task_id=roles_by_task_id,
    )
    attempts: list[StageAttemptPreparation] = []
    submissions: list[StageDispatchSubmission] = []
    diagnostics: list[Mapping[str, Any] | None] = []
    for task_id in reservation.task_ids:
        roles = reservation.roles_by_task_id.get(task_id) or {}
        attempt_outcome = prepare_reserved_task_attempt(
            project_id,
            task_id,
            reservation.run_id,
            repository=repository,
            ports=attempt_ports,
            workspace=reservation.workspace,
            git_state=reservation.git_state,
            roles=roles,
            body={**body, "by": body.get("by") or "stage-dispatch", "autoReviewAfterExecution": body.get("autoReviewAfterExecution", True)},
        )
        if attempt_outcome.result.status != 200 or attempt_outcome.preparation is None:
            payload = dict(attempt_outcome.result.payload)
            payload.setdefault("ok", False)
            payload.setdefault("code", "stage_attempt_prepare_failed")
            payload["preparedTaskIds"] = [attempt.task.get("id") for attempt in attempts]
            return MarkedProjectStartOutcome(ServiceResult(attempt_outcome.result.status, payload), reservation, tuple(attempts), tuple(submissions))
        attempts.append(attempt_outcome.preparation)
        attempt_id = str(attempt_outcome.preparation.attempt.get("id") or "")
        cancel_flag = create_cancel_flag(attempt_id)
        submission = dispatcher.submit(
            project_id=project_id,
            task_id=task_id,
            run_id=reservation.run_id,
            payload={
                "attemptId": attempt_id,
                "cancelFlag": cancel_flag,
                "stage": reservation.stage,
                "revision": reservation.orchestration.get("revision"),
            },
        )
        submissions.append(submission)
        diagnostics.append(submission.diagnostics)
        if not submission.accepted:
            block_result = _persist_dispatch_rejection(
                project_id,
                task_id,
                reservation.run_id,
                submission,
                repository=repository,
                ports=attempt_ports,
            )
            if block_result.status != 200:
                return MarkedProjectStartOutcome(block_result, reservation, tuple(attempts), tuple(submissions))
            return MarkedProjectStartOutcome(ServiceResult(409, {
                "ok": False,
                "code": submission.code,
                "error": "Stage task dispatch was rejected",
                "runId": reservation.run_id,
                "taskId": task_id,
                "currentStage": reservation.stage,
                "preparedTaskIds": [attempt.task.get("id") for attempt in attempts],
                "submittedTaskIds": [item.task_id for item in submissions if item.accepted],
                "submissions": [_submission_payload(item) for item in submissions],
                "diagnostics": _combine_diagnostics(diagnostics),
            }), reservation, tuple(attempts), tuple(submissions))

    return MarkedProjectStartOutcome(ServiceResult(200, {
        "ok": True,
        "status": "reserved_stage_submitted",
        "runId": reservation.run_id,
        "currentRunId": reservation.run_id,
        "currentStage": reservation.stage,
        "taskIds": list(reservation.task_ids),
        "attempts": [
            {
                "taskId": attempt.task.get("id"),
                "attemptId": attempt.attempt.get("id"),
                "idempotent": attempt.idempotent,
            }
            for attempt in attempts
        ],
        "submissions": [_submission_payload(item) for item in submissions],
        "diagnostics": _combine_diagnostics(diagnostics),
    }), reservation, tuple(attempts), tuple(submissions))


def reconcile_stage(
    project_id: str,
    run_id: str,
    *,
    repository: ProjectRepository,
    now: Callable[[], str],
    new_run_id: Callable[[], str],
    on_project_completed: Callable[[dict[str, Any], str], Any] | None = None,
) -> StageReconciliationOutcome:
    """Atomically reconcile a terminal callback for the current stage run."""

    started_ms = monotonic_ms()
    project_id = str(project_id or "").strip()
    run_id = str(run_id or "").strip()
    if not project_id or not run_id:
        return StageReconciliationOutcome(ServiceResult(400, {
            "ok": False,
            "code": "invalid_stage_reconcile_request",
            "error": "project_id and run_id are required",
        }))

    reconciliation_box: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> dict[str, Any]:
        if not is_marked_project(project):
            _reject_reconcile(409, ok=False, code="missing_execution_model", error="Project is not marked for stage-pipeline orchestration")

        validation = validate_stage_invariants(project)
        if not validation.ok:
            _reject_reconcile(
                409,
                ok=False,
                code=validation.issues[0].code if validation.issues else "invalid_orchestration",
                error="Project orchestration invariants are invalid",
                issues=[
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "taskId": issue.task_id,
                        "stage": issue.stage,
                    }
                    for issue in validation.issues
                ],
            )

        state = orchestration_state(project)
        current_run_id = str(state.get("currentRunId") or "")
        if current_run_id != run_id:
            reconciliation_box.update({
                "project": _copy_project(project),
                "orchestration": dict(state),
                "status": "stale_run_ignored",
                "currentStage": _int_or_none(state.get("currentStage")),
                "nextStage": None,
                "nextRunId": None,
                "pendingTaskIds": (),
                "taskIds": (),
                "idempotent": True,
                "diagnostics": duplicate_suppression_diagnostics(
                    project_id=str(project.get("id") or project_id),
                    stage=_int_or_none(state.get("currentStage")),
                    run_id=run_id,
                    revision=int(state.get("revision") or 0),
                    status="stale_run_ignored",
                ),
            })
            return _service_payload(
                200,
                ok=True,
                status="stale_run_ignored",
                runId=run_id,
                currentRunId=state.get("currentRunId"),
                currentStage=state.get("currentStage"),
                idempotent=True,
                diagnostics=reconciliation_box["diagnostics"],
            )

        current_stage = _int_or_none(state.get("currentStage"))
        if current_stage is None:
            _reject_reconcile(
                409,
                ok=False,
                code="current_stage_required",
                error="Cannot reconcile a stage without a currentStage",
                runId=run_id,
            )
        if state.get("state") == STATE_PAUSING:
            reconciliation_box.update({
                "project": _copy_project(project),
                "orchestration": dict(state),
                "status": "stage_pausing",
                "currentStage": current_stage,
                "nextStage": None,
                "nextRunId": None,
                "pendingTaskIds": (),
                "taskIds": (),
                "idempotent": True,
                "diagnostics": duplicate_suppression_diagnostics(
                    project_id=str(project.get("id") or project_id),
                    stage=current_stage,
                    run_id=run_id,
                    revision=int(state.get("revision") or 0),
                    status="stage_pausing",
                ),
            })
            return _service_payload(
                200,
                ok=True,
                status="stage_pausing",
                runId=run_id,
                currentRunId=run_id,
                currentStage=current_stage,
                idempotent=True,
                diagnostics=reconciliation_box["diagnostics"],
            )
        if state.get("state") not in {STATE_STARTING, STATE_RUNNING}:
            _reject_reconcile(
                409,
                ok=False,
                code="orchestration_not_reconcilable",
                error="Only starting or running orchestration can reconcile a stage",
                orchestrationState=state.get("state"),
                runId=run_id,
                currentStage=current_stage,
            )

        stage_tasks = _stage_tasks(project, current_stage)
        if not stage_tasks:
            _reject_reconcile(
                409,
                ok=False,
                code="empty_current_stage",
                error="No tasks are assigned to the current stage",
                runId=run_id,
                currentStage=current_stage,
            )
        pending_task_ids = tuple(
            str(task.get("id") or "")
            for task in stage_tasks
            if not task_is_accepted_terminal(task)
        )
        if pending_task_ids:
            reconciliation_box.update({
                "project": _copy_project(project),
                "orchestration": dict(state),
                "status": "stage_waiting",
                "currentStage": current_stage,
                "nextStage": None,
                "nextRunId": None,
                "pendingTaskIds": pending_task_ids,
                "taskIds": tuple(str(task.get("id") or "") for task in stage_tasks),
                "idempotent": True,
                "diagnostics": duplicate_suppression_diagnostics(
                    project_id=str(project.get("id") or project_id),
                    stage=current_stage,
                    run_id=run_id,
                    revision=int(state.get("revision") or 0),
                    status="stage_waiting",
                    pending_task_ids=pending_task_ids,
                ),
            })
            return _service_payload(
                200,
                ok=True,
                status="stage_waiting",
                runId=run_id,
                currentRunId=run_id,
                currentStage=current_stage,
                pendingTaskIds=list(pending_task_ids),
                idempotent=True,
                diagnostics=reconciliation_box["diagnostics"],
            )

        stages = sorted(tasks_by_stage(project))
        next_stage = next((stage for stage in stages if stage > current_stage), None)
        timestamp = now()
        record_stage_handoff(project, current_stage, generated_at=timestamp)
        raw_orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
        if isinstance(raw_orchestration.get("stageHandoffs"), Mapping):
            state["stageHandoffs"] = dict(raw_orchestration["stageHandoffs"])
        if next_stage is None:
            state.update({
                "state": STATE_COMPLETED,
                "currentRunId": None,
                "pauseReason": None,
                "completedAt": state.get("completedAt") or timestamp,
                "revision": int(state.get("revision") or 0) + 1,
            })
            project["orchestration"] = state
            project["status"] = "completed"
            project["updatedAt"] = timestamp
            diagnostics = stage_advancement_diagnostics(
                project_id=str(project.get("id") or project_id),
                stage=current_stage,
                run_id=run_id,
                revision=int(state.get("revision") or 0),
                status="project_completed",
                duration_ms=elapsed_ms(started_ms),
            )
            append_project_audit(project, diagnostics, at=timestamp)
            reconciliation_box.update({
                "project": _copy_project(project),
                "orchestration": dict(state),
                "status": "project_completed",
                "currentStage": current_stage,
                "nextStage": None,
                "nextRunId": None,
                "pendingTaskIds": (),
                "taskIds": tuple(str(task.get("id") or "") for task in stage_tasks),
                "idempotent": False,
                "diagnostics": diagnostics,
            })
            return _service_payload(
                200,
                ok=True,
                status="project_completed",
                runId=run_id,
                currentRunId=None,
                currentStage=current_stage,
                idempotent=False,
                diagnostics=diagnostics,
            )

        next_run_id = str(new_run_id() or "").strip()
        if not next_run_id:
            _reject_reconcile(
                500,
                ok=False,
                code="missing_stage_run_id",
                error="Unable to allocate next stage run id",
                runId=run_id,
                currentStage=current_stage,
                nextStage=next_stage,
            )
        next_tasks = _stage_tasks(project, next_stage)
        state.update({
            "state": STATE_STARTING,
            "currentStage": next_stage,
            "currentRunId": next_run_id,
            "pauseReason": None,
            "revision": int(state.get("revision") or 0) + 1,
        })
        project["orchestration"] = state
        project["updatedAt"] = timestamp
        for task in next_tasks:
            task["stageRunId"] = next_run_id
            task["updatedAt"] = timestamp
        next_task_ids = tuple(str(task.get("id") or "") for task in next_tasks)
        diagnostics = stage_advancement_diagnostics(
            project_id=str(project.get("id") or project_id),
            stage=current_stage,
            run_id=run_id,
            revision=int(state.get("revision") or 0),
            status="stage_advanced",
            next_stage=next_stage,
            next_run_id=next_run_id,
            duration_ms=elapsed_ms(started_ms),
        )
        append_project_audit(project, diagnostics, at=timestamp)
        reconciliation_box.update({
            "project": _copy_project(project),
            "orchestration": dict(state),
            "status": "stage_advanced",
            "currentStage": current_stage,
            "nextStage": next_stage,
            "nextRunId": next_run_id,
            "pendingTaskIds": (),
            "taskIds": next_task_ids,
            "idempotent": False,
            "diagnostics": diagnostics,
        })
        return _service_payload(
            200,
            ok=True,
            status="stage_advanced",
            runId=run_id,
            currentRunId=next_run_id,
            currentStage=next_stage,
            previousStage=current_stage,
            nextStage=next_stage,
            taskIds=list(next_task_ids),
            idempotent=False,
            diagnostics=diagnostics,
        )

    try:
        result = repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return StageReconciliationOutcome(ServiceResult(404, {"ok": False, "error": "Project not found"}))
    except _StageReconciliationRejected as exc:
        return StageReconciliationOutcome(exc.result)
    except ProjectConflictError:
        return StageReconciliationOutcome(ServiceResult(409, {
            "ok": False,
            "code": "stage_reconciliation_commit_conflict",
            "error": "Project changed during stage reconciliation",
            "runId": run_id,
        }))

    service_result = ServiceResult(int(result.pop("_status", 200)), result)
    if service_result.status != 200 or not reconciliation_box:
        return StageReconciliationOutcome(service_result)
    reconciliation = StageReconciliation(
        project=reconciliation_box["project"],
        orchestration=reconciliation_box["orchestration"],
        status=str(reconciliation_box["status"]),
        run_id=run_id,
        current_stage=reconciliation_box["currentStage"],
        next_stage=reconciliation_box["nextStage"],
        next_run_id=reconciliation_box["nextRunId"],
        pending_task_ids=reconciliation_box["pendingTaskIds"],
        task_ids=reconciliation_box["taskIds"],
        idempotent=bool(reconciliation_box["idempotent"]),
    )
    if reconciliation.status == "project_completed" and on_project_completed is not None:
        notification_project = _copy_project(reconciliation.project)
        try:
            notification_result = on_project_completed(
                notification_project,
                "Project pipeline completed after the final stage reached accepted terminal outcomes.",
            )
            _persist_project_completion_notification(
                project_id,
                notification_project,
                repository=repository,
            )
        except Exception as exc:
            notification_result = {
                "ok": False,
                "status": "delivery_failed",
                "error": str(exc),
            }
        payload = dict(service_result.payload)
        payload["notification"] = notification_result
        service_result = ServiceResult(service_result.status, payload)
    return StageReconciliationOutcome(service_result, reconciliation)


def _persist_project_completion_notification(
    project_id: str,
    notification_project: Mapping[str, Any],
    *,
    repository: ProjectRepository,
) -> None:
    markers = notification_project.get("feishuNotifications")
    if not isinstance(markers, Mapping):
        return

    def mutate(project: dict[str, Any]) -> None:
        project["feishuNotifications"] = dict(markers)

    try:
        repository.update(project_id, mutate)
    except (ProjectNotFoundError, ProjectConflictError):
        return


def _persist_dispatch_rejection(
    project_id: str,
    task_id: str,
    run_id: str,
    submission: StageDispatchSubmission,
    *,
    repository: ProjectRepository,
    ports: StageAttemptPorts,
) -> ServiceResult:
    reason = submission.code or QUEUE_FULL_CODE

    def mutate(project: dict[str, Any]) -> dict[str, Any]:
        state = orchestration_state(project)
        task = _find_task(project, task_id)
        if task is None:
            _reject_attempt(404, ok=False, error="Project or task not found")
        if state.get("currentRunId") != run_id:
            _reject_attempt(
                409,
                ok=False,
                code="stage_run_mismatch",
                error="Cannot block rejected task because the stage run changed",
                currentRunId=state.get("currentRunId"),
                runId=run_id,
                taskId=task_id,
            )
        if str(task.get("stageRunId") or "") != run_id:
            _reject_attempt(
                409,
                ok=False,
                code="task_not_reserved_for_run",
                error="Cannot block rejected task because it is not reserved for this run",
                taskId=task_id,
                runId=run_id,
                stageRunId=task.get("stageRunId"),
            )
        now = ports.now()
        attempt_id = str(task.get("activeAttemptId") or "")
        attempt = _matching_stage_attempt(task, run_id)
        if attempt is not None:
            attempt["status"] = "blocked"
            attempt["blockedAt"] = now
            attempt["blockedReason"] = reason
        state["state"] = STATE_BLOCKED
        state["pauseReason"] = reason
        state["revision"] = int(state.get("revision") or 0) + 1
        project["orchestration"] = state
        project["updatedAt"] = now
        task["activeAttemptId"] = None
        task["blockedReason"] = reason
        task["lastError"] = reason
        task["updatedAt"] = now
        ports.transition(project, task, "blocked", "stage-dispatch", reason, attempt_id or None)
        return _service_payload(200, ok=True, code=reason, taskId=task_id, runId=run_id)

    try:
        result = repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return ServiceResult(404, {"ok": False, "error": "Project or task not found"})
    except _StageAttemptRejected as exc:
        return exc.result
    except ProjectConflictError:
        return ServiceResult(409, {
            "ok": False,
            "code": "dispatch_rejection_commit_conflict",
            "error": "Project changed while recording dispatch rejection",
            "taskId": task_id,
            "runId": run_id,
        })
    return ServiceResult(int(result.pop("_status", 200)), result)


class _StageReservationRejected(RuntimeError):
    def __init__(self, result: ServiceResult) -> None:
        super().__init__(str(result.payload.get("code") or "stage reservation rejected"))
        self.result = result


def _revision(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        revision = int(value)
    except (TypeError, ValueError):
        return None
    return revision if revision >= 0 else None


def _actor(body: Mapping[str, Any]) -> dict[str, Any]:
    raw = body.get("actor")
    if isinstance(raw, Mapping):
        return dict(raw)
    return {"type": str(body.get("actorType") or "management"), "id": str(body.get("by") or "user")}


def _requested_stage(project: Mapping[str, Any], body: Mapping[str, Any]) -> int:
    raw = body.get("currentStage", body.get("stage"))
    if raw is None:
        state = orchestration_state(project)
        raw = state.get("currentStage") or 1
    try:
        stage = int(raw)
    except (TypeError, ValueError):
        return 0
    return stage if stage > 0 else 0


def _stage_tasks(project: Mapping[str, Any], stage: int) -> list[dict[str, Any]]:
    return [
        task
        for task in tasks_by_stage(project).get(stage, [])
        if isinstance(task, dict) and task.get("id")
    ]


def _find_task(project: Mapping[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in project.get("tasks") or []:
        if isinstance(task, dict) and str(task.get("id") or "") == str(task_id):
            return task
    return None


def _matching_stage_attempt(task: Mapping[str, Any], run_id: str) -> Mapping[str, Any] | None:
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and attempt.get("stageRunId") == run_id:
            return attempt
    return None


def _service_payload(http_status: int, **payload: Any) -> dict[str, Any]:
    return {"_status": http_status, **payload}


def _submission_payload(submission: StageDispatchSubmission) -> dict[str, Any]:
    return {
        "accepted": submission.accepted,
        "code": submission.code,
        "projectId": submission.project_id,
        "taskId": submission.task_id,
        "runId": submission.run_id,
        "queued": submission.queued,
        "inFlight": submission.in_flight,
        "workerCount": submission.worker_count,
        "queueCapacity": submission.queue_capacity,
        "diagnostics": dict(submission.diagnostics),
    }


def _combine_diagnostics(items: list[Mapping[str, Any] | None]) -> dict[str, Any]:
    from .project_orchestration_observability import combine_diagnostics

    return combine_diagnostics(*items)


class _StageAttemptRejected(RuntimeError):
    def __init__(self, result: ServiceResult) -> None:
        super().__init__(str(result.payload.get("code") or "stage attempt rejected"))
        self.result = result


class _StageReconciliationRejected(RuntimeError):
    def __init__(self, result: ServiceResult) -> None:
        super().__init__(str(result.payload.get("code") or "stage reconciliation rejected"))
        self.result = result


def _reject_attempt(status: int, **payload: Any) -> None:
    raise _StageAttemptRejected(ServiceResult(status, dict(payload)))


def _reject_reconcile(status: int, **payload: Any) -> None:
    raise _StageReconciliationRejected(ServiceResult(status, dict(payload)))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _preflight(
    project: Mapping[str, Any],
    stage: int,
    expected_revision: int,
    actor: Mapping[str, Any],
    body: Mapping[str, Any],
    ports: StagePreflightPorts,
    *,
    include_external: bool = True,
    expected_workspace_path: str | None = None,
) -> tuple[list[StagePreflightBlocker], dict[str, Any]]:
    blockers: list[StagePreflightBlocker] = []
    context: dict[str, Any] = {"workspace": {}, "gitState": {}, "rolesByTaskId": {}}
    state = orchestration_state(project)

    if not is_marked_project(project):
        blockers.append(StagePreflightBlocker("missing_execution_model", "Project is not marked for stage-pipeline orchestration"))
    validation = validate_stage_invariants(project)
    for issue in validation.issues:
        blockers.append(StagePreflightBlocker(issue.code, issue.message, task_id=issue.task_id, stage=issue.stage))
    if int(state.get("revision") or 0) != expected_revision:
        blockers.append(StagePreflightBlocker(
            "orchestration_revision_conflict",
            "Orchestration revision changed",
            details={"expectedRevision": expected_revision, "currentRevision": int(state.get("revision") or 0)},
        ))
    if state.get("state") not in {STATE_DRAFT, STATE_PAUSED, STATE_BLOCKED}:
        blockers.append(StagePreflightBlocker(
            "orchestration_not_startable",
            "Only draft, paused, or blocked orchestration can reserve a stage",
            details={"orchestrationState": state.get("state")},
        ))
    if stage <= 0:
        blockers.append(StagePreflightBlocker("invalid_stage", "currentStage must be a positive integer"))
    stage_tasks = _stage_tasks(project, stage)
    if not stage_tasks:
        blockers.append(StagePreflightBlocker("empty_stage", "No tasks are assigned to the requested stage", stage=stage))

    if include_external:
        auth = ports.authorize(dict(project), actor)
        if not auth.get("ok"):
            blockers.append(StagePreflightBlocker(
                str(auth.get("code") or "orchestration_authorization_failed"),
                str(auth.get("error") or "Actor is not authorized to reserve this stage"),
                details={key: value for key, value in auth.items() if key not in {"ok", "error"}},
            ))

    workspace_path = str(project.get("workspacePath") or "").strip()
    context["workspacePath"] = workspace_path
    if not project.get("projectExecutionEnabled"):
        blockers.append(StagePreflightBlocker("project_execution_disabled", "Project Execution is not enabled for this project"))
    if not workspace_path:
        blockers.append(StagePreflightBlocker("workspace_required", "Project workspace is required before execution can start"))
    elif not include_external:
        if expected_workspace_path and workspace_path != expected_workspace_path:
            blockers.append(StagePreflightBlocker(
                "workspace_changed",
                "Project workspace changed while stage execution was being prepared",
                details={"expectedWorkspacePath": expected_workspace_path, "currentWorkspacePath": workspace_path},
            ))
    else:
        workspace = ports.validate_workspace(workspace_path)
        context["workspace"] = dict(workspace)
        if not workspace.get("ok"):
            blockers.append(StagePreflightBlocker(
                str(workspace.get("code") or "workspace_invalid"),
                str(workspace.get("error") or "Project workspace is not ready"),
                details={key: value for key, value in workspace.items() if key not in {"ok", "error"}},
            ))
        elif workspace.get("virtual"):
            context["gitState"] = {"ok": True, "dirty": False, "files": [], "fingerprint": "", "truncated": False, "virtual": True}
        else:
            git_state = ports.git_snapshot(str(workspace.get("path") or workspace_path))
            context["gitState"] = dict(git_state)
            if git_state.get("error"):
                blockers.append(StagePreflightBlocker("workspace_git_snapshot_failed", "Unable to verify the Git workspace state"))
            elif git_state.get("dirty") and str(body.get("dirtyFingerprint") or "") != git_state.get("fingerprint"):
                blockers.append(StagePreflightBlocker(
                    "dirty_worktree_confirmation_required",
                    "Dirty workspace confirmation is required",
                    details={
                        "dirtyFingerprint": git_state.get("fingerprint"),
                        "dirtyFiles": list(git_state.get("files") or [])[:50],
                        "truncated": bool(git_state.get("truncated")),
                    },
                ))

    roles_by_task_id: dict[str, Mapping[str, Any]] = {}
    for task in stage_tasks:
        task_id = str(task.get("id") or "")
        if _task_has_any_active_attempt(task):
            blockers.append(StagePreflightBlocker("active_attempt_exists", "Task already has an active attempt", task_id=task_id, stage=stage))
        if str(task.get("stageRunId") or "").strip():
            blockers.append(StagePreflightBlocker("task_already_reserved", "Task is already reserved for a stage run", task_id=task_id, stage=stage))
        if include_external:
            roles = ports.resolve_roles(dict(project), dict(task), bool(body.get("allowSkipReviewer")))
            if not roles.get("ok"):
                blockers.append(StagePreflightBlocker(
                    str(roles.get("code") or "role_resolution_failed"),
                    str(roles.get("error") or "Unable to resolve task execution roles"),
                    task_id=task_id,
                    stage=stage,
                    details={key: value for key, value in roles.items() if key not in {"ok", "error"}},
                ))
            else:
                roles_by_task_id[task_id] = roles
    context["rolesByTaskId"] = roles_by_task_id

    for task in project.get("tasks") or []:
        if isinstance(task, Mapping) and task not in stage_tasks and _task_has_any_active_attempt(task):
            blockers.append(StagePreflightBlocker(
                "project_has_active_attempt",
                "Another project task already has an active attempt",
                task_id=str(task.get("id") or ""),
                stage=task_stage(task),
            ))
    return blockers, context


def _task_has_any_active_attempt(task: Mapping[str, Any]) -> bool:
    if task_has_active_attempt(task):
        return True
    if str(task.get("stageRunId") or "").strip() and str(task.get("executionState") or "").lower() not in {"done", "completed"}:
        return True
    return False


def _blocker_result(blockers: list[StagePreflightBlocker], context: Mapping[str, Any], status: int) -> ServiceResult:
    payload = {
        "ok": False,
        "code": blockers[0].code if blockers else "stage_preflight_blocked",
        "error": "Stage reservation preflight failed",
        "blockers": [
            {
                "code": item.code,
                "message": item.message,
                "taskId": item.task_id,
                "stage": item.stage,
                **dict(item.details),
            }
            for item in blockers
        ],
    }
    if context.get("gitState", {}).get("dirty"):
        payload["dirtyFingerprint"] = context["gitState"].get("fingerprint")
        payload["dirtyFiles"] = list(context["gitState"].get("files") or [])[:50]
        payload["truncated"] = bool(context["gitState"].get("truncated"))
    return ServiceResult(status, payload)


def _copy_project(project: Mapping[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(dict(project))


__all__ = [
    "BoundedProjectExecutionDispatcher",
    "DEFAULT_STAGE_DISPATCH_QUEUE_CAPACITY",
    "DEFAULT_STAGE_DISPATCH_WORKERS",
    "QUEUE_FULL_CODE",
    "StageDispatchResult",
    "StageDispatchSubmission",
    "StageDispatchWorkItem",
    "StageAttemptOutcome",
    "StageAttemptPorts",
    "StageAttemptPreparation",
    "MarkedProjectStartOutcome",
    "StageReconciliation",
    "StageReconciliationOutcome",
    "StagePreflightBlocker",
    "StagePreflightPorts",
    "StageReservation",
    "StageReservationOutcome",
    "prepare_reserved_task_attempt",
    "reconcile_stage",
    "reserve_stage_run",
    "start_marked_project",
]
