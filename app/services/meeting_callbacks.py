"""Trusted Meeting callback commands and persistent replay outcomes."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, MutableMapping


ALLOWED_ACTIONS = frozenset({"confirm_meeting_request", "reject_meeting_request"})
PROCESSING_LEASE_SECONDS = 900


@dataclass(frozen=True)
class TrustedCallbackContext:
    event_id: str
    message_id: str
    chat_id: str
    actor_id: str


@dataclass(frozen=True)
class CallbackPorts:
    confirm_request: Callable[[str, Mapping[str, Any]], dict[str, Any]]
    reject_request: Callable[[str, Mapping[str, Any]], dict[str, Any]]
    run_meeting: Callable[[str, Mapping[str, Any]], dict[str, Any]]


def execute(action: str, request_id: str, actor_id: str, ports: CallbackPorts) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS: return {"handled": False}
    if not request_id: return {"handled": True, "ok": False, "businessStatus": "missing_request_id"}
    if action == "reject_meeting_request":
        result = ports.reject_request(request_id, {"rejectedBy": actor_id, "reason": "Rejected from Feishu"})
        return {
            "handled": True, "ok": bool(result.get("ok")),
            "businessStatus": "rejected" if result.get("ok") else str(result.get("code") or result.get("status") or "reject_failed"),
            "businessError": "" if result.get("ok") else str(result.get("error") or "Meeting request cannot be rejected"),
            "idempotent": bool(result.get("idempotent")),
        }
    result = ports.confirm_request(request_id, {"confirmedBy": actor_id, "idempotencyKey": f"feishu-confirm:{request_id}"})
    if not result.get("ok"):
        return {"handled": True, "ok": False, "businessStatus": str(result.get("code") or result.get("status") or "confirm_failed"), "businessError": str(result.get("error") or "Meeting request cannot be confirmed")}
    meeting_id = str(result.get("meetingId") or ""); run_summary: dict[str, Any] = {}
    if meeting_id:
        run_result = ports.run_meeting(meeting_id, {"action": "start", "actorId": actor_id, "actorType": "user"})
        run_summary = {
            "attempted": True, "ok": bool(run_result.get("ok")) if isinstance(run_result, Mapping) else False,
            "stage": ((run_result or {}).get("meeting") or {}).get("stage") if isinstance(run_result, Mapping) else "",
            "error": (run_result or {}).get("error") if isinstance(run_result, Mapping) else "Meeting start failed",
        }
    if run_summary.get("attempted") and not run_summary.get("ok"):
        return {"handled": True, "ok": True, "businessStatus": "confirmed_start_failed", "businessError": str(run_summary.get("error") or "Meeting start failed"), "idempotent": bool(result.get("idempotent")), "meetingId": meeting_id, "run": run_summary}
    return {"handled": True, "ok": True, "businessStatus": "confirmed_started" if run_summary.get("attempted") else "confirmed", "idempotent": bool(result.get("idempotent")), "meetingId": meeting_id, "run": run_summary}


def callback_key(action: str, request_id: str, context: TrustedCallbackContext) -> str:
    event = context.event_id or context.message_id
    return f"feishu:{event}:{action}:{request_id}" if event else f"feishu:{action}:{request_id}:{context.actor_id}"


def _processing_claim_is_stale(record: Mapping[str, Any], now: str) -> bool:
    try:
        started_text = str(record.get("startedAt") or "")
        current_text = str(now or "")
        if started_text.endswith("Z"):
            started_text = started_text[:-1] + "+00:00"
        if current_text.endswith("Z"):
            current_text = current_text[:-1] + "+00:00"
        started = datetime.fromisoformat(started_text)
        current = datetime.fromisoformat(current_text)
        return (current - started).total_seconds() >= PROCESSING_LEASE_SECONDS
    except (TypeError, ValueError):
        return False


def begin(
    data: MutableMapping[str, Any], action: str, request_id: str, context: TrustedCallbackContext, now: str,
    claim_token: str, claimed_linkage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        return {"handled": False}
    if not request_id:
        return {"handled": True, "ok": False, "businessStatus": "missing_request_id", "_status": 400}
    request = data.get("requests", {}).get(request_id)
    if not isinstance(request, Mapping):
        return {"handled": True, "ok": False, "businessStatus": "request_not_found", "_status": 404}
    source = request.get("source") if isinstance(request.get("source"), Mapping) else {}
    conversion = request.get("conversion") if isinstance(request.get("conversion"), Mapping) else {}
    claimed = claimed_linkage or {}
    expected = {
        "project_id": str(source.get("projectId") or ""),
        "task_id": str(source.get("taskId") or ""),
        "meeting_id": str(conversion.get("meetingId") or ""),
    }
    for field, expected_value in expected.items():
        camel = field.split("_")[0] + "".join(part.title() for part in field.split("_")[1:])
        supplied = str(claimed.get(field) or claimed.get(camel) or "")
        if supplied and supplied != expected_value:
            return {"handled": True, "ok": False, "businessStatus": "callback_linkage_invalid", "_status": 403}
    key = callback_key(action, request_id, context)
    callbacks = data.setdefault("idempotency", {}).setdefault("callbacks", {})
    existing = callbacks.get(key)
    if isinstance(existing, Mapping):
        if existing.get("status") == "completed" and isinstance(existing.get("response"), Mapping):
            return {"handled": True, "ok": True, "replay": True, "key": key, "response": copy.deepcopy(existing["response"])}
        if existing.get("status") == "processing" and not _processing_claim_is_stale(existing, now):
            return {"handled": True, "ok": True, "replay": True, "inProgress": True, "key": key}
    callbacks[key] = {
        "status": "processing", "action": action, "requestId": request_id,
        "actorId": context.actor_id, "messageId": context.message_id, "chatId": context.chat_id,
        "startedAt": now, "claimToken": claim_token,
    }
    return {"handled": True, "ok": True, "claimed": True, "key": key, "claimToken": claim_token}


def _bounded_text(value: Any, limit: int = 500) -> str:
    return str(value or "")[:limit]


def complete(
    data: MutableMapping[str, Any], key: str, claim_token: str, response: Mapping[str, Any], now: str,
) -> dict[str, Any]:
    callbacks = data.setdefault("idempotency", {}).setdefault("callbacks", {})
    record = callbacks.get(key)
    if not isinstance(record, MutableMapping):
        return {"ok": False, "error": "Callback claim not found", "_status": 409}
    if record.get("status") != "processing" or record.get("claimToken") != claim_token:
        return {"ok": True, "stale": True}
    outcome = response.get("outcome") if isinstance(response.get("outcome"), Mapping) else {}
    toast = response.get("toast") if isinstance(response.get("toast"), Mapping) else {}
    safe_response = {
        "ok": bool(response.get("ok")),
        "toast": {"type": _bounded_text(toast.get("type"), 40), "content": _bounded_text(toast.get("content"), 500)},
        "outcome": {
            key: copy.deepcopy(value)
            for key, value in outcome.items()
            if key in {"handled", "ok", "businessStatus", "idempotent", "meetingId", "run"}
        },
    }
    if isinstance(safe_response["outcome"].get("run"), Mapping):
        run = safe_response["outcome"]["run"]
        safe_response["outcome"]["run"] = {
            "attempted": bool(run.get("attempted")), "ok": bool(run.get("ok")),
            "stage": _bounded_text(run.get("stage"), 80), "error": _bounded_text(run.get("error"), 300),
        }
    record.update({"status": "completed", "completedAt": now, "response": safe_response})
    if len(callbacks) > 1000:
        for old_key in list(callbacks)[:-1000]: callbacks.pop(old_key, None)
    return copy.deepcopy(safe_response)
