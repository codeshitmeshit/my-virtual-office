"""Agent activity orchestration independent from HTTP and the legacy server module."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from .agent_event_repository import AgentEventRepository


SECRET_KEYS = frozenset({
    "authorization", "cookie", "token", "api_key", "apikey", "password",
    "secret", "access_token", "refresh_token",
})
MAX_EVENT_TEXT = 12_000


def sanitize(value: Any, key: str = "") -> Any:
    key_lower = str(key or "").lower().replace("-", "_")
    if any(secret in key_lower for secret in SECRET_KEYS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): sanitize(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value[:200]]
    if isinstance(value, str):
        text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+", r"\1[REDACTED]", value)
        text = re.sub(r"(?i)(https?://[^\s/:]+:)[^@\s]+@", r"\1[REDACTED]@", text)
        return text[:MAX_EVENT_TEXT] + "\n[TRUNCATED]" if len(text) > MAX_EVENT_TEXT else text
    return value


def update_active_from_record(
    active_operations: MutableMapping[Any, dict[str, Any]],
    active_lock: Any,
    agent_id: str,
    conversation_id: str,
    record: Mapping[str, Any],
    *,
    normalize_approval: Callable[[str, str, str, Mapping[str, Any]], dict[str, Any]],
) -> None:
    with active_lock:
        active = active_operations.get((agent_id, conversation_id)) or active_operations.get(agent_id)
        if not active or active.get("conversationId") != conversation_id:
            return
        active["threadId"] = record.get("threadId") or active.get("threadId", "")
        active["turnId"] = record.get("turnId") or active.get("turnId", "")
        active["updatedAt"] = record.get("ts") or int(time.time() * 1000)
        record_type = str(record.get("type") or "").lower()
        record_status = str(record.get("status") or "").lower()
        pending = active.get("pending") if isinstance(active.get("pending"), dict) else None
        interaction_id = str(record.get("interactionId") or record.get("approvalId") or "")
        pending_id = str((pending or {}).get("interactionId") or (pending or {}).get("approvalId") or "")
        terminal_turn = record_type == "turn" and record_status in {
            "completed", "done", "success", "failed", "error", "cancelled", "canceled",
        }
        approval_terminal = (
            record_type in {"interaction", "approval"}
            and record_status in {"resolved", "failed", "cancelled", "canceled", "declined"}
            and (not pending_id or not interaction_id or pending_id == interaction_id)
        )
        if record_type in {"interaction", "approval"} and record_status == "pending":
            if record_type == "interaction":
                active["pending"] = normalize_approval("codex", agent_id, conversation_id, record)
                active["pending"]["raw"] = dict(record)
            else:
                active["pending"] = dict(record)
            active["status"] = "pending"
        elif terminal_turn or approval_terminal:
            active["pending"] = None
            active["status"] = record_status or active.get("status", "running")
        elif pending:
            active["status"] = "resolving" if str(pending.get("status") or "").lower() == "resolving" else "pending"
        else:
            active["status"] = record_status or active.get("status", "running")


def mark_approval_resolving(active_operations, active_lock, agent_id, conversation_id, approval_id) -> bool:
    with active_lock:
        active = active_operations.get((agent_id, conversation_id)) or active_operations.get(agent_id)
        if not active or active.get("conversationId") != conversation_id:
            return False
        pending = active.get("pending") if isinstance(active.get("pending"), dict) else None
        if not pending:
            return False
        pending_id = str(pending.get("approvalId") or pending.get("interactionId") or "")
        if approval_id and pending_id and approval_id != pending_id:
            raw = pending.get("raw") if isinstance(pending.get("raw"), dict) else {}
            if str(raw.get("threadId") or "") != str(active.get("threadId") or ""):
                return False
        pending["status"] = "resolving"
        active["status"] = "resolving"
        active["updatedAt"] = int(time.time() * 1000)
        return True


def append(
    repository: AgentEventRepository,
    activity_lock: Any,
    agent_id: str,
    conversation_id: str,
    event: Mapping[str, Any],
    *,
    preserve_sequence: bool = False,
) -> dict[str, Any]:
    with activity_lock:
        last_sequence = repository.max_sequence(agent_id, conversation_id)
        provider_sequence = int(event.get("providerSequence") or event.get("sequence") or 0)
        record = sanitize({
            **event,
            "providerSequence": provider_sequence,
            "sequence": int(event.get("sequence") or 0) if preserve_sequence else last_sequence + 1,
            "agentId": agent_id,
            "conversationId": conversation_id,
        })
        repository.append(record)
    return record


def list_activity(repository, activity_lock, fast_path, agent_id, conversation_id, *, after=0):
    with activity_lock:
        matching = repository.list_scope(agent_id, conversation_id, after=after)
    if fast_path.settings.enabled:
        live = fast_path.live_events(agent_id, conversation_id, after=after)
        by_identity = {(event.get("id") or "", int(event.get("sequence") or 0)): event for event in matching}
        for event in live:
            by_identity[(event.get("id") or "", int(event.get("sequence") or 0))] = event
        matching = list(by_identity.values())
    return sorted(matching, key=lambda event: int(event.get("sequence") or 0))


def get_active(active_operations, active_lock, agent_id, conversation_id="", thread_id=""):
    with active_lock:
        active = active_operations.get((agent_id, conversation_id)) if conversation_id else None
        if active:
            return dict(active)
        candidates = [
            value for key, value in active_operations.items()
            if isinstance(key, tuple) and key[0] == agent_id and isinstance(value, dict)
        ]
        legacy = active_operations.get(agent_id)
        if isinstance(legacy, dict):
            candidates.append(legacy)
        if conversation_id:
            candidates = [item for item in candidates if item.get("conversationId") == conversation_id]
        if thread_id:
            candidates = [item for item in candidates if item.get("threadId") == thread_id]
        active = max(candidates, key=lambda item: int(item.get("updatedAt") or 0), default=None)
        return dict(active) if active else None
