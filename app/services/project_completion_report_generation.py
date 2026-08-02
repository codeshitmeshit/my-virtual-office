"""Generate and validate structured human-readable completion reports."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

from .project_completion_report_content import render_content_markdown
from .project_completion_report_prompt import render_completion_report_prompt


REPORT_KEYS = frozenset({
    "title",
    "summary",
    "conclusions",
    "organizationalAdvice",
})


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
    report = {
        "title": _text(value.get("title"), 300),
        "summary": _text(value.get("summary"), 5000),
        "conclusions": _text_list(value.get("conclusions")),
        "organizationalAdvice": _text_list(value.get("organizationalAdvice")),
    }
    if not all(report[field] for field in REPORT_KEYS):
        raise CompletionReportGenerationError(
            "reporting_agent_invalid_output",
            "Completion report title, summary, conclusions, and organizational advice must be non-empty",
            recoverable=True,
        )
    return report


def render_completion_report_markdown(
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    report: Mapping[str, Any],
) -> str:
    del occurrence
    return render_content_markdown(project, report)


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
    if not any(
        artifact.get("inline") is True and str(artifact.get("content") or "").strip()
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    ):
        raise CompletionReportGenerationError(
            "final_report_content_missing",
            "No readable final artifact content is available for completion reporting",
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
