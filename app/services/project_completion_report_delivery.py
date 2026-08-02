"""Deliver structured project reports through the Feishu notification app."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .project_completion_report_content import (
    report_conclusions,
    report_organizational_advice,
    report_summary,
    report_title,
)


REQUIRED_DESTINATION_FIELDS = ("appId", "appSecret", "receiveIdType", "receiveId")


class CompletionReportDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str, *, recoverable: bool) -> None:
        self.code = code
        self.recoverable = recoverable
        super().__init__(message)


def _joined(items: Any, empty: str, *, limit: int = 500) -> str:
    values = [str(item).strip() for item in (items or []) if str(item).strip()]
    return ("\n".join(f"• {item}" for item in values) or empty)[:limit]


def deliver_completion_report(
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    app_config: Mapping[str, Any],
    send_notification: Callable[..., dict[str, Any]],
    project_url: str,
) -> dict[str, Any]:
    """Build one bounded owner-facing card and force notification-app delivery."""

    config = dict(app_config or {})
    missing = [field for field in REQUIRED_DESTINATION_FIELDS if not str(config.get(field) or "").strip()]
    if missing:
        raise CompletionReportDeliveryError(
            "project_owner_feishu_destination_missing",
            "The project owner has no configured Feishu notification destination",
            recoverable=False,
        )
    summary = report_summary(report)[:1800] or "暂无结论摘要。"
    conclusions = _joined(report_conclusions(report), "无", limit=245)
    advice = report_organizational_advice(report)
    if advice:
        conclusions = f"{conclusions}\n\n---\n\n{_joined(advice, '无', limit=245)}"
    details: list[tuple[str, str]] = [("核心结论", conclusions)]
    intent = {
        "id": (
            f"project-completion-report:{str(project.get('id') or '')}:"
            f"{str(occurrence.get('occurrenceId') or '')}"
        ),
        "type": "notification",
        "title": report_title(project, report),
        "summary": summary,
        "related": {
            "type": "project",
            "id": str(project.get("id") or ""),
            "title": str(project.get("title") or "Project"),
        },
        "details": details[:20],
        "actions": [{"category": "jump", "text": "打开项目报告", "url": project_url}],
        "target": "feishu-project-completion-report",
        "audit": {
            "attemptId": str(occurrence.get("occurrenceId") or ""),
            "application": "project-completion-report",
            "operation": "send",
        },
    }
    return send_notification(intent, app_config=config, allow_webhook=False)
