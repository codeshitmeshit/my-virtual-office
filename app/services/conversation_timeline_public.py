"""Allowlisted, bounded public serialization for conversation timelines."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from .provider_events import SECRET_VALUE, sanitize_payload


MAX_VISIBLE_TEXT = 128 * 1024
PUBLIC_TIMELINE_FIELDS = frozenset(
    {
        "id", "version", "providerKind", "conversationId", "providerRunId",
        "itemKind", "role", "text", "thinking", "status", "reasoningStatus",
        "epochMs", "timestamp", "ts", "sequence", "source", "from",
        "fromAgentId", "to", "toAgentId", "media", "attachments", "tools",
        "reasoningTokens", "approval", "idempotencyKey", "error", "durable",
        "identityFields",
    }
)
PUBLIC_MEDIA_FIELDS = frozenset(
    {"type", "url", "path", "filePath", "href", "mimeType", "media_type", "contentType", "name", "filename", "alt", "fileKey"}
)
PUBLIC_TOOL_FIELDS = frozenset(
    {
        "id", "toolCallId", "name", "canonicalName", "arguments", "input",
        "args", "args_preview", "result", "output", "error", "status",
    }
)
PUBLIC_APPROVAL_FIELDS = frozenset(
    {
        "id", "approvalId", "approval_id", "interactionId", "operationId",
        "type", "title", "summary", "description", "command", "status",
        "choices", "questions", "pending_count",
    }
)
_ABSOLUTE_PATH = re.compile(r"^(?:/|[A-Za-z]:\\)")


def _visible_text(value: Any) -> str:
    text = str(value or "")
    if SECRET_VALUE.search(text):
        return "[redacted]"
    if len(text) > MAX_VISIBLE_TEXT:
        return text[: MAX_VISIBLE_TEXT - 1] + "…"
    return text


def _structured(value: Any) -> Any:
    cleaned = sanitize_payload(copy.deepcopy(value))
    return cleaned


def _public_objects(values: Any, allowed: frozenset[str], *, suppress_paths: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(values, (list, tuple)):
        return result
    for value in values[:200]:
        if not isinstance(value, Mapping):
            continue
        projected = {}
        for key in allowed:
            if key not in value:
                continue
            item = value[key]
            if suppress_paths and key in {"path", "filePath"} and _ABSOLUTE_PATH.match(str(item or "")):
                continue
            cleaned = _structured(item)
            if cleaned is not None:
                projected[key] = cleaned
        result.append(projected)
    return result


def sanitize_public_timeline_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return one copied public record with no native or sensitive side fields."""

    record = value if isinstance(value, Mapping) else {}
    result: dict[str, Any] = {}
    for key in PUBLIC_TIMELINE_FIELDS:
        if key not in record:
            continue
        item = record[key]
        if key in {"text", "thinking", "error"}:
            result[key] = _visible_text(item)
        elif key == "tools":
            result[key] = _public_objects(item, PUBLIC_TOOL_FIELDS)
        elif key in {"media", "attachments"}:
            result[key] = _public_objects(item, PUBLIC_MEDIA_FIELDS, suppress_paths=True)
        elif key == "approval":
            if isinstance(item, Mapping):
                result[key] = {
                    field: cleaned
                    for field in PUBLIC_APPROVAL_FIELDS
                    if field in item and (cleaned := _structured(item[field])) is not None
                }
            else:
                result[key] = None
        else:
            cleaned = _structured(item)
            result[key] = cleaned
    return result
