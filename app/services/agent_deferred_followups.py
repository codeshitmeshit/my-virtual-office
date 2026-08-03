"""Lightweight watcher for deferred Agent replies."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable, Mapping


Result = dict[str, Any]


def _text(value: Any, limit: int = 0) -> str:
    text = str(value or "").strip()
    return text[:limit] if limit > 0 else text


def _is_feishu_source(source_context: Mapping[str, Any]) -> bool:
    return _text(source_context.get("sourceApp")).lower() == "feishu"


@dataclass
class DeferredAgentFollowupScheduler:
    """Poll for a deferred reply and route it through the injected delivery path."""

    find_reply: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
    deliver_reply: Callable[[Mapping[str, Any], Mapping[str, Any]], Result]
    wait_seconds: int = 3600
    interval_seconds: float = 5.0
    _scheduled: set[str] = field(default_factory=set, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def schedule(self, payload: Mapping[str, Any]) -> Result:
        source_context = payload.get("sourceContext") if isinstance(payload.get("sourceContext"), dict) else {}
        if not _is_feishu_source(source_context):
            return {"ok": True, "status": "not_required", "reason": "non_feishu_source"}
        request_event_id = _text(payload.get("requestEventId"), 128)
        conversation_id = _text(payload.get("conversationId"), 240)
        agent_id = _text(payload.get("agentId"), 160)
        if not request_event_id or not conversation_id or not agent_id:
            return {"ok": False, "status": "invalid_request"}
        source_message_id = _text(source_context.get("sourceMessageId"), 240)
        key = "|".join([source_message_id or request_event_id, conversation_id, agent_id])
        with self._lock:
            if key in self._scheduled:
                return {"ok": True, "status": "already_scheduled"}
            self._scheduled.add(key)
        thread = threading.Thread(target=self._run, args=(key, dict(payload)), daemon=True)
        thread.start()
        return {"ok": True, "status": "scheduled", "key": key}

    def _run(self, key: str, payload: dict[str, Any]) -> None:
        deadline = time.time() + max(1, int(self.wait_seconds or 1))
        try:
            while time.time() < deadline:
                reply_event = self.find_reply(payload)
                if reply_event:
                    self.deliver_reply(payload, reply_event)
                    return
                time.sleep(max(0.2, float(self.interval_seconds or 0.2)))
        finally:
            with self._lock:
                self._scheduled.discard(key)
