"""Bounded redacted Meeting notification intents and delivery markers."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping, MutableMapping


_SECRET = re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+")
_ABSOLUTE_PATH = re.compile(r"/(?:Users|home|tmp|var|private|opt|etc)/[^\s,;]*")
_SENSITIVE_KEY = re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key|credential)")


def redact_text(value: Any, limit: int = 2000) -> str:
    text = _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", str(value or ""))
    text = _ABSOLUTE_PATH.sub("[REDACTED_PATH]", text)
    return text[:limit]


def sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 5: return "[TRUNCATED]"
    if isinstance(value, str): return redact_text(value)
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:50]:
            name = str(key)[:80]
            if name.lower() in {"raw", "rawbody", "transcript"}: continue
            result[name] = "[REDACTED]" if _SENSITIVE_KEY.search(name) else sanitize(item, depth=depth + 1)
        return result
    if isinstance(value, tuple): return tuple(sanitize(item, depth=depth + 1) for item in value[:50])
    if isinstance(value, list): return [sanitize(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, (int, float, bool)) or value is None: return value
    return redact_text(value)


def request_intent(request: Mapping[str, Any], state: str, *, summary: str, actions: list[dict[str, Any]], details: Any) -> dict[str, Any]:
    proposal = request.get("originalProposal") if isinstance(request.get("originalProposal"), Mapping) else {}
    source = request.get("source") if isinstance(request.get("source"), Mapping) else {}
    prefixes = {"pending": "会议申请待处理", "approved": "会议申请已同意", "rejected": "会议申请已拒绝", "processing": "会议申请处理中", "cancelled": "会议申请已取消", "expired": "会议申请已过期", "no_longer_actionable": "会议申请不再可处理"}
    return sanitize({
        "id": f"meeting-request:{request.get('id')}:{state}", "type": "application_form",
        "title": f"{prefixes.get(state, '会议申请通知')}: {proposal.get('topic') or request.get('id')}",
        "summary": summary or proposal.get("purpose") or proposal.get("goal") or "会议申请状态已更新。",
        "state": state, "multi_participant": False,
        "related": {"type": "meeting_request", "id": request.get("id") or "", "title": proposal.get("topic") or source.get("taskTitle") or "Meeting request"},
        "details": details, "actions": actions, "target": "feishu-meeting-request",
    })


def failure_intent(meeting: Mapping[str, Any], failure: Mapping[str, Any], open_url: str) -> dict[str, Any]:
    meeting_id = str(meeting.get("id") or "")
    sequence = failure.get("failedAtSequence") or meeting.get("lastEventSequence") or failure.get("reason") or meeting.get("stage") or "failed"
    return sanitize({
        "id": f"meeting-failure:{meeting_id}:{sequence}", "type": "error",
        "title": f"AI 会议失败: {meeting.get('topic') or meeting_id}",
        "summary": failure.get("error") or meeting.get("error") or "AI meeting failed and needs user attention.",
        "error_variant": "user_facing", "related": {"type": "meeting", "id": meeting_id, "title": meeting.get("topic") or "AI meeting"},
        "details": [("会议", meeting.get("topic") or meeting_id or "-"), ("阶段", meeting.get("stage") or "-"), ("主持人", failure.get("moderator") or meeting.get("moderator") or "-"), ("原因", failure.get("reason") or "meeting_failed")],
        "actions": [{"category": "jump", "text": "打开会议", "url": open_url}],
        "target": "feishu-meeting-failure",
    })


def stage(data: MutableMapping[str, Any], entity_kind: str, entity_id: str, intent: Mapping[str, Any], now: str) -> dict[str, Any]:
    container = data.get("requests", {}).get(entity_id) if entity_kind == "request" else data.get("meetings", {}).get(entity_id)
    if not isinstance(container, MutableMapping): return {"ok": False, "status": "entity_not_found"}
    key = str(intent.get("id") or "")
    markers = container.setdefault("notificationIntents", {})
    existing = markers.get(key)
    if isinstance(existing, Mapping) and existing.get("deliveryStatus") == "sent":
        return {"ok": True, "status": "skipped_duplicate", "dedupeKey": key}
    attempts = int(existing.get("attempts") or 0) if isinstance(existing, Mapping) else 0
    markers[key] = {"intent": copy.deepcopy(dict(intent)), "deliveryStatus": "pending", "attempts": attempts + 1, "stagedAt": now}
    if len(markers) > 100:
        for old_key in list(markers)[:-100]: markers.pop(old_key, None)
    return {"ok": True, "status": "staged", "dedupeKey": key, "intent": copy.deepcopy(dict(intent))}


def mark(data: MutableMapping[str, Any], entity_kind: str, entity_id: str, key: str, result: Mapping[str, Any], now: str) -> None:
    container = data.get("requests", {}).get(entity_id) if entity_kind == "request" else data.get("meetings", {}).get(entity_id)
    marker = (container.get("notificationIntents") or {}).get(key) if isinstance(container, Mapping) else None
    if not isinstance(marker, MutableMapping): return
    status = str(result.get("status") or result.get("code") or "")
    delivered = bool(result.get("ok")) and not status.startswith("skipped_") and status not in {"delivery_failed", "failed"}
    marker["deliveryStatus"] = "sent" if delivered else "failed"
    marker["lastAttemptAt"] = now
    marker["lastError"] = "" if delivered else redact_text(result.get("error") or status or "delivery_failed", 500)
    marker["recordId"] = str(((result.get("record") or {}).get("id")) or "")
