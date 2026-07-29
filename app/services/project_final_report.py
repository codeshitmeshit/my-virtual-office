"""Project-level final report generation for completed stage pipelines."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .project_artifact_paths import project_uses_dated_run_artifacts


PROJECT_FINAL_REPORT_FILENAME = "PROJECT_FINAL_REPORT.md"


def ensure_project_final_report(
    project: dict[str, Any],
    *,
    now: str | None = None,
) -> dict[str, Any]:
    orchestration = project.setdefault("orchestration", {})
    if not isinstance(orchestration, dict):
        orchestration = {}
        project["orchestration"] = orchestration
    existing = orchestration.get("finalReport") if isinstance(orchestration.get("finalReport"), dict) else {}
    generated_at = now or existing.get("generatedAt") or _now_iso()
    markdown_path = existing.get("markdownPath") or project_final_report_workspace_relative_path(project, generated_at)
    tasks = [task for task in project.get("tasks") or [] if isinstance(task, Mapping)]
    completed = [task for task in tasks if task.get("completedAt") or str(task.get("executionState") or "").lower() in {"done", "completed"}]
    report = {
        "schemaVersion": 1,
        "status": "available",
        "markdownPath": markdown_path,
        "generatedAt": generated_at,
        "taskCount": len(tasks),
        "completedTaskCount": len(completed),
    }
    orchestration["finalReport"] = report
    return report


def project_final_report_workspace_relative_path(project: Mapping[str, Any] | None, generated_at: Any) -> str:
    if project_uses_dated_run_artifacts(project):
        return f".vo/project-final-reports/{_timestamp_slug(generated_at)}/{PROJECT_FINAL_REPORT_FILENAME}"
    return PROJECT_FINAL_REPORT_FILENAME


def render_project_final_report_markdown(project: Mapping[str, Any] | None) -> str:
    value = project if isinstance(project, Mapping) else {}
    orchestration = value.get("orchestration") if isinstance(value.get("orchestration"), Mapping) else {}
    final_report = orchestration.get("finalReport") if isinstance(orchestration.get("finalReport"), Mapping) else {}
    tasks = [task for task in value.get("tasks") or [] if isinstance(task, Mapping)]
    stages = _tasks_by_stage(tasks)
    title = str(value.get("title") or value.get("id") or "Project")
    generated_at = str(final_report.get("generatedAt") or orchestration.get("completedAt") or "")
    lines = [
        "# PROJECT_FINAL_REPORT",
        "",
        "## Project",
        f"- Project: {title}",
        f"- Project ID: {str(value.get('id') or '')}",
        f"- Status: {str(value.get('status') or '')}",
        f"- Generated at: {generated_at}",
        f"- Completed at: {str(orchestration.get('completedAt') or '')}",
        f"- Tasks: {final_report.get('completedTaskCount', _completed_count(tasks))}/{final_report.get('taskCount', len(tasks))}",
        "",
        "## Executive Summary",
        _project_summary(value, tasks),
        "",
        "## Stage Results",
    ]
    if stages:
        for stage in sorted(stages):
            lines.extend(["", f"### Stage {stage}"])
            for task in stages[stage]:
                lines.extend(_task_lines(task))
    else:
        lines.append("- No task results were recorded.")
    lines.extend(["", "## Final Artifacts"])
    artifact_lines = _artifact_lines(tasks)
    lines.extend(artifact_lines or ["- No task artifacts were recorded."])
    lines.extend(["", "## Risks And Follow-up"])
    risk_lines = _risk_lines(tasks)
    lines.extend(risk_lines or ["- No remaining risks were recorded."])
    return "\n".join(lines).rstrip() + "\n"


def _tasks_by_stage(tasks: list[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    result: dict[int, list[Mapping[str, Any]]] = {}
    for task in tasks:
        stage = _positive_int(task.get("executionStage")) or 0
        result.setdefault(stage, []).append(task)
    for stage_tasks in result.values():
        stage_tasks.sort(key=lambda item: (str(item.get("completedAt") or ""), str(item.get("id") or "")))
    return result


def _task_lines(task: Mapping[str, Any]) -> list[str]:
    final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
    status = str(final_result.get("status") or task.get("executionState") or "unknown")
    summary = _compact(final_result.get("summary"), 900) or _compact((task.get("evidence") or {}).get("executorSummary") if isinstance(task.get("evidence"), Mapping) else "", 900)
    path = str(final_result.get("markdownPath") or "")
    lines = [
        f"- **{str(task.get('title') or task.get('id') or 'Task')}** `{status}`",
        f"  - Task ID: {str(task.get('id') or '')}",
    ]
    if summary:
        lines.append(f"  - Summary: {summary}")
    if path:
        lines.append(f"  - Task final result: `{path}`")
    return lines


def _project_summary(project: Mapping[str, Any], tasks: list[Mapping[str, Any]]) -> str:
    completed = _completed_count(tasks)
    total = len(tasks)
    title = str(project.get("title") or "project")
    if total:
        return f"{title} finished with {completed}/{total} tasks in accepted terminal states. See the stage results below for each task conclusion and artifact path."
    return f"{title} completed without recorded tasks."


def _artifact_lines(tasks: list[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for task in tasks:
        final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
        path = str(final_result.get("markdownPath") or "").strip()
        if path and path not in seen:
            seen.add(path)
            lines.append(f"- task-result: `{path}`")
        refs = final_result.get("artifactRefs") if isinstance(final_result.get("artifactRefs"), list) else []
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            ref_path = str(ref.get("path") or "").strip()
            if ref_path and ref_path not in seen:
                seen.add(ref_path)
                lines.append(f"- {str(ref.get('kind') or 'file')}: `{ref_path}`")
    return lines


def _risk_lines(tasks: list[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for task in tasks:
        evidence = task.get("evidence") if isinstance(task.get("evidence"), Mapping) else {}
        text = evidence.get("remainingRisks") or evidence.get("risk") or evidence.get("error") or ""
        compact = _compact(text, 240)
        if compact:
            lines.append(f"- {str(task.get('title') or task.get('id') or 'Task')}: {compact}")
    return lines


def _completed_count(tasks: list[Mapping[str, Any]]) -> int:
    return sum(1 for task in tasks if task.get("completedAt") or str(task.get("executionState") or "").lower() in {"done", "completed"})


def _compact(value: Any, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit].rstrip() + "...[truncated]"


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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
    return parsed.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
