"""Project reset helpers shared by legacy and stage-pipeline flows."""

from __future__ import annotations

from typing import Any, Mapping

from .project_orchestration import (
    STATE_DRAFT,
    default_orchestration_state,
    default_skip_state,
    is_marked_project,
    orchestration_state,
)


ACTIVE_ATTEMPT_STATES = frozenset({
    "validating",
    "executing",
    "retrying",
    "reviewing",
    "reworking",
    "meeting_action_items",
})


def reset_marked_stage_pipeline(
    project: dict[str, Any],
    *,
    now: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Clear stage-pipeline runtime bindings during a full project reset."""
    if not is_marked_project(project):
        return {"ok": True, "resetTaskIds": [], "cancelledAttemptCount": 0}

    previous = orchestration_state(project)
    reset_state = default_orchestration_state()
    reset_state["revision"] = int(previous.get("revision") or 0) + 1
    project["orchestration"] = reset_state

    reset_task_ids: set[str] = set()
    cancelled_attempts = 0
    default_skip = default_skip_state()
    for task in project.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        changed = False
        if str(task.get("stageRunId") or "").strip():
            task["stageRunId"] = None
            changed = True
        if _skip_changed(task.get("orchestrationSkip"), default_skip):
            task["orchestrationSkip"] = dict(default_skip)
            changed = True
        if task.get("activeAttemptId"):
            task["activeAttemptId"] = None
            changed = True
        for attempt in task.get("attempts") or []:
            if not isinstance(attempt, dict):
                continue
            if str(attempt.get("status") or "").strip().lower() not in ACTIVE_ATTEMPT_STATES:
                continue
            attempt["status"] = "cancelled"
            attempt["cancelledAt"] = now
            attempt["cancelledBy"] = actor
            attempt["cancelReason"] = reason
            cancelled_attempts += 1
            changed = True
        if changed:
            task_id = str(task.get("id") or "").strip()
            if task_id:
                reset_task_ids.add(task_id)

    project["projectExecutionFlowActive"] = False
    project["projectExecutionFlowStopReason"] = None
    project["workflowActive"] = False
    project["workflowPhase"] = "idle"
    project["activeTaskId"] = None
    project["activeAgent"] = None
    return {
        "ok": True,
        "resetTaskIds": sorted(reset_task_ids),
        "cancelledAttemptCount": cancelled_attempts,
        "orchestrationState": STATE_DRAFT,
        "orchestrationRevision": reset_state["revision"],
    }


def marked_stage_reset_is_risky(project: Mapping[str, Any]) -> bool:
    if not is_marked_project(project):
        return False
    state = orchestration_state(project)
    if state.get("state") != STATE_DRAFT:
        return True
    if state.get("currentRunId") or state.get("currentStage") or state.get("pauseReason"):
        return True
    return any(
        isinstance(task, Mapping)
        and (
            str(task.get("stageRunId") or "").strip()
            or bool(task.get("activeAttemptId"))
            or _skip_changed(task.get("orchestrationSkip"), default_skip_state())
            or _has_active_attempt(task)
        )
        for task in project.get("tasks") or []
    )


def _skip_changed(raw: Any, default_skip: Mapping[str, Any]) -> bool:
    return isinstance(raw, Mapping) and any(raw.get(key) != value for key, value in default_skip.items())


def _has_active_attempt(task: Mapping[str, Any]) -> bool:
    for attempt in task.get("attempts") or []:
        if isinstance(attempt, Mapping) and str(attempt.get("status") or "").strip().lower() in ACTIVE_ATTEMPT_STATES:
            return True
    return False
