"""Host adapters for notification-topic conversations.

The orchestration stays in ``feishu_notification_topics``; this module adapts
existing notification audit, communication history, and resource functions.
"""

from __future__ import annotations

from collections import deque
import hashlib
import json
import os
from typing import Any, Callable, Iterable, Mapping

from services.feishu_notification_topics import NotificationRoot, TopicMessage


LONG_RUNNING_CLASSIFICATIONS = frozenset({"long_running_diversion"})


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _audit_paths(status_dir: str, backups: int = 3) -> list[str]:
    base = os.path.join(status_dir, "feishu-notification-records.jsonl")
    return [base, *(f"{base}.{index}" for index in range(1, max(0, backups) + 1))]


def _iter_recent_jsonl(paths: Iterable[str], *, max_records: int = 5_000) -> Iterable[dict[str, Any]]:
    remaining = max(1, int(max_records))
    for path in paths:
        if remaining <= 0:
            break
        try:
            with open(path, "r", encoding="utf-8") as stream:
                lines = deque(stream, maxlen=remaining)
        except OSError:
            continue
        for line in reversed(lines):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value
                remaining -= 1
                if remaining <= 0:
                    return


def notification_root_from_record(record: Mapping[str, Any], expected_message_id: str = "") -> NotificationRoot | None:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    send_result = metadata.get("feishuSendResult") if isinstance(metadata.get("feishuSendResult"), Mapping) else {}
    message_id = _bounded(record.get("messageId") or metadata.get("messageId") or send_result.get("messageId"), 300)
    delivered = record.get("ok")
    if delivered is None:
        delivered = send_result.get("ok") if "ok" in send_result else str(record.get("deliveryStatus") or metadata.get("deliveryStatus") or "").lower() == "sent"
    if not message_id or (expected_message_id and message_id != expected_message_id) or not delivered:
        return None
    context = record.get("topicContext") if isinstance(record.get("topicContext"), Mapping) else (
        metadata.get("topicContext") if isinstance(metadata.get("topicContext"), Mapping) else {}
    )
    classification = _bounded(context.get("classification"), 80)
    if classification not in LONG_RUNNING_CLASSIFICATIONS:
        return None
    return NotificationRoot(
        message_id=message_id,
        classification=classification,
        conversation_id=_bounded(context.get("conversationId"), 240),
        agent_id=_bounded(context.get("agentId"), 160),
        title=_bounded(context.get("title") or record.get("title"), 8_000),
        summary=_bounded(context.get("summary"), 8_000),
        request_text=_bounded(context.get("requestText"), 8_000),
        response_text=_bounded(context.get("responseText"), 8_000),
        goal=_bounded(context.get("goal"), 8_000),
        request_id=_bounded(context.get("requestId"), 240),
        response_id=_bounded(context.get("responseId"), 240),
    )


def lookup_notification_root(
    status_dir: str,
    message_id: str,
    communication_loader: Callable[..., list[dict[str, Any]]] | None = None,
) -> NotificationRoot | None:
    target = _bounded(message_id, 300)
    if not target:
        return None
    for record in _iter_recent_jsonl(_audit_paths(status_dir)):
        if record.get("messageId") != target:
            continue
        root = notification_root_from_record(record, target)
        if root and root.eligible:
            return root
    if communication_loader:
        try:
            records = communication_loader(limit=1_000)
        except TypeError:
            records = communication_loader(1_000)
        for record in reversed(records if isinstance(records, list) else []):
            root = notification_root_from_record(record, target) if isinstance(record, Mapping) else None
            if root and root.eligible:
                return root
    return None


def load_origin_history(
    root: NotificationRoot,
    load_communication: Callable[..., list[dict[str, Any]]],
    *,
    limit: int = 1_000,
) -> list[dict[str, Any]]:
    try:
        records = load_communication(limit=limit)
    except TypeError:
        records = load_communication(limit)
    result = []
    for item in records if isinstance(records, list) else []:
        if not isinstance(item, Mapping) or str(item.get("conversationId") or "") != root.conversation_id:
            continue
        direction = str(item.get("direction") or "").lower()
        role = "user" if direction == "request" else ("assistant" if direction == "reply" else "")
        text = _bounded(item.get("text") or item.get("message") or item.get("reply"), 8_000)
        if role and text:
            result.append({"role": role, "text": text})
    return result[-80:]


def load_topic_resources(
    message: TopicMessage,
    *,
    download: Callable[..., Mapping[str, Any]],
    validate: Callable[..., list[dict[str, Any]]],
    app_config: Mapping[str, Any],
    status_dir: str,
) -> list[dict[str, Any]]:
    downloaded = []
    for resource in message.resources:
        resource_type = _bounded(resource.get("resource_type") or resource.get("type") or "file", 40).lower()
        key = _bounded(resource.get("file_key") or resource.get("image_key") or resource.get("fileKey") or resource.get("imageKey"), 500)
        if not key:
            continue
        result = download(
            message.message_id,
            key,
            resource_type="image" if resource_type == "image" else "file",
            app_config=dict(app_config),
            status_dir=status_dir,
        )
        if not isinstance(result, Mapping) or not result.get("ok"):
            raise ValueError(f"Feishu {resource_type} download failed")
        downloaded.append(dict(result))
    allowed_root = os.path.join(status_dir, "feishu-chat-attachments")
    return validate(downloaded, allowed_roots=(allowed_root,))


def safe_preflight_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    """Defensive public projection for production read-only preflight."""
    root_hash = _bounded(result.get("rootHash"), 32)
    classification = _bounded(result.get("classification"), 80)
    fields = result.get("fields") if isinstance(result.get("fields"), Mapping) else {}
    return {
        "ok": bool(result.get("ok")),
        "rootHash": root_hash or hashlib.sha256(b"missing").hexdigest()[:16],
        "classification": classification or "unverified",
        "fields": {key: bool(fields.get(key)) for key in ("messageId", "conversationId", "agentId", "request", "response")},
    }
