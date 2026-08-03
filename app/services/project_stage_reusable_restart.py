"""Reusable stage-pipeline restart helpers."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .project_orchestration import STATE_COMPLETED, STATE_DRAFT, orchestration_state


MEETING_CHECKLIST_SOURCES = frozenset({"meeting_action_item", "meeting_risk"})


def should_restart_completed_reusable_project(project: Mapping[str, Any]) -> bool:
    """Return whether a completed project should be reset before stage start."""
    return (
        str(project.get("projectType") or "").strip().lower() == "reusable"
        and orchestration_state(project).get("state") == STATE_COMPLETED
    )


def preview_completed_reusable_restart(
    project: Mapping[str, Any],
    *,
    now: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Build the project shape used for preflight after an automatic restart."""
    restarted = copy.deepcopy(dict(project))
    reset_completed_reusable_project(restarted, now=now, actor=actor, reason=reason)
    return restarted


def reset_completed_reusable_project(
    project: dict[str, Any],
    *,
    now: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Clear completed-run state while preserving audit/history for a new run."""
    state = orchestration_state(project)
    state.update({
        "state": STATE_DRAFT,
        "currentStage": None,
        "currentRunId": None,
        "pauseReason": None,
        "startedAt": None,
        "completedAt": None,
    })
    project["orchestration"] = state
    if str(project.get("status") or "").lower() == "completed":
        project["status"] = "active"
    project["projectExecutionFlowActive"] = False
    project["projectExecutionFlowStopReason"] = None
    project["workflowActive"] = False
    project["workflowPhase"] = "restarting"
    project["activeTaskId"] = None
    project["activeAgent"] = None
    project["updatedAt"] = now

    for task in project.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        previous_state = str(task.get("executionState") or "").strip() or (
            "done" if task.get("completedAt") else "backlog"
        )
        if str(task.get("stageRunId") or "").strip():
            task["previousStageRunId"] = task.get("stageRunId")
        task["stageRunId"] = None
        task["completedAt"] = None
        task["executionState"] = "backlog"
        task["activeAttemptId"] = None
        task["blockedReason"] = None
        task["lastError"] = None
        task["reworkFeedback"] = None
        task["reworkCount"] = 0
        task["evidence"] = {}
        task["reviewResult"] = {}
        _archive_meeting_blocker(task, now=now, actor=actor, reason=reason)
        task["meetingBlocker"] = {}
        task["meetingActionItems"] = []
        task["meetingDecisionHistory"] = []
        task["meetingDiscussionPoints"] = []
        task["meetingRecords"] = []
        _reset_checklist_completion(task)
        task["updatedAt"] = now
        task.setdefault("stateHistory", []).append({
            "actor": actor,
            "from": previous_state,
            "to": "backlog",
            "reason": reason,
            "at": now,
        })
        task["stateHistory"] = task["stateHistory"][-100:]
    return project


def _archive_meeting_blocker(
    task: dict[str, Any],
    *,
    now: str,
    actor: str,
    reason: str,
) -> None:
    blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), dict) else {}
    if not blocker:
        return
    archived = dict(blocker)
    archived["resetAt"] = now
    archived["resetBy"] = actor
    archived["resetReason"] = reason
    task.setdefault("meetingBlockerHistory", []).append(archived)
    task["meetingBlockerHistory"] = task["meetingBlockerHistory"][-50:]


def _reset_checklist_completion(task: dict[str, Any]) -> None:
    checklist = task.get("checklist")
    if not isinstance(checklist, list):
        return
    task["checklist"] = [
        item
        for item in checklist
        if isinstance(item, dict) and item.get("source") in MEETING_CHECKLIST_SOURCES
    ]
