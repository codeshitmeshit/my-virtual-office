"""Provider-neutral execution contract helpers for Virtual Office workflows."""

from __future__ import annotations

import time
from typing import Any


TERMINAL_HTTP_STATUS = {
    "timeout": 408,
    "bridge_unavailable": 503,
    "provider_unavailable": 503,
    "disabled": 503,
    "busy": 409,
    "needs_human_intervention": 409,
    "invalid_request": 400,
    "not_found": 404,
}


def provider_http_status(result: dict[str, Any]) -> int:
    status = str((result or {}).get("status") or "").lower()
    if (result or {}).get("ok") or status in {"completed", "compacted", "cancelled", "canceled"}:
        return 200
    return TERMINAL_HTTP_STATUS.get(status, 500)


def collect_modified_files(provider_files: Any = None, before: Any = None, after: Any = None) -> list[str]:
    files = set()
    if isinstance(provider_files, (list, tuple, set)):
        files.update(str(item) for item in provider_files if str(item or "").strip())
    if isinstance(before, (list, tuple, set)) and isinstance(after, (list, tuple, set)):
        files.update(str(item) for item in set(after) - set(before) if str(item or "").strip())
    return sorted(files)


def normalize_provider_result(
    provider_kind: str,
    agent: dict[str, Any] | None,
    result: dict[str, Any] | None,
    *,
    conversation_id: str = "",
    thread_id: str = "",
    session_id: str = "",
    turn_id: str = "",
    run_id: str = "",
    modified_files: Any = None,
    default_status: str = "completed",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    agent = agent if isinstance(agent, dict) else {}
    ok = bool(result.get("ok"))
    status = str(result.get("status") or (default_status if ok else "execution_failed"))
    normalized = {
        "ok": ok,
        "status": status,
        "reply": result.get("reply") or "",
        "error": result.get("error"),
        "errorCode": result.get("errorCode"),
        "providerKind": provider_kind,
        "conversationId": conversation_id or result.get("conversationId") or "",
        "threadId": thread_id or result.get("threadId") or "",
        "sessionId": session_id or result.get("sessionId") or "",
        "turnId": turn_id or result.get("turnId") or "",
        "runId": run_id or result.get("runId") or "",
        "tools": result.get("tools") or [],
        "thinking": result.get("thinking") or "",
        "tokenUsage": result.get("tokenUsage") or {},
        "modifiedFiles": collect_modified_files(modified_files if modified_files is not None else result.get("modifiedFiles")),
        "needsHumanIntervention": bool(result.get("needsHumanIntervention") or status == "needs_human_intervention"),
        "durationMs": result.get("durationMs"),
        "mode": result.get("mode", ""),
        "providerPath": result.get("providerPath") or result.get("mode") or "",
        "agent": {
            "id": agent.get("id"),
            "name": agent.get("name"),
            "providerKind": provider_kind,
            "profile": agent.get("profile") or agent.get("providerAgentId") or "",
        },
        "providerMetadata": result.get("providerMetadata") if isinstance(result.get("providerMetadata"), dict) else {},
    }
    if result.get("approval") is not None:
        normalized["approval"] = result.get("approval")
    if extra:
        normalized.update({k: v for k, v in extra.items() if v is not None})
    return normalized


def normalize_approval_record(
    provider_kind: str,
    agent_id: str,
    conversation_id: str,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = record if isinstance(record, dict) else {}
    return {
        "providerKind": provider_kind,
        "agentId": agent_id or record.get("agentId") or "",
        "conversationId": conversation_id or record.get("conversationId") or "",
        "operationId": str(record.get("operationId") or ""),
        "interactionId": str(record.get("interactionId") or record.get("approvalId") or ""),
        "approvalId": str(record.get("approvalId") or record.get("interactionId") or ""),
        "status": str(record.get("status") or "pending"),
        "title": str(record.get("title") or record.get("method") or "Provider approval required"),
        "description": str(record.get("description") or record.get("error") or ""),
        "choices": record.get("choices") if isinstance(record.get("choices"), list) else [],
        "raw": record,
    }


def normalize_active_operation(
    provider_kind: str,
    agent_id: str,
    conversation_id: str,
    *,
    thread_id: str = "",
    session_id: str = "",
    turn_id: str = "",
    run_id: str = "",
    status: str = "running",
    pending: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "providerKind": provider_kind,
        "agentId": agent_id,
        "conversationId": conversation_id,
        "threadId": thread_id,
        "sessionId": session_id,
        "turnId": turn_id,
        "runId": run_id,
        "status": status,
        "pending": pending,
        "startedAt": int(time.time() * 1000),
    }
