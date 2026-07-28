"""Shared scheduling decisions for marked stage-pipeline projects."""

from __future__ import annotations

from typing import Any, Mapping

from .project_orchestration import (
    STATE_COMPLETED,
    STATE_PAUSING,
    STATE_RUNNING,
    STATE_STARTING,
    active_task_count,
    is_marked_project,
    orchestration_state,
    task_is_accepted_terminal,
    task_stage,
)


MARKED_SCHEDULING_ACTIVE_STATES = frozenset({STATE_STARTING, STATE_RUNNING, STATE_PAUSING})


def marked_project_scheduling_satisfaction(project: Mapping[str, Any]) -> str | None:
    """Return already-started/completed scheduling state for marked projects."""

    if not is_marked_project(project):
        return None
    state = orchestration_state(project)
    if state.get("state") == STATE_COMPLETED or marked_project_all_tasks_completed(project):
        return "already_completed"
    if state.get("state") in MARKED_SCHEDULING_ACTIVE_STATES or active_task_count(project) > 0:
        return "already_active"
    return None


def marked_project_all_tasks_completed(project: Mapping[str, Any]) -> bool:
    if not is_marked_project(project):
        return False
    tasks = [task for task in project.get("tasks") or [] if isinstance(task, Mapping)]
    return bool(tasks) and all(task_is_accepted_terminal(task) for task in tasks)


def marked_task_cron_skip_reason(project: Mapping[str, Any], task: Mapping[str, Any] | None) -> str:
    """Explain why task-targeted cron cannot launch a marked project task."""

    if task is None:
        return "task_missing"
    state = orchestration_state(project)
    current_stage = state.get("currentStage")
    try:
        current_stage = int(current_stage)
    except (TypeError, ValueError):
        current_stage = None
    if current_stage is None or task_stage(task) != current_stage:
        return "marked_task_not_current_stage"
    return "marked_project_task_cron_forbidden"
