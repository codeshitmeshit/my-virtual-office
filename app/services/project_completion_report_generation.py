"""Generate and validate structured human-readable completion reports."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

from .project_completion_report_prompt import render_completion_report_prompt


REPORT_KEYS = frozenset({
    "goal",
    "conclusion",
    "keyResults",
    "nonFatalExceptions",
    "followUps",
    "importantArtifacts",
})
ARTIFACT_KEYS = frozenset({"label", "path", "note"})


class CompletionReportGenerationError(RuntimeError):
    def __init__(self, code: str, message: str, *, recoverable: bool) -> None:
        self.code = code
        self.recoverable = recoverable
        super().__init__(message)


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise CompletionReportGenerationError(
            "reporting_agent_invalid_output",
            "Completion report fields must be strings",
            recoverable=True,
        )
    return value.strip()[:limit]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise CompletionReportGenerationError(
            "reporting_agent_invalid_output",
            "Completion report list fields must be arrays",
            recoverable=True,
        )
    return [_text(item, 500) for item in value[:10] if isinstance(item, str) and item.strip()]


def _normalize_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != REPORT_KEYS:
        raise CompletionReportGenerationError(
            "reporting_agent_invalid_output",
            "Completion report output does not match the required schema",
            recoverable=True,
        )
    raw_artifacts = value.get("importantArtifacts")
    if not isinstance(raw_artifacts, list):
        raise CompletionReportGenerationError(
            "reporting_agent_invalid_output",
            "importantArtifacts must be an array",
            recoverable=True,
        )
    artifacts = []
    for item in raw_artifacts[:10]:
        if not isinstance(item, Mapping) or set(item) != ARTIFACT_KEYS:
            raise CompletionReportGenerationError(
                "reporting_agent_invalid_output",
                "importantArtifacts entries do not match the required schema",
                recoverable=True,
            )
        artifacts.append({
            "label": _text(item.get("label"), 200),
            "path": _text(item.get("path"), 500),
            "note": _text(item.get("note"), 500),
        })
    return {
        "goal": _text(value.get("goal"), 2000),
        "conclusion": _text(value.get("conclusion"), 4000),
        "keyResults": _text_list(value.get("keyResults")),
        "nonFatalExceptions": _text_list(value.get("nonFatalExceptions")),
        "followUps": _text_list(value.get("followUps")),
        "importantArtifacts": artifacts,
    }


def _bullets(items: Sequence[str], empty: str) -> list[str]:
    return [f"- {item}" for item in items] or [f"- {empty}"]


def render_completion_report_markdown(
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    report: Mapping[str, Any],
) -> str:
    lines = [
        f"# Project Completion Report — {str(project.get('title') or project.get('id') or 'Project')}",
        "",
        "## Execution",
        f"- Project ID: {str(project.get('id') or '')}",
        f"- Version: v{occurrence.get('version') or 1}",
        f"- Run: {str(occurrence.get('runId') or '')}",
        f"- Completed at: {str(occurrence.get('completedAt') or '')}",
        "",
        "## Goal",
        str(report.get("goal") or "No goal was provided."),
        "",
        "## Conclusion",
        str(report.get("conclusion") or "No conclusion was provided."),
        "",
        "## Key Results",
        *_bullets(report.get("keyResults") or [], "No key results were reported."),
        "",
        "## Non-fatal Exceptions",
        *_bullets(report.get("nonFatalExceptions") or [], "No non-fatal exceptions were reported."),
        "",
        "## Follow-ups",
        *_bullets(report.get("followUps") or [], "No follow-up was recommended."),
        "",
        "## Important Artifacts",
    ]
    artifacts = report.get("importantArtifacts") or []
    if artifacts:
        for item in artifacts:
            lines.append(f"- **{item.get('label') or 'Artifact'}**: `{item.get('path') or ''}`")
            if item.get("note"):
                lines.append(f"  - {item.get('note')}")
    else:
        lines.append("- No important artifacts were reported.")
    return "\n".join(lines).rstrip() + "\n"


def generate_completion_report(
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    *,
    artifacts: Sequence[Mapping[str, Any]],
    omissions: Sequence[Mapping[str, Any]],
    reporting_agent_id: str,
    generate: Callable[..., Mapping[str, Any]],
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    agent_id = str(reporting_agent_id or "").strip()
    if not agent_id:
        raise CompletionReportGenerationError(
            "reporting_agent_missing",
            "No reporting Agent is configured",
            recoverable=False,
        )
    prompt = render_completion_report_prompt(
        project,
        occurrence,
        artifacts=artifacts,
        omissions=omissions,
    )
    conversation_id = (
        f"project-completion-report:{str(project.get('id') or '')}:"
        f"{str(occurrence.get('occurrenceId') or '')}"
    )
    try:
        provider_result = generate(
            agent_id=agent_id,
            prompt=prompt,
            conversation_id=conversation_id,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        raise CompletionReportGenerationError(
            "reporting_agent_execution_failed", str(exc), recoverable=True
        ) from exc
    if not provider_result.get("ok"):
        status = str(provider_result.get("status") or "execution_failed").strip().lower()
        code = f"reporting_agent_{status}" if status in {"busy", "timeout"} else "reporting_agent_execution_failed"
        raise CompletionReportGenerationError(
            code,
            str(provider_result.get("error") or status),
            recoverable=status in {"busy", "timeout"},
        )
    reply = str(provider_result.get("reply") or "").strip()
    if not reply:
        raise CompletionReportGenerationError(
            "reporting_agent_empty_reply",
            "Reporting Agent returned an empty reply",
            recoverable=True,
        )
    try:
        parsed = json.loads(reply)
    except json.JSONDecodeError as exc:
        raise CompletionReportGenerationError(
            "reporting_agent_invalid_output",
            "Reporting Agent returned invalid JSON",
            recoverable=True,
        ) from exc
    report = _normalize_report(parsed)
    return {
        "report": report,
        "markdown": render_completion_report_markdown(project, occurrence, report),
        "reportingAgentId": agent_id,
    }
