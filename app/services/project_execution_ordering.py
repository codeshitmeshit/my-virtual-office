"""Project task execution ordering helpers."""

from __future__ import annotations

from typing import Any, Mapping


Task = dict[str, Any]
Project = dict[str, Any]


def task_execution_order(task: Mapping[str, Any], index: int = 0) -> int:
    """Return the project-wide execution order, with legacy order fallback."""
    try:
        explicit = int(task.get("executionOrder") or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return explicit
    try:
        legacy = int(task.get("order"))
    except (TypeError, ValueError):
        legacy = index
    return legacy + 1


def ordered_tasks(project: Mapping[str, Any]) -> list[Task]:
    tasks = [task for task in project.get("tasks", []) or [] if isinstance(task, dict)]
    indexed = list(enumerate(tasks))
    indexed.sort(
        key=lambda item: (
            task_execution_order(item[1], item[0]),
            item[1].get("createdAt") or "",
            item[1].get("id") or "",
        )
    )
    return [task for _, task in indexed]


def done_column_ids(project: Mapping[str, Any]) -> set[Any]:
    return {
        column.get("id")
        for column in project.get("columns", []) or []
        if isinstance(column, Mapping)
        and str(column.get("title") or "").strip().lower()
        in {"done", "completed", "verified", "published", "fixed", "closed"}
    }


def task_complete(project: Mapping[str, Any], task: Mapping[str, Any]) -> bool:
    if task.get("completedAt"):
        return True
    if str(task.get("executionState") or "").strip().lower() in {
        "done",
        "completed",
        "execution_complete",
        "awaiting_user_acceptance",
    }:
        return True
    return task.get("columnId") in done_column_ids(project)


def prior_incomplete_task(project: Mapping[str, Any], task_id: str) -> Task | None:
    for task in ordered_tasks(project):
        if task.get("id") == task_id:
            return None
        if not task_complete(project, task):
            return task
    return None


def first_incomplete_task(project: Mapping[str, Any]) -> Task | None:
    return next((task for task in ordered_tasks(project) if not task_complete(project, task)), None)
