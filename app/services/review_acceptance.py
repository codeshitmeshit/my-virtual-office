"""Review, rework, acceptance, and notification domain helpers.

The module deliberately contains no HTTP or ``server.py`` dependencies.  Entry
adapters create a trusted :class:`EntryContext`; caller supplied ``actor`` fields
are never treated as authority.  Notification intents are persisted as local
state before an adapter attempts best-effort external delivery.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from services.project_repository import ProjectNotFoundError


Project = dict[str, Any]
Task = dict[str, Any]


class Repository(Protocol):
    def get(self, project_id: str) -> Project: ...
    def update(self, project_id: str, mutator: Callable[[Project], Any]) -> Any: ...


class CommandError(RuntimeError):
    def __init__(self, message: str, status: int, **payload: Any) -> None:
        super().__init__(message)
        self.payload = {"error": message, "_status": status, **payload}


def _find_task(project: Project, task_id: str) -> Task | None:
    return next((task for task in project.get("tasks", []) if task.get("id") == task_id), None)


def _error(exc: CommandError) -> dict[str, Any]:
    return copy.deepcopy(exc.payload)


@dataclass(frozen=True)
class EntryContext:
    """Identity established by a trusted transport adapter."""

    source: str
    actor: str
    trusted: bool = True

    @classmethod
    def http(cls) -> "EntryContext":
        return cls(source="http", actor="user")

    @classmethod
    def feishu(cls, actor: str) -> "EntryContext":
        return cls(source="feishu", actor=str(actor or "feishu-user"))

    @classmethod
    def system(cls, actor: str = "system") -> "EntryContext":
        return cls(source="system", actor=str(actor or "system"))


@dataclass(frozen=True)
class ReviewStartPorts:
    enabled: Callable[[Project], bool]
    latest_attempt: Callable[[Task], dict[str, Any] | None]
    resolve_roles: Callable[[Project, Task], dict[str, Any]]
    active_task: Callable[[Project], Task | None]
    transition: Callable[..., Any]
    now: Callable[[], str]
    new_id: Callable[[], str]
    register_review: Callable[[str], Any]
    launcher: Callable[[Callable[[], None]], Any]
    runner: Callable[[str, str, str, str], Any]


def start_review(
    project_id: str,
    task_id: str,
    body: Mapping[str, Any] | None,
    *,
    context: EntryContext,
    repository: Repository,
    ports: ReviewStartPorts,
) -> dict[str, Any]:
    """Atomically persist reviewer handoff before launching background work."""
    if not context.trusted:
        return {"error": "Untrusted review entry context", "_status": 403}
    review_id = ports.new_id()
    prepared: dict[str, Any] = {}

    def prepare(project: Project) -> None:
        task = _find_task(project, task_id)
        if task is None:
            raise CommandError("Project or task not found", 404)
        if not ports.enabled(project):
            raise CommandError("Project Execution is not enabled for this project", 409)
        if task.get("executionState") != "execution_complete":
            raise CommandError("Task must be execution_complete before reviewer handoff", 409)
        attempt = ports.latest_attempt(task)
        if not attempt or not (attempt.get("evidence") or task.get("evidence")):
            raise CommandError("Execution evidence is required before review", 409)
        requested_attempt = str((body or {}).get("attemptId") or attempt.get("id"))
        if requested_attempt != attempt.get("id"):
            raise CommandError("Stale or mismatched attempt cannot be reviewed", 409)
        roles = ports.resolve_roles(project, task)
        if not roles.get("ok"):
            raise CommandError(str(roles.get("error") or "Reviewer is unavailable"), 409, **{
                key: value for key, value in roles.items() if key not in {"ok", "error", "_status"}
            })
        active = ports.active_task(project)
        if active:
            raise CommandError("Another task is already active for this project", 409, activeTaskId=active.get("id"))
        reviewer = copy.deepcopy(roles["reviewer"])
        attempt["reviewer"] = reviewer
        attempt["reviewStartedAt"] = ports.now()
        task.update({
            "activeAttemptId": review_id,
            "reviewerAgentId": reviewer["id"],
            "reviewResult": {},
            "blockedReason": None,
            "lastError": None,
        })
        project.update({
            "workflowActive": True,
            "workflowPhase": "reviewing",
            "activeTaskId": task_id,
            "activeAgent": reviewer["id"],
        })
        ports.transition(
            project, task, "reviewing", context.actor,
            "Independent reviewer handoff started", attempt.get("id"),
        )
        prepared.update({"attemptId": attempt.get("id"), "reviewId": review_id})

    try:
        repository.update(project_id, prepare)
    except ProjectNotFoundError:
        return {"error": "Project or task not found", "_status": 404}
    except CommandError as exc:
        return _error(exc)
    ports.register_review(review_id)
    ports.launcher(lambda: ports.runner(project_id, task_id, prepared["attemptId"], review_id))
    return {
        "ok": True, "status": "reviewing", "taskId": task_id,
        "attemptId": prepared["attemptId"], "reviewId": review_id,
    }


@dataclass(frozen=True)
class AcceptancePorts:
    enabled: Callable[[Project], bool]
    validate_workspace: Callable[[str], dict[str, Any]]
    active_task: Callable[[Project], Task | None]
    resolve_roles: Callable[[Project, Task, bool], dict[str, Any]]
    automatic_snapshot: Callable[[Project, str], dict[str, Any]]
    requires_acceptance: Callable[[Task], bool]
    mark_done: Callable[..., dict[str, Any]]
    transition: Callable[..., Any]
    log_activity: Callable[..., Any]
    redact: Callable[[Any], str]
    now: Callable[[], str]
    new_id: Callable[[], str]
    create_cancel_flag: Callable[[str], Any]
    launcher: Callable[[Callable[[], None]], Any]
    runner: Callable[[str, str, str, Any], Any]
    schedule_continue: Callable[[str, str], Any]
    notify_intervention: Callable[..., Any]


@dataclass(frozen=True)
class ReviewRunnerPorts:
    find: Callable[..., tuple[dict[str, Any], Project | None, Task | None]]
    find_attempt: Callable[[Task, str], dict[str, Any] | None]
    build_prompt: Callable[[Project, Task, dict[str, Any]], str]
    call_reviewer: Callable[..., dict[str, Any]]
    normalize: Callable[..., dict[str, Any]]
    commit: Callable[[str, str, str, str, dict[str, Any], Project], bool]
    attempt_requires_acceptance: Callable[[Task, dict[str, Any]], bool]
    transition: Callable[..., Any]
    stage_acceptance: Callable[..., str]
    deliver_notification: Callable[[str, str, str, str], Any]
    mark_done: Callable[..., dict[str, Any]]
    prepare_incomplete_checklist: Callable[..., dict[str, Any]]
    schedule_continue: Callable[[str, str], Any]
    review_feedback: Callable[[dict[str, Any]], str]
    resolve_roles: Callable[[Project, Task], dict[str, Any]]
    validate_workspace: Callable[[str], dict[str, Any]]
    automatic_snapshot: Callable[[Project, str], dict[str, Any]]
    deliver_intervention: Callable[[str, str, Any, str | None, str, str], Any]
    now: Callable[[], str]
    new_id: Callable[[], str]
    launch_rework: Callable[[str, str, str], Any]
    discard_review: Callable[[str], Any]


def run_review(
    project_id: str,
    task_id: str,
    attempt_id: str,
    review_id: str,
    *,
    ports: ReviewRunnerPorts,
) -> None:
    """Invoke an independent reviewer, then compare-and-commit its state machine."""
    notification_key: str | None = None
    rework_launch: str | None = None
    continue_reason: str | None = None
    interventions: list[tuple[Any, str | None, str, str]] = []
    try:
        _data, project, task = ports.find(project_id, task_id)
        if not project or not task:
            return
        attempt = ports.find_attempt(task, attempt_id)
        if not attempt or task.get("activeAttemptId") != review_id:
            return
        reviewer = copy.deepcopy(attempt.get("reviewer") or {})
        result = ports.call_reviewer(
            reviewer, ports.build_prompt(project, task, attempt), review_id,
            project_id=project_id, task_id=task_id,
        )
        data, project, task = ports.find(project_id, task_id)
        if not project or not task:
            return
        attempt = ports.find_attempt(task, attempt_id)
        if not attempt or task.get("activeAttemptId") != review_id:
            return
        commit_baseline = copy.deepcopy(project)
        review = ports.normalize(result, reviewer, attempt_id, review_id)
        attempt["review"] = review
        attempt["reviewedAt"] = review["reviewedAt"]
        task.setdefault("reviewHistory", []).append(review)
        task["reviewHistory"] = task["reviewHistory"][-50:]
        task["reviewResult"] = review
        task["activeAttemptId"] = None
        project.update({"workflowActive": False, "activeTaskId": None, "activeAgent": None})
        if review["status"] == "pass":
            task.update({"blockedReason": None, "lastError": None})
            attempt["status"] = "review_passed"
            if ports.attempt_requires_acceptance(task, attempt):
                project["projectExecutionFlowActive"] = False
                project["projectExecutionFlowStopReason"] = "awaiting_user_acceptance"
                ports.transition(
                    project, task, "awaiting_user_acceptance", reviewer.get("id") or "reviewer",
                    "Reviewer passed; waiting for explicit user acceptance.", attempt_id,
                )
                notification_key = ports.stage_acceptance(
                    project, task, attempt_id,
                    "Reviewer passed; waiting for explicit user acceptance.",
                )
            else:
                done_result = ports.mark_done(
                    project, task, reviewer.get("id") or "reviewer",
                    "Reviewer passed; task does not require user acceptance.", attempt_id,
                )
                if not done_result.get("ok"):
                    continued = ports.prepare_incomplete_checklist(
                        project, task, attempt_id, reviewer.get("id") or "reviewer", done_result,
                    )
                    if continued.get("continued"):
                        rework_launch = str(continued.get("attemptId") or "")
                    else:
                        task["blockedReason"] = task.get("blockedReason") or done_result.get("error")
                        if task.get("executionState") != "blocked":
                            ports.transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                        interventions.append((task["blockedReason"], attempt_id, "blocked", "warning"))
                elif attempt.get("projectFlow") or project.get("projectExecutionFlowActive"):
                    project["projectExecutionFlowActive"] = True
                    project["projectExecutionFlowStopReason"] = None
                    continue_reason = "review_passed"
        elif review["status"] == "needs_more_work":
            attempt["status"] = "review_needs_more_work"
            prior_reworks = int(task.get("reworkCount") or 0)
            feedback = ports.review_feedback(review)
            if prior_reworks >= 3:
                task["blockedReason"] = "Reviewer still requested more work after three rework cycles."
                task["reworkFeedback"] = feedback
                ports.transition(
                    project, task, "blocked", reviewer.get("id") or "reviewer",
                    task["blockedReason"], attempt_id,
                )
                interventions.append((task["blockedReason"], attempt_id, "blocked", "warning"))
            else:
                task["reworkCount"] = prior_reworks + 1
                task.update({"blockedReason": None, "lastError": None, "reworkFeedback": feedback})
                roles = ports.resolve_roles(project, task)
                workspace = ports.validate_workspace(str(project.get("workspacePath") or ""))
                if not roles.get("ok") or not workspace.get("ok"):
                    task["blockedReason"] = roles.get("error") if not roles.get("ok") else workspace.get("error")
                    ports.transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                    interventions.append((task["blockedReason"], attempt_id, "blocked", "warning"))
                else:
                    automatic = ports.automatic_snapshot(project, workspace["path"])
                    if not automatic.get("ok"):
                        task["blockedReason"] = automatic.get("error")
                        task["lastError"] = automatic.get("code")
                        ports.transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                        interventions.append((task["blockedReason"], attempt_id, "blocked", "error"))
                        project["workflowPhase"] = "blocked"
                        if ports.commit(project_id, task_id, attempt_id, review_id, data, commit_baseline):
                            _deliver_review_interventions(
                                project_id, task_id, interventions, ports.deliver_intervention,
                            )
                        return
                    rework_attempt_id = ports.new_id()
                    rework_attempt = {
                        "id": rework_attempt_id, "status": "reworking", "startedAt": ports.now(),
                        "workspacePath": workspace["path"], "workspaceKind": workspace["kind"],
                        "dirtyConfirmed": False, "dirtyFingerprint": "",
                        "executor": copy.deepcopy(roles["executor"]),
                        "reviewer": copy.deepcopy(roles["reviewer"]),
                        "baseline": copy.deepcopy(automatic["snapshot"]), "rework": True,
                        "reworkCycle": task["reworkCount"], "reworkFromAttemptId": attempt_id,
                        "reworkFromReviewId": review_id, "reworkFeedback": feedback,
                        "autoReviewAfterExecution": True,
                    }
                    task.setdefault("attempts", []).append(rework_attempt)
                    task["attempts"] = task["attempts"][-20:]
                    task.update({
                        "activeAttemptId": rework_attempt_id,
                        "executorAgentId": roles["executor"]["id"],
                        "reviewerAgentId": roles["reviewer"]["id"],
                    })
                    project.update({
                        "workflowActive": True, "workflowPhase": "reworking",
                        "activeTaskId": task_id, "activeAgent": roles["executor"]["id"],
                    })
                    ports.transition(
                        project, task, "reworking", reviewer.get("id") or "reviewer",
                        feedback, rework_attempt_id,
                    )
                    rework_launch = rework_attempt_id
        else:
            attempt["status"] = "review_blocked"
            task["blockedReason"] = review["summary"] or "Reviewer marked the task blocked."
            ports.transition(
                project, task, "blocked", reviewer.get("id") or "reviewer",
                task["blockedReason"], attempt_id,
            )
            interventions.append((task["blockedReason"], attempt_id, "blocked", "warning"))
        project["workflowPhase"] = task["executionState"]
        if not ports.commit(project_id, task_id, attempt_id, review_id, data, commit_baseline):
            return
        _deliver_review_interventions(project_id, task_id, interventions, ports.deliver_intervention)
        if notification_key:
            ports.deliver_notification(project_id, task_id, attempt_id, notification_key)
        if continue_reason:
            ports.schedule_continue(project_id, continue_reason)
        if rework_launch:
            ports.launch_rework(project_id, task_id, rework_launch)
    finally:
        ports.discard_review(review_id)


def _deliver_review_interventions(
    project_id: str,
    task_id: str,
    interventions: list[tuple[Any, str | None, str, str]],
    deliver: Callable[[str, str, Any, str | None, str, str], Any],
) -> None:
    for reason, attempt_id, event, kind in interventions:
        try:
            deliver(project_id, task_id, reason, attempt_id, event, kind)
        except Exception:
            continue


def acceptance(
    project_id: str,
    task_id: str,
    body: Mapping[str, Any] | None,
    *,
    context: EntryContext,
    repository: Repository,
    ports: AcceptancePorts,
) -> dict[str, Any]:
    """Apply acceptance/rework using review+attempt compare tokens."""
    if not context.trusted:
        return {"error": "Untrusted acceptance entry context", "_status": 403}
    body = body or {}
    action = str(body.get("action") or "").strip()
    if action not in {"accept", "reject_and_rework", "mark_blocked"}:
        return {"error": "Invalid acceptance action", "_status": 400}
    attempt_id = str(body.get("attemptId") or "")
    feedback = str(body.get("feedback") or "").strip()
    if action != "accept" and not feedback:
        return {"error": "Feedback is required", "_status": 400}
    try:
        snapshot = repository.get(project_id)
    except ProjectNotFoundError:
        return {"error": "Project or task not found", "_status": 404}
    if not isinstance(snapshot, dict):
        return {"error": "Project or task not found", "_status": 404}
    task_snapshot = _find_task(snapshot, task_id)
    if task_snapshot is None:
        return {"error": "Project or task not found", "_status": 404}
    if not ports.enabled(snapshot):
        return {"error": "Project Execution is not enabled for this project", "_status": 409}
    review_snapshot = task_snapshot.get("reviewResult") if isinstance(task_snapshot.get("reviewResult"), dict) else {}
    review_attempt_id = str(review_snapshot.get("attemptId") or "")
    if task_snapshot.get("executionState") != "awaiting_user_acceptance" or review_snapshot.get("status") not in {"pass", "skipped"}:
        message = (
            "Reviewer pass or skipped review confirmation is required before user acceptance"
            if action == "accept" else
            "A current reviewer pass or skipped review result is required before this acceptance action"
        )
        return {"error": message, "_status": 409}
    if (action == "accept" and (not attempt_id or attempt_id != review_attempt_id)) or (
        action != "accept" and attempt_id and attempt_id != review_attempt_id
    ):
        return {"error": "Stale or mismatched acceptance attempt", "_status": 409}

    workspace = roles = automatic = None
    rework_config_basis = None
    if action == "reject_and_rework":
        workspace = ports.validate_workspace(str(snapshot.get("workspacePath") or ""))
        if not workspace.get("ok"):
            _persist_rework_preflight_failure(
                repository, project_id, task_id, review_attempt_id, workspace,
                context=context, ports=ports, workspace_status=workspace,
            )
            return {**workspace, "_status": 409}
        active = ports.active_task(snapshot)
        if active:
            return {"error": "Another task is already active for this project", "activeTaskId": active.get("id"), "_status": 409}
        roles = ports.resolve_roles(
            snapshot, task_snapshot,
            task_snapshot.get("allowReviewerlessExecution") is True or review_snapshot.get("status") == "skipped",
        )
        if not roles.get("ok"):
            return {**roles, "_status": 409}
        rework_config_basis = _rework_config_token(snapshot, task_snapshot)
        automatic = ports.automatic_snapshot(snapshot, workspace["path"])
        if not automatic.get("ok"):
            _persist_rework_preflight_failure(
                repository, project_id, task_id, review_attempt_id, automatic,
                context=context, ports=ports,
            )
            return {**automatic, "_status": 409}

    outcome: dict[str, Any] = {}
    rework_attempt_id = ports.new_id() if action == "reject_and_rework" else ""

    def commit(project: Project) -> None:
        task = _find_task(project, task_id)
        if task is None:
            raise CommandError("Project or task not found", 404)
        review = task.get("reviewResult") if isinstance(task.get("reviewResult"), dict) else {}
        if (
            task.get("executionState") != "awaiting_user_acceptance"
            or review.get("status") not in {"pass", "skipped"}
            or str(review.get("attemptId") or "") != review_attempt_id
        ):
            raise CommandError("Stale or mismatched acceptance attempt", 409)
        if action == "reject_and_rework":
            if str(project.get("workspacePath") or "") != str(snapshot.get("workspacePath") or ""):
                raise CommandError("Project workspace changed while preparing rework", 409)
            if _rework_config_token(project, task) != rework_config_basis:
                raise CommandError("Project execution roles changed while preparing rework", 409)
            active = ports.active_task(project)
            if active:
                raise CommandError(
                    "Another task is already active for this project", 409,
                    activeTaskId=active.get("id"),
                )
        if action == "accept":
            done_reason = "User accepted skipped review result" if review.get("status") == "skipped" else "User accepted reviewer pass"
            done_result = ports.mark_done(
                project, task, context.actor, done_reason, attempt_id,
                allow_empty_checklist=body.get("allowEmptyChecklist") is True,
            )
            if not done_result.get("ok"):
                raise CommandError(
                    str(done_result.get("error") or "Task cannot be accepted"),
                    int(done_result.get("_status") or 409),
                    **{key: value for key, value in done_result.items() if key not in {"ok", "error", "_status"}},
                )
            task.setdefault("acceptanceHistory", []).append({
                "action": "accept", "attemptId": attempt_id,
                "at": ports.now(), "by": context.actor, "source": context.source,
            })
            task["acceptanceHistory"] = task["acceptanceHistory"][-50:]
            should_continue = project.get("projectExecutionStartMode") == "continuous"
            project.update({
                "workflowActive": False, "workflowPhase": "done",
                "activeTaskId": None, "activeAgent": None, "updatedAt": ports.now(),
                "projectExecutionFlowActive": should_continue,
                "projectExecutionFlowStopReason": None if should_continue else "user_acceptance_completed",
            })
            ports.log_activity(
                project, "project_execution_user_accepted", context.actor,
                f"User accepted Project Execution task '{task.get('title', '')}'", task_id,
            )
            outcome.update({"ok": True, "status": "done", "task": copy.deepcopy(task), "flowContinues": should_continue})
            return
        safe_feedback = ports.redact(feedback)
        task.setdefault("acceptanceHistory", []).append({
            "action": action, "attemptId": review_attempt_id, "feedback": safe_feedback,
            "at": ports.now(), "by": context.actor, "source": context.source,
        })
        task["acceptanceHistory"] = task["acceptanceHistory"][-50:]
        task["reviewResult"] = {}
        task["reworkFeedback"] = safe_feedback
        if action == "mark_blocked":
            task["blockedReason"] = safe_feedback
            ports.transition(project, task, "blocked", context.actor, feedback, review_attempt_id)
            project.update({
                "workflowActive": False, "workflowPhase": "blocked",
                "activeTaskId": None, "activeAgent": None, "updatedAt": ports.now(),
            })
            outcome.update({"ok": True, "status": "blocked", "task": copy.deepcopy(task)})
            return
        task["reworkCount"] = int(task.get("reworkCount") or 0) + 1
        task["blockedReason"] = None
        rejected_source = "skipped review result" if review_snapshot.get("status") == "skipped" else "reviewer pass"
        rework_attempt = {
            "id": rework_attempt_id, "status": "reworking", "startedAt": ports.now(),
            "workspacePath": workspace["path"], "workspaceKind": workspace["kind"],
            "dirtyConfirmed": False, "dirtyFingerprint": "", "executor": copy.deepcopy(roles["executor"]),
            "reviewer": copy.deepcopy(roles.get("reviewer")), "skipReview": bool(roles.get("skipReview")),
            "skipReviewReason": roles.get("skipReviewReason"), "baseline": copy.deepcopy(automatic["snapshot"]),
            "startMode": "single", "projectFlow": False,
            "requiresUserAcceptance": ports.requires_acceptance(task), "rework": True,
            "reworkCycle": task["reworkCount"], "reworkFromAttemptId": review_attempt_id,
            "reworkFeedback": safe_feedback, "autoReviewAfterExecution": not roles.get("skipReview"),
        }
        task.setdefault("attempts", []).append(rework_attempt)
        task["attempts"] = task["attempts"][-20:]
        task.update({
            "activeAttemptId": rework_attempt_id, "executorAgentId": roles["executor"]["id"],
            "reviewerAgentId": (roles.get("reviewer") or {}).get("id"), "lastError": None,
        })
        project.update({
            "workspaceStatus": copy.deepcopy(workspace), "projectExecutionFlowActive": False,
            "projectExecutionFlowStopReason": None, "workflowActive": True,
            "workflowPhase": "reworking", "activeTaskId": task_id,
            "activeAgent": roles["executor"]["id"], "updatedAt": ports.now(),
        })
        ports.transition(
            project, task, "reworking", context.actor,
            f"User rejected {rejected_source}: {feedback}", rework_attempt_id,
        )
        outcome.update({"ok": True, "status": "reworking", "task": copy.deepcopy(task), "attemptId": rework_attempt_id})

    try:
        repository.update(project_id, commit)
    except ProjectNotFoundError:
        return {"error": "Project or task not found", "_status": 404}
    except CommandError as exc:
        return _error(exc)
    if action == "accept" and outcome.get("flowContinues"):
        ports.schedule_continue(project_id, "user_accepted")
    elif action == "reject_and_rework":
        cancel_flag = ports.create_cancel_flag(rework_attempt_id)
        ports.launcher(lambda: ports.runner(project_id, task_id, rework_attempt_id, cancel_flag))
    elif action == "mark_blocked":
        try:
            project = repository.get(project_id)
            task = _find_task(project, task_id)
            ports.notify_intervention(
                project, task, task.get("blockedReason"), review_attempt_id,
                event="blocked", kind="warning",
            )
        except (ProjectNotFoundError, RuntimeError):
            pass
    return outcome


def _rework_config_token(project: Project, task: Task) -> tuple[Any, ...]:
    return (
        project.get("workspacePath"), project.get("defaultExecutorAgentId"),
        project.get("defaultReviewerAgentId"), task.get("executorAgentId"),
        task.get("reviewerAgentId"), task.get("assignee"),
        task.get("allowReviewerlessExecution"),
    )


def _persist_rework_preflight_failure(
    repository: Repository,
    project_id: str,
    task_id: str,
    review_attempt_id: str,
    failure: Mapping[str, Any],
    *,
    context: EntryContext,
    ports: AcceptancePorts,
    workspace_status: Mapping[str, Any] | None = None,
) -> None:
    """Preserve legacy fail-closed state while keeping external delivery outside the lock."""
    reason = str(failure.get("error") or "Project workspace is not available for rework.")
    committed = {"value": False}

    def block(project: Project) -> None:
        task = _find_task(project, task_id)
        review = task.get("reviewResult") if isinstance((task or {}).get("reviewResult"), dict) else {}
        if (
            task is None
            or task.get("executionState") != "awaiting_user_acceptance"
            or str(review.get("attemptId") or "") != review_attempt_id
        ):
            return
        task["blockedReason"] = ports.redact(reason)
        task["lastError"] = failure.get("code")
        ports.transition(project, task, "blocked", "system", task["blockedReason"], review_attempt_id)
        project.update({
            "workflowActive": False, "workflowPhase": "blocked",
            "activeTaskId": None, "activeAgent": None, "updatedAt": ports.now(),
        })
        if workspace_status is not None:
            project["workspaceStatus"] = copy.deepcopy(dict(workspace_status))
        committed["value"] = True

    try:
        repository.update(project_id, block)
        if not committed["value"]:
            return
        project = repository.get(project_id)
        task = _find_task(project, task_id)
        ports.notify_intervention(
            project, task, ports.redact(reason), review_attempt_id,
            event="blocked", kind="error",
        )
    except (ProjectNotFoundError, RuntimeError):
        return


def extract_json(text: Any) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        pass
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


def normalize_review(
    result: Mapping[str, Any] | None,
    reviewer: Mapping[str, Any] | None,
    attempt_id: str,
    review_id: str,
    *,
    redact: Callable[[Any], str],
    now: Callable[[], str],
) -> dict[str, Any]:
    """Normalize untrusted Provider output; malformed output fails closed."""
    result = result if isinstance(result, Mapping) else {}
    reviewer = reviewer if isinstance(reviewer, Mapping) else {}
    explicit = result.get("review")
    parsed = explicit if isinstance(explicit, dict) else extract_json(result.get("reply"))
    parsed = parsed if isinstance(parsed, dict) else {}
    status = str(parsed.get("status") or "").strip().lower()
    schema_ok = (
        all(key in parsed for key in ("status", "summary", "rationale", "items"))
        and isinstance(parsed.get("items"), list)
    )
    if not schema_ok or status not in {"pass", "needs_more_work", "blocked"}:
        status = "blocked"
    items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    sanitized_items = _sanitize_review_items(items, redact)
    return {
        "id": review_id,
        "attemptId": attempt_id,
        "status": status,
        "summary": redact(parsed.get("summary") or result.get("reply") or ""),
        "rationale": redact(parsed.get("rationale") or result.get("error") or ""),
        "items": sanitized_items,
        "reviewer": {"providerKind": reviewer.get("providerKind"), "agentId": reviewer.get("id")},
        "providerStatus": result.get("status") or ("completed" if result.get("ok") else "review_failed"),
        "raw": redact(result.get("reply") or ""),
        "reviewedAt": now(),
    }


_REVIEW_ITEM_FIELDS = ("status", "text", "summary", "file", "severity")
_REVIEW_ITEM_TEXT_LIMIT = 1000


def _bounded_redacted_text(value: Any, redact: Callable[[Any], str]) -> str:
    text = redact(value)
    return text if len(text) <= _REVIEW_ITEM_TEXT_LIMIT else text[:_REVIEW_ITEM_TEXT_LIMIT] + "...[truncated]"


def _sanitize_review_items(items: list[Any], redact: Callable[[Any], str]) -> list[Any]:
    """Persist only the bounded public Review item DTO, never arbitrary Provider JSON."""
    sanitized: list[Any] = []
    for item in items[:50]:
        if isinstance(item, str):
            sanitized.append(_bounded_redacted_text(item, redact))
            continue
        if not isinstance(item, Mapping):
            continue
        safe = {
            key: _bounded_redacted_text(item.get(key), redact)
            for key in _REVIEW_ITEM_FIELDS
            if item.get(key) is not None
        }
        if safe:
            sanitized.append(safe)
    return sanitized


def acceptance_intent_id(attempt_id: str) -> str:
    return f"project-acceptance:{attempt_id}"


def build_acceptance_intent(
    project: Project,
    task: Task,
    attempt_id: str,
    reason: str,
    *,
    redact: Callable[[Any], str],
    open_url: Callable[[str, str], str],
) -> dict[str, Any]:
    """Build a sanitized transport-neutral notification DTO."""
    project_id = str(project.get("id") or "")
    task_id = str(task.get("id") or "")
    review = task.get("reviewResult") if isinstance(task.get("reviewResult"), dict) else {}
    safe_project_title = redact(project.get("title") or project_id or "-")
    safe_task_title = redact(task.get("title") or task_id or "-")
    return {
        "id": acceptance_intent_id(attempt_id),
        "type": "application_form",
        "title": f"项目任务等待验收: {safe_task_title}",
        "summary": redact(reason or "Project Execution 已完成并通过 Review，等待用户验收。"),
        "state": "pending",
        "multi_participant": False,
        "related": {"type": "project_task", "id": f"{project_id}:{task_id}", "title": safe_task_title},
        "details": [
            ("项目", safe_project_title),
            ("任务", safe_task_title),
            ("Attempt", redact(attempt_id)),
            ("Review", redact(review.get("summary") or "-")),
        ],
        "inputs": [{
            "name": "feedback", "label": "返工原因",
            "placeholder": "点击“要求返工”前填写需要补充或重做的内容",
            "multiline": True, "required": False,
        }],
        "actions": [
            {"category": "confirm", "text": "接受", "value": {
                "action": "project_execution_accept", "project_id": project_id,
                "task_id": task_id, "attempt_id": attempt_id,
            }},
            {"category": "cancel", "text": "要求返工", "value": {
                "action": "project_execution_rework", "project_id": project_id,
                "task_id": task_id, "attempt_id": attempt_id,
            }},
            {"category": "jump", "text": "打开任务", "url": open_url(project_id, task_id)},
        ],
        "target": "feishu-project-execution-acceptance",
    }


def stage_notification_intent(task: Task, attempt_id: str, intent: Mapping[str, Any], now: Callable[[], str]) -> bool:
    """Persist a stable local intent exactly once; return whether delivery is due."""
    attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
    container = attempt if isinstance(attempt, dict) else task
    intents = container.setdefault("notificationIntents", {})
    if not isinstance(intents, dict):
        intents = {}
        container["notificationIntents"] = intents
    key = str(intent.get("id") or acceptance_intent_id(attempt_id))
    existing = intents.get(key)
    if isinstance(existing, dict):
        return existing.get("deliveryStatus") not in {"sent", "sending"}
    intents[key] = {
        "id": key,
        "intent": copy.deepcopy(dict(intent)),
        "createdAt": now(),
        "deliveryStatus": "pending",
        "attempts": 0,
    }
    return True


def notification_intent(task: Task, attempt_id: str, key: str) -> dict[str, Any] | None:
    attempt = next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)
    container = attempt if isinstance(attempt, dict) else task
    intents = container.get("notificationIntents") if isinstance(container, dict) else None
    value = intents.get(key) if isinstance(intents, dict) else None
    return value if isinstance(value, dict) else None
