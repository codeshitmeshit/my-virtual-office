"""Send short Feishu progress notices back to the originating chat."""

from __future__ import annotations

from typing import Any, Callable


MAX_NOTICE_TEXT = 1000


def _clean(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def send_original_channel_notice(
    body: dict[str, Any],
    *,
    command_sender: Callable[[str, dict[str, Any]], dict[str, Any]],
    record_event: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a user-visible progress notice to the Feishu source channel."""
    data = body if isinstance(body, dict) else {}
    source_app = _clean(data.get("sourceApp") or data.get("app") or "feishu", 80).lower()
    chat_id = _clean(data.get("feishuChatId") or data.get("chatId") or data.get("to"))
    text = _clean(data.get("text") or data.get("message"), MAX_NOTICE_TEXT)
    source_surface = _clean(data.get("sourceSurface") or data.get("surface") or "feishu-dm", 80).lower()
    chat_type = _clean(data.get("chatType"), 40).lower()
    source_message_id = _clean(data.get("sourceMessageId") or data.get("messageId"))
    reply_in_thread = bool(data.get("replyInThread"))
    is_group = source_surface == "feishu-group" or chat_type == "group"

    if source_app != "feishu":
        return {"ok": False, "status": "unsupported_source_app", "error": "sourceApp must be feishu", "_status": 400}
    if not chat_id:
        return {"ok": False, "status": "missing_feishu_chat_id", "error": "feishuChatId is required", "_status": 400}
    if not text:
        return {"ok": False, "status": "missing_text", "error": "text is required", "_status": 400}
    if is_group and not source_message_id:
        return {"ok": False, "status": "missing_source_message_id", "error": "sourceMessageId is required for group replies", "_status": 400}

    payload = {
        "to": chat_id,
        "content": text,
        "contentType": "text",
    }
    operation = "send"
    if is_group:
        operation = "reply"
        payload["messageId"] = source_message_id
        payload["replyInThread"] = reply_in_thread

    result = command_sender(operation, payload)
    result = result if isinstance(result, dict) else {"ok": False, "status": "invalid_command_response"}
    if record_event:
        record = {
            "event": "original_channel_notice",
            "channel": "feishu",
            "sourceApp": "feishu",
            "sourceSurface": "feishu-group" if is_group else "feishu-dm",
            "sourceMessageId": source_message_id,
            "conversationId": _clean(data.get("conversationId"), 300),
            "feishuChatId": chat_id,
            "chatType": "group" if is_group else "p2p",
            "text": text,
            "sendResult": result,
        }
        if data.get("representativeAgentId"):
            record["representativeAgentId"] = _clean(data.get("representativeAgentId"), 120)
        result = {**result, "record": record_event(record)}
    return result


__all__ = ["send_original_channel_notice"]
