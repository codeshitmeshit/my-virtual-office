"""Sanitized audit-event construction for project authoring workflows."""

from __future__ import annotations

import re
from typing import Any


CONTEXT_FIELDS = frozenset({
    "requestId", "projectId", "maintenanceRequestId", "recurrenceId",
    "templateId", "taskId", "code", "error", "changedFields",
})
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|token|secret|password|cookie|api[_-]?key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")


def sanitize_audit_text(value: Any, *, limit: int = 1000) -> str:
    text = str(value or "")
    text = _NAMED_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    return text if len(text) <= limit else text[:limit].rstrip() + "...[truncated]"


def build_audit_event(
    action: str,
    actor: str,
    source: str,
    at: str,
    result: str,
    **context: Any,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "action": sanitize_audit_text(action, limit=100),
        "actor": sanitize_audit_text(actor, limit=256),
        "source": sanitize_audit_text(source, limit=100),
        "at": str(at or ""),
        "result": sanitize_audit_text(result, limit=100),
    }
    for key in CONTEXT_FIELDS:
        value = context.get(key)
        if value in (None, "", []):
            continue
        if key == "changedFields":
            event[key] = [sanitize_audit_text(item, limit=100) for item in value[:50]] if isinstance(value, list) else []
        else:
            event[key] = sanitize_audit_text(value, limit=1000)
    return event
