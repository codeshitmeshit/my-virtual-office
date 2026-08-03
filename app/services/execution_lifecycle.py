"""Project Execution lifecycle commands independent of HTTP and ``server.py``.

The module owns the atomic start/status/cancel state transitions.  Slow workspace,
Git, provider-launch and provider-cancel work is supplied through explicit ports and
runs outside the repository's project lock.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from services import project_execution_prompt_formatting
from services.project_execution_ordering import prior_incomplete_task
from services.project_orchestration import active_task_ids, is_marked_project, orchestration_state
from services.project_repository import ProjectNotFoundError


Project = dict[str, Any]
Task = dict[str, Any]

STALE_RECONCILE_STATES = frozenset({
    "validating",
    "executing",
    "retrying",
    "reviewing",
    "reworking",
})
STAGE_PIPELINE_ACTIVE_STATES = frozenset({"starting", "running", "pausing"})


class Repository(Protocol):
    def get(self, project_id: str) -> Project: ...
    def update(self, project_id: str, mutator: Callable[[Project], Any]) -> Any: ...


class CancelRegistry:
    """Thread-safe attempt cancellation registry used by lifecycle adapters."""

    def __init__(self, lock: threading.Lock | None = None, flags: dict[str, threading.Event] | None = None) -> None:
        self._lock = lock or threading.Lock()
        self._flags = flags if flags is not None else {}

    def create(self, attempt_id: str) -> threading.Event:
        flag = threading.Event()
        with self._lock:
            self._flags[attempt_id] = flag
        return flag

    def get(self, attempt_id: str) -> threading.Event | None:
        with self._lock:
            return self._flags.get(attempt_id)

    def cancel(self, attempt_id: str) -> bool:
        flag = self.get(attempt_id)
        if flag is None:
            return False
        flag.set()
        return True

    def discard(self, attempt_id: str) -> None:
        with self._lock:
            self._flags.pop(attempt_id, None)

    def is_live(self, attempt_id: str) -> bool:
        with self._lock:
            return attempt_id in self._flags


@dataclass(frozen=True)
class StartPorts:
    validate_workspace: Callable[[str], dict[str, Any]]
    git_snapshot: Callable[[str], dict[str, Any]]
    resolve_roles: Callable[[Project, Task, bool], dict[str, Any]]
    active_task: Callable[[Project], Task | None]
    start_mode: Callable[[Project, dict[str, Any]], str]
    requires_acceptance: Callable[[Task], bool]
    reopen_completed_task: Callable[..., bool]
    clear_restart_bindings: Callable[..., Any]
    seed_checklist: Callable[..., bool]
    has_pending_meeting_actions: Callable[[Task], bool]
    transition: Callable[[Project, Task, str, str, str, str | None], Any]
    now: Callable[[], str]
    new_id: Callable[[], str]
    launcher: Callable[[Callable[[], None]], Any]
    runner: Callable[[str, str, str, threading.Event], Any]
    notify_intervention: Callable[..., Any]


@dataclass(frozen=True)
class ProviderInvocation:
    project: Project
    task: Task
    attempt: dict[str, Any]
    executor: dict[str, Any]
    workspace: str
    result: dict[str, Any]
    started_at: float


@dataclass(frozen=True)
class RunnerPorts:
    repository: Repository
    build_prompt: Callable[..., str]
    provider: Callable[..., dict[str, Any]]
    git_snapshot: Callable[[str], dict[str, Any]]
    find: Callable[..., tuple[dict[str, Any], Project | None, Task | None]]
    find_attempt: Callable[[Task, str], dict[str, Any] | None]
    apply_checklist_updates: Callable[[Task, dict[str, Any]], bool]
    apply_meeting_discussion_points: Callable[[Task, dict[str, Any]], bool]
    redact: Callable[[Any], str]
    now: Callable[[], str]
    acceptance_checklist: Callable[[Task], list[Any]]
    test_evidence: Callable[[dict[str, Any]], Any]
    transition: Callable[..., Any]
    notify_intervention: Callable[..., Any]
    mark_meeting_actions_completed: Callable[..., Any]
    move_task_to_column: Callable[..., Any]
    backlog_column: Callable[[Project], Any]
    commit_projects: Callable[[str, str, str, dict[str, Any], Project], bool]
    cancel_registry: CancelRegistry
    has_pending_meeting_actions: Callable[[Task], bool]
    launcher: Callable[[Callable[[], None]], Any]
    start_task: Callable[[str, str, dict[str, Any]], dict[str, Any]]
    attempt_requires_acceptance: Callable[[Task, dict[str, Any]], bool]
    stage_acceptance: Callable[..., str]
    deliver_notification: Callable[[str, str, str, str], Any]
    mark_done: Callable[..., dict[str, Any]]
    continue_incomplete_checklist: Callable[..., dict[str, Any]]
    schedule_continue: Callable[..., Any]
    transient_failure_reason: Callable[[dict[str, Any]], str | None]
    schedule_transient_retry: Callable[..., bool]
    start_review: Callable[..., dict[str, Any]]
    finalize_cancel: Callable[[str, str, str, dict[str, Any]], bool]
    is_stage_pipeline: Callable[[Project], bool] = lambda project: False
    reconcile_terminal: Callable[[str, str, str, str], Any] = lambda project_id, task_id, attempt_id, reason: None
    seed_checklist: Callable[..., bool] | None = None


def invoke_provider(
    project_id: str,
    task_id: str,
    attempt_id: str,
    *,
    repository: Repository,
    monotonic: Callable[[], float],
    build_prompt: Callable[[Project, Task, dict[str, Any], str], str],
    provider: Callable[..., dict[str, Any]],
) -> ProviderInvocation | None:
    """Read a persisted attempt and perform Provider work without a project lock."""
    project = repository.get(project_id)
    if project is None:
        return None
    task = _find_task(project, task_id)
    if task is None or task.get("activeAttemptId") != attempt_id:
        return None
    attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
    if attempt is None:
        return None
    workspace = str(attempt.get("workspacePath") or "")
    executor = copy.deepcopy(attempt.get("executor") or {})
    started_at = monotonic()
    result = provider(
        executor,
        build_prompt(project, task, attempt, workspace),
        workspace,
        attempt_id,
        project_id=project_id,
        task_id=task_id,
    )
    return ProviderInvocation(project, task, attempt, executor, workspace, result, started_at)


def _checklist_needs_planning(task: Task, attempt: dict[str, Any], ports: RunnerPorts) -> bool:
    if attempt.get("meetingActionPhase") or attempt.get("rework") or attempt.get("reworkCycle"):
        return False
    acceptance_checklist = getattr(ports, "acceptance_checklist", lambda value: value.get("checklist") or [])
    return not bool(acceptance_checklist(task))


def _build_checklist_planning_prompt(project: Project, task: Task, attempt: dict[str, Any], workspace: str) -> str:
    return project_execution_prompt_formatting.render_checklist_planning_prompt(
        project=project,
        task=task,
        attempt=attempt,
        workspace=workspace,
    )


def _planning_failure_result(planning_result: dict[str, Any], message: str) -> dict[str, Any]:
    reply = str(planning_result.get("reply") or "")
    error = str(planning_result.get("error") or "").strip() or message
    return {
        "ok": False,
        "reply": reply,
        "error": error,
        "status": "checklist_planning_failed",
        "planningResult": copy.deepcopy(planning_result),
    }


def _persist_checklist_planning(
    project_id: str,
    task_id: str,
    attempt_id: str,
    planning_result: dict[str, Any],
    *,
    repository: Repository,
    ports: RunnerPorts,
) -> bool:
    outcome = {"persisted": False}

    def apply(project: Project) -> None:
        task = _find_task(project, task_id)
        if task is None or task.get("activeAttemptId") != attempt_id:
            return
        attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
        if attempt is None:
            return
        changed = ports.apply_checklist_updates(task, planning_result)
        checklist = ports.acceptance_checklist(task)
        if not changed or not checklist:
            seed_checklist = getattr(ports, "seed_checklist", None)
            if callable(seed_checklist):
                changed = bool(seed_checklist(task, "project_execution_seed"))
                checklist = ports.acceptance_checklist(task)
        attempt["checklistPlanning"] = {
            "status": planning_result.get("status") or ("completed" if planning_result.get("ok") else "failed"),
            "checklistUpdated": changed,
            "plannedAt": ports.now(),
            "reply": ports.redact(planning_result.get("reply") or "")[:4000],
            "error": ports.redact(planning_result.get("error") or ""),
        }
        if changed and checklist:
            task["updatedAt"] = ports.now()
            project["updatedAt"] = ports.now()
            outcome["persisted"] = True

    repository.update(project_id, apply)
    return bool(outcome.get("persisted"))


def invoke_provider_with_checklist_planning(
    project_id: str,
    task_id: str,
    attempt_id: str,
    *,
    repository: Repository,
    monotonic: Callable[[], float],
    ports: RunnerPorts,
) -> ProviderInvocation | None:
    """Run an optional checklist-planning round, then execute the task."""
    project = repository.get(project_id)
    if project is None:
        return None
    task = _find_task(project, task_id)
    if task is None or task.get("activeAttemptId") != attempt_id:
        return None
    attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
    if attempt is None:
        return None
    workspace = str(attempt.get("workspacePath") or "")
    executor = copy.deepcopy(attempt.get("executor") or {})

    if _checklist_needs_planning(task, attempt, ports):
        planning_result = ports.provider(
            executor,
            _build_checklist_planning_prompt(project, task, attempt, workspace),
            workspace,
            attempt_id,
            project_id=project_id,
            task_id=task_id,
        )
        if not planning_result.get("ok"):
            return ProviderInvocation(project, task, attempt, executor, workspace, _planning_failure_result(
                planning_result,
                "Checklist planning failed before task execution.",
            ), monotonic())
        if not _persist_checklist_planning(project_id, task_id, attempt_id, planning_result, repository=repository, ports=ports):
            return ProviderInvocation(project, task, attempt, executor, workspace, _planning_failure_result(
                planning_result,
                "Checklist planning did not produce persisted acceptance criteria.",
            ), monotonic())
        project = repository.get(project_id)
        if project is None:
            return None
        task = _find_task(project, task_id)
        if task is None or task.get("activeAttemptId") != attempt_id:
            return None
        attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
        if attempt is None:
            return None
        workspace = str(attempt.get("workspacePath") or "")
        executor = copy.deepcopy(attempt.get("executor") or {})

    started_at = monotonic()
    result = ports.provider(
        executor,
        ports.build_prompt(project, task, attempt, workspace),
        workspace,
        attempt_id,
        project_id=project_id,
        task_id=task_id,
    )
    return ProviderInvocation(project, task, attempt, executor, workspace, result, started_at)


def attempt_is_committable(task: Task | None, attempt_id: str) -> bool:
    """Reject stale Provider results after cancel/restart replaced the attempt."""
    if task is None:
        return False
    attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
    return bool(attempt and task.get("activeAttemptId") == attempt_id)


def _find_task(project: Project, task_id: str) -> Task | None:
    return next((task for task in project.get("tasks", []) if task.get("id") == task_id), None)


def _stage_pipeline_status(project: Project, task: Task | None = None) -> dict[str, Any]:
    state = orchestration_state(project)
    phase = str(state.get("state") or "draft")
    active_ids = list(active_task_ids(project))
    active = bool(active_ids)
    visible_phase = phase if active else "idle"
    return {
        "ok": True,
        "active": active,
        "phase": visible_phase,
        "currentTaskId": active_ids[0] if len(active_ids) == 1 else None,
        "activeTaskIds": active_ids,
        "startMode": None,
        "flowActive": active,
        "flowStopReason": state.get("pauseReason"),
        "task": task,
        "executionModel": project.get("executionModel"),
        "orchestration": state,
        "orchestrationState": phase,
        "currentStage": state.get("currentStage"),
        "runId": state.get("currentRunId"),
    }


def _status(payload: dict[str, Any], status: int) -> dict[str, Any]:
    return {**payload, **({"_status": status} if status != 200 else {})}


def _notify_start_failure(
    repository: Repository,
    project_id: str,
    task_id: str,
    payload: dict[str, Any],
    notify: Callable[..., Any],
) -> None:
    """Deliver start intervention outside locks, then persist its dedupe marker."""
    try:
        project = repository.get(project_id)
        task = _find_task(project, task_id) if project else None
        if task is None:
            return
        notify(
            project,
            task,
            payload.get("error") or "Project Execution needs user attention.",
            task.get("activeAttemptId"),
            event="start_failed",
            kind="error",
        )
        markers = copy.deepcopy(task.get("feishuNotifications") or {})
        if not markers:
            return

        def persist(latest: Project) -> None:
            latest_task = _find_task(latest, task_id)
            if latest_task is not None:
                latest_task["feishuNotifications"] = markers

        repository.update(project_id, persist)
    except (ProjectNotFoundError, RuntimeError):
        return


def _blocked_checklist_items(task: Task, *, limit: int = 8) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in task.get("checklist") or []:
        if not isinstance(item, dict):
            continue
        if item.get("source") in {"meeting_action_item", "meeting_risk"}:
            continue
        if item.get("done") is True:
            continue
        item_id = str(item.get("id") or "").strip()
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        key = item_id or text
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": item_id,
            "text": text,
            "evidence": str(item.get("evidence") or "").strip(),
        })
        if len(items) >= limit:
            break
    return items


def transition(
    project: Project,
    task: Task,
    next_state: str,
    actor: str,
    reason: str,
    attempt_id: str | None,
    *,
    now: Callable[[], str],
    sync_column: Callable[[Project, Task, str], Any],
    log_activity: Callable[..., Any],
    redact: Callable[[Any], str],
) -> None:
    """Apply the compatible task transition and bounded state-history update."""
    previous = task.get("executionState") or ("done" if task.get("completedAt") else "backlog")
    if next_state == "blocked" and task.get("lastError") == "checklist_incomplete_rework_limit" and not task.get("blockedChecklistItems"):
        task["blockedChecklistItems"] = _blocked_checklist_items(task)
    task["executionState"] = next_state
    task["updatedAt"] = now()
    if next_state != "done":
        task["completedAt"] = None
    sync_column(project, task, next_state)
    project["updatedAt"] = now()
    log_activity(
        project,
        "project_execution_state_changed",
        actor,
        f"Project Execution task '{task.get('title', '')}' changed from {previous} to {next_state}: {reason}",
        task.get("id"),
    )
    task.setdefault("stateHistory", []).append(
        {"attemptId": attempt_id, "actor": actor, "from": previous, "to": next_state, "reason": redact(reason), "at": now()}
    )
    task["stateHistory"] = task["stateHistory"][-100:]


def _claim_attempt_runner(project_id: str, task_id: str, attempt_id: str, ports: RunnerPorts) -> bool:
    update = getattr(ports.repository, "update", None)
    find_attempt = getattr(ports, "find_attempt", None)
    if not callable(update) or not callable(find_attempt):
        return True

    def claim(project: Project) -> bool:
        task = _find_task(project, task_id)
        attempt = find_attempt(task or {}, attempt_id)
        if not task or not attempt:
            return False
        if not attempt_is_committable(task, attempt_id):
            return False
        if attempt.get("runnerClaimedAt"):
            return False
        attempt["runnerClaimedAt"] = ports.now()
        return True

    try:
        return bool(update(project_id, claim))
    except ProjectNotFoundError:
        return False


def _attempt_waiting_for_human_decision(
    project_id: str,
    task_id: str,
    attempt_id: str,
    ports: RunnerPorts,
) -> bool:
    try:
        project = ports.repository.get(project_id)
    except ProjectNotFoundError:
        return False
    task = _find_task(project or {}, task_id)
    if not task or task.get("activeAttemptId") != attempt_id:
        return False
    attempt = ports.find_attempt(task, attempt_id)
    return bool(
        attempt
        and attempt.get("status") == "awaiting_user_decision"
        and attempt.get("humanDecisionId")
    )


def run_attempt(project_id: str, task_id: str, attempt_id: str, cancel_flag: threading.Event, *, ports: RunnerPorts) -> None:
    notification_key: str | None = None
    reconcile_reason: str | None = None
    try:
        if not _claim_attempt_runner(project_id, task_id, attempt_id, ports):
            return
        invocation = invoke_provider_with_checklist_planning(
            project_id, task_id, attempt_id,
            repository=ports.repository,
            monotonic=time.time,
            ports=ports,
        )
        if invocation is None:
            return
        workspace = invocation.workspace
        executor = invocation.executor
        started = invocation.started_at
        result = invocation.result
        if _attempt_waiting_for_human_decision(project_id, task_id, attempt_id, ports):
            return
        final_snapshot = ports.git_snapshot(workspace)
        data, project, task = ports.find(project_id, task_id)
        if not project or not task:
            return
        attempt = ports.find_attempt(task, attempt_id)
        if not attempt or (
            not attempt_is_committable(task, attempt_id)
            and attempt.get("status") not in {"cancelling", "cancelled"}
        ):
            return
        stage_pipeline = (
            ports.is_stage_pipeline(project)
            and orchestration_state(project).get("state") != "draft"
        )
        commit_baseline = copy.deepcopy(project)
        checklist_changed = ports.apply_checklist_updates(task, result)
        discussion_points_changed = ports.apply_meeting_discussion_points(task, result)
        cancelled = cancel_flag.is_set() or result.get("status") == "cancelled"
        evidence = {
            "attemptId": attempt_id,
            "executorSummary": ports.redact(result.get("reply") or ""),
            "changedFiles": sorted(set(final_snapshot.get("files", [])) | set(result.get("modifiedFiles") or []))[:200],
            "workspaceBefore": attempt.get("baseline", {}), "workspaceAfter": final_snapshot,
            "checklist": ports.acceptance_checklist(task),
            "providerStatus": result.get("status") or ("completed" if result.get("ok") else "execution_failed"),
            "error": ports.redact(result.get("error") or ""), "durationMs": int((time.time() - started) * 1000), "capturedAt": ports.now(),
            "testResults": ports.test_evidence(result),
            "checklistUpdated": checklist_changed,
            "meetingDiscussionUpdated": discussion_points_changed,
            "providerRef": {"providerKind": executor.get("providerKind"), "agentId": executor.get("id"), "attemptId": attempt_id},
        }
        if cancelled:
            ports.finalize_cancel(project_id, task_id, attempt_id, evidence)
            ports.cancel_registry.discard(attempt_id)
            return
        attempt.update({"evidence": evidence, "finishedAt": ports.now()})
        task.update({"evidence": evidence, "activeAttemptId": None})
        project.update({"workflowActive": False, "activeTaskId": None, "activeAgent": None})
        if result.get("ok"):
            attempt["status"] = "execution_complete"
            task.update({"blockedReason": None, "lastError": None})
            if attempt.get("meetingActionPhase"):
                ports.mark_meeting_actions_completed(project, task, attempt_id, executor.get("id") or "executor")
                attempt["status"] = "meeting_action_items_completed"
                task["reviewResult"] = {}
                task["evidence"] = evidence
                ports.transition(project, task, "backlog", executor.get("id") or "executor", "Meeting action items completed; original task can resume.", attempt_id)
                ports.move_task_to_column(project, task, ports.backlog_column(project))
                project_update = {
                    "workflowActive": False,
                    "workflowPhase": "meeting_action_items_completed",
                    "activeTaskId": None,
                    "activeAgent": None,
                    "updatedAt": ports.now(),
                }
                if not stage_pipeline:
                    project_update.update({
                        "projectExecutionFlowActive": project.get("projectExecutionStartMode") == "continuous",
                        "projectExecutionFlowStopReason": None,
                    })
                project.update(project_update)
                if not ports.commit_projects(project_id, task_id, attempt_id, data, commit_baseline):
                    return
                ports.cancel_registry.discard(attempt_id)
                if stage_pipeline:
                    ports.reconcile_terminal(project_id, task_id, attempt_id, "meeting_action_items_completed")
                elif not ports.has_pending_meeting_actions(task):
                    ports.launcher(lambda: ports.start_task(project_id, task_id, {"projectStart": True, "mode": project.get("projectExecutionStartMode") or "continuous", "autoReviewAfterExecution": True, "by": "meeting-action-items"}))
                return
            if attempt.get("skipReview"):
                task["reviewResult"] = {
                    "id": f"skipped-{attempt_id}",
                    "attemptId": attempt_id,
                    "status": "skipped",
                    "summary": "Independent review skipped after user confirmation because no reviewer was configured.",
                    "rationale": attempt.get("skipReviewReason") or "reviewer_missing",
                    "items": [],
                    "reviewedAt": ports.now(),
                }
                task.setdefault("reviewHistory", []).append(task["reviewResult"])
                task["reviewHistory"] = task["reviewHistory"][-50:]
                if ports.attempt_requires_acceptance(task, attempt):
                    attempt["status"] = "review_skipped_waiting_acceptance"
                    if not stage_pipeline:
                        project["projectExecutionFlowActive"] = False
                        project["projectExecutionFlowStopReason"] = "awaiting_user_acceptance"
                    ports.transition(project, task, "awaiting_user_acceptance", "system", "Review skipped by user confirmation; waiting for user acceptance.", attempt_id)
                    notification_key = ports.stage_acceptance(
                        project, task, attempt_id,
                        "Review skipped by user confirmation; waiting for user acceptance.",
                    )
                    if stage_pipeline:
                        reconcile_reason = "awaiting_user_acceptance"
                else:
                    done_result = ports.mark_done(project, task, "system", "Review skipped by user confirmation; task does not require user acceptance.", attempt_id)
                    if not done_result.get("ok"):
                        continued = ports.continue_incomplete_checklist(data, project_id, task_id, project, task, attempt_id, "system", done_result)
                        if continued.get("continued"):
                            ports.cancel_registry.discard(attempt_id)
                            return
                        task["blockedReason"] = done_result.get("error")
                        ports.transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                        ports.notify_intervention(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
                    elif stage_pipeline:
                        reconcile_reason = "review_skipped"
                    elif attempt.get("projectFlow") or project.get("projectExecutionFlowActive"):
                        project["projectExecutionFlowActive"] = True
                        project["projectExecutionFlowStopReason"] = None
                        ports.schedule_continue(project_id, "review_skipped")
            else:
                ports.transition(project, task, "execution_complete", executor.get("id") or "executor", "Execution completed; Independent review has not started.", attempt_id)
                if stage_pipeline:
                    reconcile_reason = "execution_complete"
        else:
            transient_reason = ports.transient_failure_reason(result)
            if transient_reason and ports.schedule_transient_retry(data, project_id, task_id, project, task, attempt, evidence, transient_reason, commit_baseline):
                ports.cancel_registry.discard(attempt_id)
                return
            attempt["status"] = "blocked"
            task["lastError"] = evidence["error"] or "Executor failed"
            task["blockedReason"] = task["lastError"]
            ports.transition(project, task, "blocked", executor.get("id") or "executor", task["blockedReason"], attempt_id)
            ports.notify_intervention(project, task, task["blockedReason"], attempt_id, event="blocked", kind="error")
        project["workflowPhase"] = task["executionState"]
        if not ports.commit_projects(project_id, task_id, attempt_id, data, commit_baseline):
            return
        ports.cancel_registry.discard(attempt_id)
        if notification_key:
            ports.deliver_notification(project_id, task_id, attempt_id, notification_key)
        if reconcile_reason:
            ports.reconcile_terminal(project_id, task_id, attempt_id, reconcile_reason)
        if result.get("ok") and attempt.get("autoReviewAfterExecution"):
            ports.start_review(project_id, task_id, {"attemptId": attempt_id})
    finally:
        ports.cancel_registry.discard(attempt_id)

def start_task(
    project_id: str,
    task_id: str,
    body: dict[str, Any] | None,
    *,
    repository: Repository,
    cancel_registry: CancelRegistry,
    ports: StartPorts,
) -> dict[str, Any]:
    """Validate slow prerequisites, atomically persist an attempt, then launch it."""
    body = body or {}
    try:
        snapshot_project = repository.get(project_id)
    except ProjectNotFoundError:
        return _status({"error": "Project or task not found"}, 404)
    if snapshot_project is None:
        return _status({"error": "Project or task not found"}, 404)
    snapshot_task = _find_task(snapshot_project, task_id)
    if snapshot_task is None:
        return _status({"error": "Project or task not found"}, 404)
    if not snapshot_project.get("projectExecutionEnabled"):
        return _status({"error": "Project Execution is not enabled for this project"}, 409)
    active = ports.active_task(snapshot_project)
    if active:
        return _status({"error": "Another task is already active for this project", "activeTaskId": active.get("id")}, 409)
    prior_task = prior_incomplete_task(snapshot_project, task_id)
    if prior_task is not None:
        return _status(
            {
                "ok": False,
                "error": "A lower-order task must be completed before this task can start",
                "code": "project_execution_order_blocked",
                "taskId": task_id,
                "priorTaskId": prior_task.get("id"),
                "priorTaskTitle": prior_task.get("title", ""),
            },
            409,
        )

    workspace_path = snapshot_project.get("workspacePath")
    allow_workspace_optional = (
        str(body.get("source") or "") == "agent_project_execution"
        and not str(workspace_path or "").strip()
    )
    workspace = (
        {"ok": True, "path": "", "kind": "none", "virtual": True}
        if allow_workspace_optional
        else ports.validate_workspace(workspace_path)
    )
    if not workspace.get("ok"):
        repository.update(project_id, lambda project: project.update({"workspaceStatus": copy.deepcopy(workspace)}))
        result = _status(workspace, 409)
        _notify_start_failure(repository, project_id, task_id, result, ports.notify_intervention)
        return result

    roles = ports.resolve_roles(
        snapshot_project,
        snapshot_task,
        snapshot_task.get("allowReviewerlessExecution") is True,
    )
    if not roles.get("ok"):
        payload = dict(roles)
        if roles.get("confirmationRequired"):
            payload.update(
                {
                    "taskId": task_id,
                    "startMode": ports.start_mode(snapshot_project, body) if body.get("projectStart") else "single",
                    "requiresUserAcceptance": ports.requires_acceptance(snapshot_task),
                }
            )
        result = _status(payload, 409)
        _notify_start_failure(repository, project_id, task_id, result, ports.notify_intervention)
        return result

    git_state = (
        {"ok": True, "dirty": False, "files": [], "fingerprint": "", "truncated": False, "virtual": True}
        if workspace.get("virtual")
        else ports.git_snapshot(workspace["path"])
    )
    if git_state.get("error"):
        result = _status(
            {
                "ok": False,
                "error": "Unable to verify the Git workspace state",
                "code": "workspace_git_snapshot_failed",
            },
            409,
        )
        _notify_start_failure(repository, project_id, task_id, result, ports.notify_intervention)
        return result

    start_mode = ports.start_mode(snapshot_project, body) if body.get("projectStart") else "single"
    if git_state.get("dirty") and str(body.get("dirtyFingerprint") or "") != git_state.get("fingerprint"):
        return _status(
            {
                "ok": False,
                "confirmationRequired": True,
                "code": "dirty_worktree_confirmation_required",
                "taskId": task_id,
                "startMode": start_mode,
                "requiresUserAcceptance": ports.requires_acceptance(snapshot_task),
                "dirtyFingerprint": git_state.get("fingerprint"),
                "dirtyFiles": git_state.get("files", [])[:50],
                "truncated": git_state.get("truncated", False),
            },
            409,
        )

    attempt_id = ports.new_id()

    def prepare(project: Project) -> dict[str, Any]:
        task = _find_task(project, task_id)
        if task is None:
            return _status({"error": "Project or task not found"}, 404)
        if not project.get("projectExecutionEnabled"):
            return _status({"error": "Project Execution is not enabled for this project"}, 409)
        active = ports.active_task(project)
        if active:
            return _status({"error": "Another task is already active for this project", "activeTaskId": active.get("id")}, 409)
        prior_task = prior_incomplete_task(project, task_id)
        if prior_task is not None:
            return _status(
                {
                    "ok": False,
                    "error": "A lower-order task must be completed before this task can start",
                    "code": "project_execution_order_blocked",
                    "taskId": task_id,
                    "priorTaskId": prior_task.get("id"),
                    "priorTaskTitle": prior_task.get("title", ""),
                },
                409,
            )
        if project.get("workspacePath") != workspace_path:
            return _status({"error": "Project workspace changed while execution was being prepared", "code": "workspace_changed"}, 409)
        reopened = False
        if task.get("completedAt"):
            if task.get("scheduledRepeatEnabled") is not True:
                return _status(
                    {
                        "ok": False,
                        "error": "Task is completed and repeat triggering is not enabled",
                        "code": "task_completed_repeat_disabled",
                        "taskId": task_id,
                    },
                    409,
                )
            reopened = ports.reopen_completed_task(project, task, actor=str(body.get("by") or "user"))
        state = task.get("executionState") or ("done" if task.get("completedAt") else "backlog")
        normalized_state = str(state or "").strip().lower()
        if normalized_state not in {"", "backlog", "blocked"}:
            payload = {
                "ok": False,
                "error": "Task is not startable in its current execution state",
                "code": "task_not_startable",
                "taskId": task_id,
                "executionState": state,
            }
            if normalized_state in {"validating", "executing", "reviewing", "reworking", "awaiting_meeting_resolution"}:
                payload["activeTaskId"] = task_id
            return _status(payload, 409)
        if body.get("resetExecutionContext") is True:
            ports.clear_restart_bindings(task, ports.now(), str(body.get("by") or "user"), "manual task restart")
            ports.seed_checklist(task, "project_execution_seed")
            task["_suppressExecutorChecklistCreateOnce"] = True
        if str(task.get("executionState") or "").lower() == "blocked":
            task["reworkCount"] = 0
        if git_state.get("dirty"):
            project.setdefault("executionDirtyConfirmations", []).append(git_state.get("fingerprint"))
            project["executionDirtyConfirmations"] = project["executionDirtyConfirmations"][-100:]
        project_flow = bool(body.get("projectStart")) and start_mode == "continuous"
        meeting_phase = ports.has_pending_meeting_actions(task)
        attempt = {
            "id": attempt_id,
            "status": "meeting_action_items" if meeting_phase else "executing",
            "startedAt": ports.now(),
            "workspacePath": workspace["path"],
            "workspaceKind": workspace["kind"],
            "dirtyConfirmed": bool(git_state.get("dirty")),
            "dirtyFingerprint": git_state.get("fingerprint") if git_state.get("dirty") else "",
            "executor": roles["executor"],
            "reviewer": roles.get("reviewer"),
            "skipReview": bool(roles.get("skipReview")),
            "skipReviewReason": roles.get("skipReviewReason"),
            "baseline": git_state,
            "startMode": start_mode,
            "projectFlow": project_flow,
            "requiresUserAcceptance": ports.requires_acceptance(task),
            "autoReviewAfterExecution": bool(body.get("autoReviewAfterExecution")) and not roles.get("skipReview"),
            "meetingActionPhase": meeting_phase,
        }
        task.setdefault("attempts", []).append(attempt)
        task["attempts"] = task["attempts"][-20:]
        if not task.get("assignee"):
            task["assignee"] = roles["executor"]["id"]
        task.update(
            {
                "activeAttemptId": attempt_id,
                "executorAgentId": roles["executor"]["id"],
                "reviewerAgentId": (roles.get("reviewer") or {}).get("id"),
                "blockedReason": None,
                "lastError": None,
            }
        )
        project.update(
            {
                "projectExecutionStartMode": start_mode if body.get("projectStart") else project.get("projectExecutionStartMode", "continuous"),
                "projectExecutionFlowActive": project_flow,
                "projectExecutionFlowStopReason": None,
                "workspaceStatus": workspace,
                "workflowActive": True,
                "workflowPhase": "executing",
                "activeTaskId": task_id,
                "activeAgent": roles["executor"]["id"],
            }
        )
        reason = "Meeting action item phase started" if meeting_phase else "Project Execution task started"
        ports.transition(project, task, "executing", "user", reason, attempt_id)
        return {
            "ok": True,
            "status": "started",
            "taskId": task_id,
            "attemptId": attempt_id,
            "startMode": start_mode,
            "requiresUserAcceptance": ports.requires_acceptance(task),
            "reopenedCompletedTask": reopened,
        }

    update_from_snapshot = getattr(repository, "update_from_snapshot", None)
    if callable(update_from_snapshot):
        result = update_from_snapshot(project_id, snapshot_project, prepare)
    else:
        result = repository.update(project_id, prepare)
    if not result.get("ok"):
        return result
    cancel_flag = cancel_registry.create(attempt_id)
    ports.launcher(lambda: ports.runner(project_id, task_id, attempt_id, cancel_flag))
    return result


def start_project(
    project_id: str,
    body: dict[str, Any] | None,
    *,
    repository: Repository,
    active_task: Callable[[Project], Task | None],
    all_tasks_repeatable: Callable[[Project], bool],
    reset_tasks: Callable[..., dict[str, Any]],
    next_task: Callable[[Project], Task | None],
    start_mode: Callable[[Project, dict[str, Any]], str],
    start_task_command: Callable[[str, str, dict[str, Any]], dict[str, Any]],
    notify_complete: Callable[[Project, str], Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    """Select and start the next eligible task with atomic project-flow state."""
    body = body or {}
    try:
        project = repository.get(project_id)
    except ProjectNotFoundError:
        return _status({"error": "Project not found"}, 404)
    if project is None:
        return _status({"error": "Project not found"}, 404)
    if not project.get("projectExecutionEnabled"):
        return _status({"error": "Project Execution is not enabled for this project"}, 409)
    active = active_task(project)
    if active:
        return _status({"error": "Another task is already active for this project", "activeTaskId": active.get("id")}, 409)

    restart_pipeline = body.get("restartPipeline") is True
    reset_result: dict[str, Any] | None = None
    if restart_pipeline:
        if not all_tasks_repeatable(project):
            return _status(
                {
                    "ok": False,
                    "error": "Project pipeline can only be restarted when every task allows retriggering",
                    "code": "project_restart_requires_all_tasks_repeatable",
                },
                409,
            )

        def reset(latest: Project) -> dict[str, Any]:
            if active_task(latest):
                return _status({"error": "Another task is already active for this project", "activeTaskId": active_task(latest).get("id")}, 409)
            return reset_tasks(latest, actor=str(body.get("by") or "user"))

        try:
            reset_result = repository.update(project_id, reset)
        except ProjectNotFoundError:
            return _status({"error": "Project not found"}, 404)
        if not reset_result.get("ok"):
            return reset_result
        project = repository.get(project_id)

    selected = next_task(project)
    if selected is None:
        def stop_empty(latest: Project) -> Project:
            latest["projectExecutionFlowActive"] = False
            latest["projectExecutionFlowStopReason"] = "no_eligible_task"
            latest["workflowActive"] = False
            latest["workflowPhase"] = "no_eligible_task"
            latest["updatedAt"] = now()
            return copy.deepcopy(latest)
        try:
            completed = repository.update(project_id, stop_empty)
        except ProjectNotFoundError:
            return _status({"error": "Project not found"}, 404)
        notify_complete(completed, "Project Execution 已完成，当前没有可继续执行的任务。")
        notification_markers = copy.deepcopy(completed.get("feishuNotifications") or {})
        if notification_markers:
            try:
                repository.update(
                    project_id,
                    lambda latest: latest.update({"feishuNotifications": notification_markers}),
                )
            except ProjectNotFoundError:
                pass
        return _status({"error": "No eligible task to start", "code": "no_eligible_task"}, 409)

    mode = start_mode(project, body)
    result = start_task_command(
        project_id,
        selected.get("id"),
        {**body, "mode": mode, "projectStart": True, "autoReviewAfterExecution": True},
    )
    if restart_pipeline:
        result["restartPipeline"] = True
        result["resetTaskCount"] = (reset_result or {}).get("resetTaskCount", 0)
    if result.get("ok") or result.get("confirmationRequired"):
        result["selectedTask"] = {"id": selected.get("id"), "title": selected.get("title", "")}
    if result.get("confirmationRequired") or (not result.get("ok") and result.get("error")):
        def record_failure(latest: Project) -> None:
            latest["projectExecutionStartMode"] = mode
            latest["projectExecutionFlowActive"] = False
            latest["projectExecutionFlowStopReason"] = result.get("code") or result.get("error")
            latest["workflowActive"] = False
            latest["workflowPhase"] = result.get("code") or "start_failed"
            latest["updatedAt"] = now()
        try:
            repository.update(project_id, record_failure)
        except ProjectNotFoundError:
            return _status({"error": "Project not found"}, 404)
        result["selectedTask"] = {"id": selected.get("id"), "title": selected.get("title", "")}
    return result


def status(
    project_id: str,
    task_id: str | None,
    *,
    repository: Repository,
    is_live: Callable[[str], bool],
    transition_task: Callable[[Project, Task, str, str, str, str | None], Any],
) -> dict[str, Any]:
    try:
        project = repository.get(project_id)
    except ProjectNotFoundError:
        return _status({"error": "Project or task not found"}, 404)
    if project is None:
        return _status({"error": "Project or task not found"}, 404)
    task = _find_task(project, task_id) if task_id else None
    if task_id and task is None:
        return _status({"error": "Project or task not found"}, 404)
    if is_marked_project(project):
        return _stage_pipeline_status(project, task)
    targets = [task] if task else project.get("tasks", [])
    stale = [item.get("id") for item in targets if item and item.get("executionState") in STALE_RECONCILE_STATES and not is_live(str(item.get("activeAttemptId") or ""))]
    if stale:
        def reconcile(latest: Project) -> None:
            for item_id in stale:
                item = _find_task(latest, item_id)
                if not item or item.get("executionState") not in STALE_RECONCILE_STATES:
                    continue
                attempt_id = item.get("activeAttemptId")
                if is_live(str(attempt_id or "")):
                    continue
                item["activeAttemptId"] = None
                item["blockedReason"] = "previous_execution_not_resumable"
                transition_task(latest, item, "blocked", "system", item["blockedReason"], attempt_id)
            latest.update({
                "workflowActive": False,
                "activeTaskId": None,
                "activeAgent": None,
                "workflowPhase": "blocked",
                "projectExecutionFlowActive": False,
                "projectExecutionFlowStopReason": "previous_execution_not_resumable",
            })
        repository.update(project_id, reconcile)
        project = repository.get(project_id)
        task = _find_task(project, task_id) if task_id else None
    return {
        "ok": True,
        "active": bool(project.get("workflowActive")),
        "phase": project.get("workflowPhase") or "idle",
        "currentTaskId": project.get("activeTaskId"),
        "startMode": project.get("projectExecutionStartMode") or "continuous",
        "flowActive": bool(project.get("projectExecutionFlowActive")),
        "flowStopReason": project.get("projectExecutionFlowStopReason"),
        "task": task,
    }


def cancel(
    project_id: str,
    task_id: str,
    body: dict[str, Any] | None,
    *,
    repository: Repository,
    cancel_registry: CancelRegistry,
    transition_task: Callable[[Project, Task, str, str, str, str | None], Any],
    now: Callable[[], str],
    cancel_provider: Callable[[dict[str, Any], str, str, str], Any],
    notify_intervention: Callable[..., Any],
) -> dict[str, Any]:
    requested_id = str((body or {}).get("attemptId") or "")

    def prepare(project: Project) -> dict[str, Any]:
        task = _find_task(project, task_id)
        if task is None:
            return _status({"error": "Task not found"}, 404)
        attempt_id = requested_id or str(task.get("activeAttemptId") or "")
        if not attempt_id or task.get("activeAttemptId") != attempt_id:
            return _status({"error": "No matching active attempt"}, 409)
        attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), {})
        attempt["status"] = "cancelled"
        task["activeAttemptId"] = None
        task["blockedReason"] = "Execution was stopped by user. Existing workspace changes were not rolled back."
        task["lastError"] = None
        transition_task(project, task, "blocked", "user", task["blockedReason"], attempt_id)
        project.update(
            {
                "workflowActive": False,
                "workflowPhase": "blocked",
                "activeTaskId": None,
                "activeAgent": None,
                "projectExecutionFlowActive": False,
                "projectExecutionFlowStopReason": "user_stopped_execution",
                "updatedAt": now(),
            }
        )
        return {"ok": True, "status": "blocked", "attemptId": attempt_id, "task": copy.deepcopy(task), "attempt": copy.deepcopy(attempt)}

    try:
        result = repository.update(project_id, prepare)
    except ProjectNotFoundError:
        return _status({"error": "Task not found"}, 404)
    if not result.get("ok"):
        return result
    cancel_registry.cancel(result["attemptId"])
    committed_attempt = result.pop("attempt")
    cancel_provider(committed_attempt, project_id, task_id, result["attemptId"])
    try:
        project = repository.get(project_id)
        task = _find_task(project, task_id) if project else None
        if task is not None:
            notify_intervention(
                project, task, task.get("blockedReason"), result["attemptId"],
                event="blocked", kind="warning",
            )
            notified_attempt = next(
                (item for item in task.get("attempts", []) if item.get("id") == result["attemptId"]),
                None,
            )
            markers = copy.deepcopy((notified_attempt or {}).get("feishuNotifications") or {})
            if markers:
                def persist_markers(latest: Project) -> None:
                    latest_task = _find_task(latest, task_id)
                    latest_attempt = next(
                        (item for item in (latest_task or {}).get("attempts", []) if item.get("id") == result["attemptId"]),
                        None,
                    )
                    if latest_attempt is not None:
                        latest_attempt["feishuNotifications"] = markers
                repository.update(project_id, persist_markers)
    except (ProjectNotFoundError, RuntimeError):
        pass
    return result
