"""Sanitized query and owner-only manual resend operations for completion reports."""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from .project_completion_reporting import CompletionReportStateError, request_manual_resend
from .project_execution import ServiceResult
from .project_repository import ProjectNotFoundError, ProjectRepository


_SECRET_VALUE_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|webhook)\s*[:=]\s*([^\s,;]+)"
)
_PUBLIC_STATUSES = frozenset({"pending", "delivered", "failed"})


def _safe_error(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    message = _SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", str(value.get("message") or ""))
    result = {
        "code": str(value.get("code") or "completion_report_failed")[:120],
        "message": message[:500],
        "at": str(value.get("at") or "")[:80],
    }
    return result


def _summary(occurrence: Mapping[str, Any]) -> dict[str, Any]:
    status = str(occurrence.get("visibleStatus") or "pending")
    if status not in _PUBLIC_STATUSES:
        status = "pending"
    return {
        "occurrenceId": str(occurrence.get("occurrenceId") or ""),
        "version": int(occurrence.get("version") or 0),
        "runId": str(occurrence.get("runId") or ""),
        "status": status,
        "completedAt": str(occurrence.get("completedAt") or ""),
        "generatedAt": str(occurrence.get("generatedAt") or ""),
        "deliveredAt": str(occurrence.get("deliveredAt") or ""),
        "reportMarkdownPath": str(occurrence.get("reportMarkdownPath") or ""),
        "attemptCount": max(0, int(occurrence.get("attemptCount") or 0)),
        "nextAttemptAt": str(occurrence.get("nextAttemptAt") or ""),
        "lastError": _safe_error(occurrence.get("lastError")),
        "canResend": occurrence.get("state") == "failed",
    }


def completion_report_summaries(project: Mapping[str, Any]) -> list[dict[str, Any]]:
    orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
    reports = [item for item in orchestration.get("completionReports") or [] if isinstance(item, Mapping)]
    return sorted((_summary(item) for item in reports), key=lambda item: item["version"], reverse=True)


def resend_completion_report(
    project_id: str,
    occurrence_id: str,
    body: Mapping[str, Any] | None,
    *,
    repository: ProjectRepository,
    now: Callable[[], str],
    owner_authorized: bool,
    wake: Callable[[], None],
) -> ServiceResult:
    if not owner_authorized:
        return ServiceResult(403, {
            "ok": False,
            "code": "completion_report_resend_forbidden",
            "error": "Only the project owner can resend a report",
        })
    if body:
        return ServiceResult(400, {
            "ok": False,
            "code": "completion_report_resend_overrides_forbidden",
            "error": "Completion report resend does not accept overrides",
        })
    result: dict[str, Any] = {}

    def mutate(project: dict[str, Any]) -> None:
        occurrence = request_manual_resend(
            project,
            occurrence_id=occurrence_id,
            now=now(),
            owner_authorized=True,
        )
        result["report"] = _summary(occurrence)

    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return ServiceResult(404, {
            "ok": False,
            "code": "project_not_found",
            "error": "Project not found",
        })
    except CompletionReportStateError as exc:
        status = 404 if exc.code == "completion_report_not_found" else 409
        return ServiceResult(status, {"ok": False, "code": exc.code, "error": str(exc)})
    try:
        wake()
    except Exception:
        # The periodic worker remains the durable recovery path.
        pass
    return ServiceResult(200, {"ok": True, "report": result["report"]})
