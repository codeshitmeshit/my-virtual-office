"""Deliver structured project reports through the Feishu notification app."""

from __future__ import annotations

from typing import Any, Callable, Mapping


REQUIRED_DESTINATION_FIELDS = ("appId", "appSecret", "receiveIdType", "receiveId")


class CompletionReportDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str, *, recoverable: bool) -> None:
        self.code = code
        self.recoverable = recoverable
        super().__init__(message)


def _joined(items: Any, empty: str, *, limit: int = 500) -> str:
    values = [str(item).strip() for item in (items or []) if str(item).strip()]
    return ("\n".join(f"• {item}" for item in values) or empty)[:limit]


def _artifact_details(items: Any) -> list[tuple[str, str]]:
    details = []
    for item in (items or [])[:10]:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "Artifact").strip()
        path = str(item.get("path") or "").strip()
        note = str(item.get("note") or "").strip()
        value = " — ".join(part for part in (path, note) if part)[:500]
        if value:
            details.append(("重要产物", f"{label}: {value}"[:500]))
    return details


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
    goal = str(report.get("goal") or "").strip()
    conclusion = str(report.get("conclusion") or "").strip()
    summary = "\n".join(part for part in (goal, conclusion) if part)[:1800] or "项目已完成。"
    details: list[tuple[str, str]] = [
        ("执行版本", f"v{occurrence.get('version') or 1}"),
        ("关键结果", _joined(report.get("keyResults"), "无")),
        ("非致命异常", _joined(report.get("nonFatalExceptions"), "无")),
        ("后续建议", _joined(report.get("followUps"), "无")),
    ]
    details.extend(_artifact_details(report.get("importantArtifacts")))
    intent = {
        "id": (
            f"project-completion-report:{str(project.get('id') or '')}:"
            f"{str(occurrence.get('occurrenceId') or '')}"
        ),
        "type": "notification",
        "title": f"项目执行完成：{str(project.get('title') or project.get('id') or 'Project')}",
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
