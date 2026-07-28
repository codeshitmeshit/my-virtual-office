"""Task final-result artifacts and compact stage handoff indexes."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


FINAL_RESULT_FILENAME = "TASK_FINAL_RESULT.md"
AVAILABLE = "available"
MISSING = "missing"
SKIPPED = "skipped"


def ensure_task_final_result(
    project: Mapping[str, Any] | None,
    task: dict[str, Any],
    *,
    attempt: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
    provider_result: Mapping[str, Any] | None = None,
    status: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Create or refresh the compact final-result index stored on a task."""

    existing = task.get("finalResult") if isinstance(task.get("finalResult"), dict) else {}
    evidence_map = dict(evidence or task.get("evidence") or {})
    attempt_map = dict(attempt or {})
    provider_map = dict(provider_result or {})
    result_status = status or existing.get("status") or AVAILABLE
    if result_status not in {AVAILABLE, MISSING, SKIPPED}:
        result_status = AVAILABLE
    summary = (
        _compact(existing.get("summary"), 600)
        or _compact(evidence_map.get("executorSummary"), 600)
        or _compact(provider_map.get("reply"), 600)
        or _fallback_summary(task, result_status)
    )
    attempt_id = (
        existing.get("sourceAttemptId")
        or evidence_map.get("attemptId")
        or attempt_map.get("id")
        or task.get("activeAttemptId")
    )
    final_result = {
        "schemaVersion": 1,
        "status": result_status,
        "summary": summary,
        "markdownPath": existing.get("markdownPath") or "",
        "sourceAttemptId": attempt_id or "",
        "executionStage": _positive_int(task.get("executionStage")),
        "generatedAt": now or existing.get("generatedAt") or "",
        "artifactRefs": _artifact_refs(evidence_map, provider_map),
    }
    if result_status == SKIPPED:
        skip = task.get("orchestrationSkip") if isinstance(task.get("orchestrationSkip"), dict) else {}
        final_result["skipReason"] = skip.get("decisionReason") or skip.get("reason") or ""
        final_result["summary"] = summary or "Task was skipped by approved orchestration decision."
    task["finalResult"] = final_result
    return final_result


def render_task_final_result_markdown(project: Mapping[str, Any] | None, task: Mapping[str, Any]) -> str:
    """Render the fixed Markdown artifact body for a task final result."""

    final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
    evidence = task.get("evidence") if isinstance(task.get("evidence"), Mapping) else {}
    status = str(final_result.get("status") or MISSING)
    title = str(task.get("title") or task.get("id") or "Task")
    lines = [
        "# TASK_FINAL_RESULT",
        "",
        "## Task",
        f"- Project: {str((project or {}).get('title') or '')}",
        f"- Task: {title}",
        f"- Task ID: {str(task.get('id') or '')}",
        f"- Stage: {final_result.get('executionStage') or task.get('executionStage') or ''}",
        f"- Status: {status}",
        f"- Source attempt: {str(final_result.get('sourceAttemptId') or '')}",
        f"- Generated at: {str(final_result.get('generatedAt') or '')}",
        "",
        "## Final Conclusion",
        _paragraph(final_result.get("summary") or _fallback_summary(task, status)),
        "",
        "## Completed Work",
    ]
    completed = _bullet_lines(evidence.get("completedWork") or evidence.get("work") or evidence.get("executorSummary"))
    lines.extend(completed or ["- See the final conclusion above."])
    lines.extend(["", "## Changed Files And Artifacts"])
    refs = final_result.get("artifactRefs") if isinstance(final_result.get("artifactRefs"), list) else []
    lines.extend(_artifact_lines(refs) or ["- No changed files or artifacts were recorded."])
    lines.extend(["", "## Verification"])
    tests = evidence.get("testResults") if isinstance(evidence.get("testResults"), list) else []
    checklist = evidence.get("checklist") if isinstance(evidence.get("checklist"), list) else []
    verification = [_compact(item, 220) for item in tests if _compact(item, 220)]
    if checklist:
        verification.extend(_checklist_lines(checklist))
    lines.extend([f"- {item}" for item in verification] or ["- No explicit verification evidence was recorded."])
    lines.extend(["", "## Risks And Follow-up"])
    risk_text = evidence.get("error") or evidence.get("remainingRisks") or evidence.get("risk") or ""
    lines.extend(_bullet_lines(risk_text) or ["- No remaining risks were recorded."])
    lines.extend(["", "## References For Later Stages"])
    markdown_path = str(final_result.get("markdownPath") or "")
    lines.append(f"- Final result Markdown: {markdown_path or FINAL_RESULT_FILENAME}")
    if refs:
        for ref in refs[:20]:
            if isinstance(ref, Mapping) and ref.get("path"):
                lines.append(f"- Artifact: {ref.get('path')}")
    return "\n".join(lines).rstrip() + "\n"


def build_stage_handoff(project: Mapping[str, Any], stage: int, *, generated_at: str | None = None) -> dict[str, Any]:
    """Build the compact result index for all tasks in one completed stage."""

    tasks = []
    for task in project.get("tasks") or []:
        if not isinstance(task, Mapping) or _positive_int(task.get("executionStage")) != stage:
            continue
        final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
        tasks.append({
            "taskId": str(task.get("id") or ""),
            "title": str(task.get("title") or ""),
            "stage": stage,
            "status": str(final_result.get("status") or MISSING),
            "summary": _compact(final_result.get("summary"), 600),
            "markdownPath": str(final_result.get("markdownPath") or ""),
            "sourceAttemptId": str(final_result.get("sourceAttemptId") or ""),
            "artifactRefs": list(final_result.get("artifactRefs") or [])[:20] if isinstance(final_result.get("artifactRefs"), list) else [],
        })
    return {
        "schemaVersion": 1,
        "stage": stage,
        "generatedAt": generated_at or "",
        "tasks": tasks,
    }


def record_stage_handoff(project: dict[str, Any], stage: int, *, generated_at: str | None = None) -> dict[str, Any]:
    """Persist one stage handoff into project.orchestration.stageHandoffs."""

    for task in project.get("tasks") or []:
        if not isinstance(task, dict) or _positive_int(task.get("executionStage")) != stage:
            continue
        final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
        if final_result:
            continue
        skip = task.get("orchestrationSkip") if isinstance(task.get("orchestrationSkip"), Mapping) else {}
        status = SKIPPED if skip.get("status") == "approved" else AVAILABLE
        ensure_task_final_result(project, task, status=status, now=generated_at)
    handoff = build_stage_handoff(project, stage, generated_at=generated_at)
    orchestration = project.setdefault("orchestration", {})
    handoffs = orchestration.get("stageHandoffs")
    if not isinstance(handoffs, dict):
        handoffs = {}
    handoffs[str(stage)] = handoff
    orchestration["stageHandoffs"] = handoffs
    return handoff


def prior_stage_result_prompt_block(project: Mapping[str, Any], task: Mapping[str, Any]) -> str:
    """Render compact prior-stage result indexes for a task execution prompt."""

    current_stage = _positive_int(task.get("executionStage"))
    if current_stage is None or current_stage <= 1:
        return ""
    orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
    handoffs = orchestration.get("stageHandoffs") if isinstance(orchestration.get("stageHandoffs"), Mapping) else {}
    selected = []
    for raw_stage, handoff in sorted(handoffs.items(), key=lambda item: _positive_int(item[0]) or 0):
        stage = _positive_int(raw_stage)
        if stage is None or stage >= current_stage or not isinstance(handoff, Mapping):
            continue
        selected.append(handoff)
    if not selected:
        return ""
    lines = [
        "PRIOR STAGE RESULT INDEX:",
        "Use these prior task outputs as dependency context. Inspect the listed Markdown path or artifact refs when the current task depends on the earlier conclusion. Do not assume parallel tasks were merged into one output.",
    ]
    for handoff in selected:
        lines.append(f"- Stage {handoff.get('stage')}:")
        tasks = handoff.get("tasks") if isinstance(handoff.get("tasks"), list) else []
        for item in tasks:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("markdownPath") or "")
            summary = _compact(item.get("summary"), 360)
            lines.append(
                "  - "
                f"{item.get('title') or item.get('taskId')} "
                f"[taskId={item.get('taskId')}, status={item.get('status')}, result={path or 'missing'}]: "
                f"{summary or 'No summary recorded.'}"
            )
    return "\n".join(lines) + "\n"


def task_final_result_prompt_instructions() -> str:
    return (
        "TASK FINAL RESULT REQUIREMENT:\n"
        f"- Treat `{FINAL_RESULT_FILENAME}` as the mandatory default artifact for this task.\n"
        "- Your final Markdown summary is the source for that artifact when no explicit deliverable file is requested.\n"
        "- Include the final conclusion, completed work, changed files/artifacts, verification, remaining risks, and notes useful for later stages.\n"
        "- Later-stage tasks will receive only compact indexes and paths by default, so keep this summary self-contained and searchable.\n"
    )


def _compact(value: Any, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit].rstrip() + "...[truncated]"


def _fallback_summary(task: Mapping[str, Any], status: str) -> str:
    if status == SKIPPED:
        return "Task was skipped by approved orchestration decision."
    return f"Task '{task.get('title') or task.get('id') or 'task'}' reached a terminal accepted state."


def _artifact_refs(*sources: Mapping[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        candidates = []
        for key in ("changedFiles", "files", "artifacts", "artifactRefs"):
            raw = source.get(key)
            if isinstance(raw, list):
                candidates.extend(raw)
        for item in candidates:
            if isinstance(item, Mapping):
                path = str(item.get("path") or item.get("file") or item.get("relpath") or "").strip()
                kind = str(item.get("kind") or item.get("type") or "file").strip()
            else:
                path = str(item or "").strip()
                kind = "file"
            if not path or path in seen:
                continue
            seen.add(path)
            refs.append({"kind": kind or "file", "path": path})
            if len(refs) >= 50:
                return refs
    return refs


def _artifact_lines(refs: Iterable[Any]) -> list[str]:
    lines = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        path = str(ref.get("path") or "").strip()
        if path:
            lines.append(f"- {str(ref.get('kind') or 'file')}: {path}")
    return lines


def _bullet_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        values = [_compact(item, 220) for item in value]
    else:
        text = str(value or "").strip()
        values = [line.strip(" -") for line in text.splitlines() if line.strip()]
        if len(values) == 1 and len(values[0]) > 220:
            values = [values[0][:220].rstrip() + "...[truncated]"]
    return [f"- {item}" for item in values if item]


def _checklist_lines(checklist: list[Any]) -> list[str]:
    lines = []
    for item in checklist[:20]:
        if not isinstance(item, Mapping):
            continue
        status = "done" if item.get("done") is True else "pending"
        text = _compact(item.get("text") or item.get("id"), 180)
        if text:
            lines.append(f"checklist {status}: {text}")
    return lines


def _paragraph(value: Any) -> str:
    text = str(value or "").strip()
    return text or "No final conclusion was recorded."


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
