"""Deterministic notification-to-chat fallback for project completion reports."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .project_completion_report_content import render_content_markdown
from .project_completion_report_delivery import CompletionReportDeliveryError


UNKNOWN_PRIMARY_STATUSES = frozenset({"network_error", "timeout", "delivery_timeout"})


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def render_chat_fallback_markdown(
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    report: Mapping[str, Any],
) -> str:
    del occurrence
    return render_content_markdown(project, report, title_level=2).rstrip()[:12000]


def _delivery_error_result(exc: CompletionReportDeliveryError) -> dict[str, Any]:
    return {
        "ok": False,
        "status": exc.code,
        "error": _text(exc, 1000),
        "recoverable": bool(exc.recoverable),
    }


def _audit(
    callback: Callable[[Mapping[str, Any]], None],
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    primary: Mapping[str, Any],
    *,
    decision: str,
    fallback: Mapping[str, Any] | None = None,
    final_channel: str = "",
    message_id: str = "",
) -> None:
    fallback = fallback or {}
    event = {
        "projectId": _text(project.get("id"), 160),
        "occurrenceId": _text(occurrence.get("occurrenceId"), 200),
        "primaryStatus": _text(primary.get("status"), 120),
        "primaryCode": _text(primary.get("code"), 120),
        "fallbackDecision": decision,
        "fallbackStatus": _text(fallback.get("status"), 120),
        "fallbackCode": _text(fallback.get("code"), 120),
        "finalChannel": final_channel,
        "messageId": _text(message_id, 300),
    }
    try:
        callback(event)
    except Exception:
        pass


def deliver_with_chat_fallback(
    project: Mapping[str, Any],
    occurrence: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    primary_delivery: Callable[[], Mapping[str, Any]],
    chat_delivery: Callable[[str, str], Mapping[str, Any]],
    owner_chat_id: str,
    audit: Callable[[Mapping[str, Any]], None],
) -> dict[str, Any]:
    try:
        primary = dict(primary_delivery() or {})
    except CompletionReportDeliveryError as exc:
        primary = _delivery_error_result(exc)
    if primary.get("ok"):
        result = {**primary, "deliveryChannel": "notification_app"}
        _audit(
            audit, project, occurrence, primary,
            decision="not_needed",
            final_channel="notification_app",
            message_id=_text(primary.get("messageId"), 300),
        )
        return result
    if _text(primary.get("status")) in UNKNOWN_PRIMARY_STATUSES:
        _audit(audit, project, occurrence, primary, decision="suppressed_unknown")
        return primary
    chat_id = _text(owner_chat_id, 300)
    if not chat_id:
        fallback = {
            "ok": False,
            "status": "chat_fallback_destination_missing",
            "error": "A fixed owner chat is required for completion report fallback",
        }
        _audit(audit, project, occurrence, primary, decision="unavailable", fallback=fallback)
        return {**fallback, "primaryStatus": _text(primary.get("status"))}
    try:
        fallback = dict(chat_delivery(chat_id, render_chat_fallback_markdown(project, occurrence, report)) or {})
    except Exception as exc:
        fallback = {"ok": False, "status": "chat_fallback_error", "error": _text(exc, 1000)}
    if fallback.get("ok"):
        result = {
            **fallback,
            "deliveryChannel": "chat_app_fallback",
            "primaryStatus": _text(primary.get("status")),
        }
        _audit(
            audit, project, occurrence, primary,
            decision="attempted",
            fallback=fallback,
            final_channel="chat_app_fallback",
            message_id=_text(fallback.get("messageId"), 300),
        )
        return result
    _audit(audit, project, occurrence, primary, decision="attempted", fallback=fallback)
    return {
        **fallback,
        "ok": False,
        "primaryStatus": _text(primary.get("status")),
        "fallbackStatus": _text(fallback.get("status")),
    }
