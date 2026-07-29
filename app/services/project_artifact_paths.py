"""Path helpers for project execution artifacts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping


def project_uses_dated_run_artifacts(project: Mapping[str, Any] | None) -> bool:
    value = project if isinstance(project, Mapping) else {}
    return (
        str(value.get("projectType") or "").strip().lower() == "reusable"
        or bool(value.get("longTermProject"))
        or bool(value.get("recurrence"))
        or bool(value.get("recurrenceRef"))
    )


def task_final_result_run_slug(project: Mapping[str, Any] | None, task: Mapping[str, Any] | None) -> str:
    if not project_uses_dated_run_artifacts(project):
        return ""
    project_value = project if isinstance(project, Mapping) else {}
    value = task if isinstance(task, Mapping) else {}
    final_result = value.get("finalResult") if isinstance(value.get("finalResult"), Mapping) else {}
    attempts = value.get("attempts") if isinstance(value.get("attempts"), list) else []
    attempt = _matching_attempt(value, final_result, attempts)
    timestamp = (
        final_result.get("generatedAt")
        or value.get("completedAt")
        or attempt.get("finishedAt")
        or attempt.get("startedAt")
        or project_value.get("updatedAt")
        or project_value.get("createdAt")
    )
    date_part = _timestamp_slug(timestamp)
    orchestration = project_value.get("orchestration") if isinstance(project_value.get("orchestration"), Mapping) else {}
    identity = (
        final_result.get("sourceAttemptId")
        or attempt.get("id")
        or value.get("activeAttemptId")
        or attempt.get("stageRunId")
        or value.get("stageRunId")
        or orchestration.get("currentRunId")
    )
    identity_part = _short_slug(identity)
    return f"{date_part}--{identity_part}" if identity_part else date_part


def task_final_result_workspace_relative_path(
    project: Mapping[str, Any] | None,
    task: Mapping[str, Any] | None,
) -> str:
    if not project_uses_dated_run_artifacts(project):
        return ""
    slug = task_final_result_run_slug(project, task)
    if not slug:
        return ""
    value = task if isinstance(task, Mapping) else {}
    task_id = str(value.get("id") or "").strip()
    task_title = str(value.get("title") or "task").strip()
    task_part = _path_slug(task_id or task_title) or "task"
    return f".vo/{task_part}/{slug.split('--', 1)[0].replace('-', '')}/TASK_FINAL_RESULT.md"


def task_final_result_workspace_task_directory(
    project: Mapping[str, Any] | None,
    task: Mapping[str, Any] | None,
) -> str:
    if not project_uses_dated_run_artifacts(project):
        return ""
    value = task if isinstance(task, Mapping) else {}
    task_id = str(value.get("id") or "").strip()
    task_title = str(value.get("title") or "task").strip()
    task_part = _path_slug(task_id or task_title) or "task"
    return f".vo/{task_part}"


def artifact_prompt_run_directory(project: Mapping[str, Any] | None, task: Mapping[str, Any] | None) -> str:
    path = task_final_result_workspace_relative_path(project, task)
    if not path:
        return ""
    return path.rsplit("/", 1)[0]


def _matching_attempt(task: Mapping[str, Any], final_result: Mapping[str, Any], attempts: list[Any]) -> Mapping[str, Any]:
    source_id = str(final_result.get("sourceAttemptId") or task.get("activeAttemptId") or "").strip()
    for item in attempts:
        if isinstance(item, Mapping) and source_id and str(item.get("id") or "") == source_id:
            return item
    for item in reversed(attempts):
        if isinstance(item, Mapping):
            return item
    return {}


def _timestamp_slug(value: Any) -> str:
    text = str(value or "").strip()
    parsed: datetime | None = None
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y%m%d-%H%M%S")


def _short_slug(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-").lower()
    return slug[:18]


def _path_slug(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-").lower()
    return slug[:120]
