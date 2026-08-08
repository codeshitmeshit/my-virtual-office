"""Persist and resume one project attempt waiting for a human decision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .human_decision_chat_continuation import ContinuationDispatchResult
from .human_decisions import HumanDecisionContinuationClaim
from .project_human_decision_comment import ensure_decision_comment
from .project_repository import ProjectNotFoundError


class ProjectRepositoryPort(Protocol):
    def get(self, project_id: str) -> dict[str, Any] | None: ...
    def update(self, project_id: str, mutator: Callable[[dict[str, Any]], Any]) -> Any: ...


@dataclass(frozen=True)
class ProjectContinuationPorts:
    repository: ProjectRepositoryPort
    now: Callable[[], str]
    new_id: Callable[[], str]
    launch_direct: Callable[[str, str, str], bool]
    submit_stage: Callable[[str, str, str, str], bool]


def _task(project: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    return next((item for item in project.get("tasks") or [] if item.get("id") == task_id), None)


def _attempt(task: dict[str, Any], attempt_id: str) -> dict[str, Any] | None:
    return next((item for item in task.get("attempts") or [] if item.get("id") == attempt_id), None)


def mark_attempt_waiting(
    repository: ProjectRepositoryPort,
    *,
    project_id: str,
    task_id: str,
    attempt_id: str,
    decision_id: str,
    agent_id: str,
    now: Callable[[], str],
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "code": "project_attempt_not_found"}

    def mutate(project: dict[str, Any]) -> None:
        task = _task(project, task_id)
        attempt = _attempt(task or {}, attempt_id)
        if not task or not attempt:
            return
        executor_id = str((attempt.get("executor") or {}).get("id") or task.get("executorAgentId") or "")
        if task.get("activeAttemptId") != attempt_id:
            result.update(code="project_attempt_replaced")
            return
        if executor_id and executor_id != agent_id:
            result.update(code="project_executor_mismatch")
            return
        existing = str(attempt.get("humanDecisionId") or "")
        if existing and existing != decision_id:
            result.update(code="project_attempt_decision_conflict")
            return
        attempt.update({
            "status": "awaiting_user_decision",
            "humanDecisionId": decision_id,
            "humanDecisionWaitingAt": now(),
        })
        task["executionState"] = "awaiting_user_decision"
        task["updatedAt"] = now()
        project["updatedAt"] = now()
        result.update(ok=True, code="", mode="stage" if attempt.get("stageRunId") else "direct")

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        result.update(code="project_not_found")
    return result


class ProjectHumanDecisionContinuation:
    def __init__(self, *, ports: ProjectContinuationPorts):
        self._ports = ports

    def dispatch(self, claim: HumanDecisionContinuationClaim) -> ContinuationDispatchResult:
        binding = claim.binding
        project_id = str(binding.get("projectId") or "")
        task_id = str(binding.get("taskId") or "")
        attempt_id = str(binding.get("attemptId") or "")
        run_id = str(binding.get("runId") or "")
        source = claim.decision.get("source") if isinstance(claim.decision.get("source"), dict) else {}
        if (
            claim.kind != "task" or not project_id or not task_id or not attempt_id
            or source.get("id") != task_id or source.get("projectId") != project_id
        ):
            return ContinuationDispatchResult("failed", "project_binding_invalid")

        resume_key = f"human-decision-resume:{claim.decision_id}"
        prepared: dict[str, Any] = {"ok": False, "code": "project_attempt_not_found"}
        resolution = claim.decision.get("resolution") if isinstance(claim.decision.get("resolution"), dict) else {}

        def prepare(project: dict[str, Any]) -> None:
            task = _task(project, task_id)
            attempt = _attempt(task or {}, attempt_id)
            if not task or not attempt:
                return
            if task.get("activeAttemptId") != attempt_id:
                prepared.update(code="project_attempt_replaced")
                return
            if attempt.get("decisionResumeKey") == resume_key and attempt.get("status") == "executing":
                prepared.update(ok=True, idempotent=True, mode="stage" if attempt.get("stageRunId") else "direct")
                return
            if attempt.get("status") != "awaiting_user_decision" or attempt.get("humanDecisionId") != claim.decision_id:
                prepared.update(code="project_attempt_not_waiting")
                return
            attempt.update({
                "status": "executing",
                "decisionResumeKey": resume_key,
                "decisionResume": {
                    "decisionId": claim.decision_id,
                    "answer": str(resolution.get("answer") or ""),
                    "situation": str(claim.decision.get("situation") or ""),
                },
                "decisionResumedAt": self._ports.now(),
            })
            attempt.pop("runnerClaimedAt", None)
            task["executionState"] = "executing"
            task["updatedAt"] = self._ports.now()
            project["updatedAt"] = self._ports.now()
            ensure_decision_comment(
                task,
                claim.decision,
                decision_id=claim.decision_id,
                new_id=self._ports.new_id,
                now=self._ports.now,
            )
            prepared.update(ok=True, idempotent=False, mode="stage" if attempt.get("stageRunId") else "direct")

        try:
            self._ports.repository.update(project_id, prepare)
        except ProjectNotFoundError:
            return ContinuationDispatchResult("failed", "project_not_found")
        if not prepared.get("ok"):
            return ContinuationDispatchResult("failed", str(prepared.get("code") or "project_attempt_not_resumable"))
        if prepared.get("idempotent"):
            return ContinuationDispatchResult("dispatched")
        try:
            accepted = (
                self._ports.submit_stage(project_id, task_id, run_id, attempt_id)
                if prepared.get("mode") == "stage"
                else self._ports.launch_direct(project_id, task_id, attempt_id)
            )
        except Exception:
            return ContinuationDispatchResult("dispatch_uncertain", "project_dispatch_exception")
        if not accepted:
            def restore_waiting(project: dict[str, Any]) -> None:
                task = _task(project, task_id)
                attempt = _attempt(task or {}, attempt_id)
                if (
                    not task or not attempt
                    or task.get("activeAttemptId") != attempt_id
                    or attempt.get("decisionResumeKey") != resume_key
                ):
                    return
                attempt["status"] = "awaiting_user_decision"
                attempt.pop("decisionResumeKey", None)
                attempt.pop("decisionResume", None)
                attempt.pop("decisionResumedAt", None)
                task["executionState"] = "awaiting_user_decision"
                task["updatedAt"] = self._ports.now()
                project["updatedAt"] = self._ports.now()

            try:
                self._ports.repository.update(project_id, restore_waiting)
            except ProjectNotFoundError:
                return ContinuationDispatchResult("failed", "project_not_found")
            return ContinuationDispatchResult("not_dispatched_retryable", "project_dispatch_rejected")
        return ContinuationDispatchResult("dispatched")


__all__ = [
    "ProjectContinuationPorts",
    "ProjectHumanDecisionContinuation",
    "mark_attempt_waiting",
]
