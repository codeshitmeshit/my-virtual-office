"""Provider-neutral, read-only conversation timeline contracts and policies.

This module owns canonical scope, lifecycle, visibility, and reasoning state. It
intentionally has no dependency on the legacy HTTP/server composition root.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from .conversation_timeline_public import sanitize_public_timeline_record

MAX_AGENT_ID = 160
MAX_PROFILE = 160
MAX_CONVERSATION_ID = 256
MAX_SESSION_KEY = 512
MAX_PAGE_SIZE = 50
MAX_SOURCE_CANDIDATES = 1_000
MAX_REASONING_STATES = 1_000
MAX_REASONING_EVENT_IDS = 4_000
ITEM_KINDS = frozenset({"message", "reasoning", "tool", "approval", "run"})
ITEM_ROLES = frozenset({"user", "assistant", "system", "tool"})
ITEM_KIND_ORDER = {"message": 0, "reasoning": 1, "tool": 2, "approval": 3, "run": 4}

PROVIDER_ALIASES = {
    "codex": "codex",
    "claude": "claude-code",
    "claude_code": "claude-code",
    "claudecode": "claude-code",
    "claude-code": "claude-code",
    "hermes": "hermes",
    "gateway": "openclaw",
    "open-claw": "openclaw",
    "openclaw": "openclaw",
}

LIFECYCLE_ALIASES = {
    "pending": "queued",
    "queued": "queued",
    "starting": "running",
    "started": "running",
    "active": "running",
    "in_progress": "running",
    "in-progress": "running",
    "live": "running",
    "processing": "running",
    "running": "running",
    "streaming": "running",
    "complete": "done",
    "completed": "done",
    "done": "done",
    "finished": "done",
    "succeeded": "done",
    "success": "done",
    "error": "failed",
    "execution_failed": "failed",
    "failed": "failed",
    "aborted": "cancelled",
    "canceled": "cancelled",
    "cancelled": "cancelled",
}
CANONICAL_LIFECYCLES = frozenset({"queued", "running", "done", "failed", "cancelled"})
TERMINAL_LIFECYCLES = frozenset({"done", "failed", "cancelled"})

GENERIC_REASONING_PLACEHOLDERS = frozenset(
    {
        "queued",
        "starting",
        "running",
        "completed",
        "complete",
        "done",
        "success",
        "failed",
        "error",
        "execution_failed",
        "cancelled",
        "canceled",
    }
)
PROVIDER_REASONING_PLACEHOLDERS = {
    "claude-code": frozenset({"claude code completed.", "claude code completed"}),
    "codex": frozenset(
        {
            "codex run 已完成",
            "codex run 未完成",
            "codex run 正在执行",
            "codex run 正在取消",
            "waiting for codex run events.",
        }
    ),
}


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _scope_value(value: Any, limit: int, label: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) > limit:
        raise ValueError(f"timeline {label} is too long")
    return normalized


def canonical_provider_kind(value: Any) -> str:
    provider = str(value or "").strip().lower()
    try:
        return PROVIDER_ALIASES[provider]
    except KeyError as exc:
        raise ValueError("unsupported conversation timeline provider") from exc


def normalize_lifecycle(value: Any, *, default: str = "done") -> str:
    fallback = str(default or "").strip().lower()
    if fallback not in CANONICAL_LIFECYCLES:
        raise ValueError("invalid lifecycle default")
    return LIFECYCLE_ALIASES.get(str(value or "").strip().lower(), fallback)


def visible_reasoning(provider_kind: Any, record: Mapping[str, Any] | None) -> str:
    """Return only Provider-supplied, non-placeholder reasoning text."""

    provider = canonical_provider_kind(provider_kind)
    value = record if isinstance(record, Mapping) else {}
    thinking = str(value.get("thinking") or value.get("text") or value.get("output") or "").strip()
    if not thinking:
        return ""
    lowered = thinking.lower()
    raw_status = str(value.get("status") or "").strip().lower()
    if lowered == raw_status or lowered in GENERIC_REASONING_PLACEHOLDERS:
        return ""
    if lowered in PROVIDER_REASONING_PLACEHOLDERS.get(provider, frozenset()):
        return ""
    return thinking


@dataclass(frozen=True)
class TimelineScope:
    provider_kind: str
    agent_id: str
    profile: str
    conversation_id: str
    session_key: str = ""

    @classmethod
    def create(
        cls,
        provider_kind: Any,
        agent_id: Any,
        profile: Any,
        conversation_id: Any,
        session_key: Any = "",
    ) -> "TimelineScope":
        provider = canonical_provider_kind(provider_kind)
        agent = _scope_value(agent_id, MAX_AGENT_ID, "agent id")
        normalized_profile = _scope_value(profile, MAX_PROFILE, "profile")
        conversation = _scope_value(conversation_id, MAX_CONVERSATION_ID, "conversation id")
        session = _scope_value(session_key, MAX_SESSION_KEY, "session key")
        if not agent:
            raise ValueError("timeline agent id is required")
        if not conversation and not session:
            raise ValueError("timeline conversation id or session key is required")
        return cls(provider, agent, normalized_profile, conversation, session)

    @property
    def conversation_ref(self) -> str:
        return self.conversation_id or self.session_key

    def key(self) -> tuple[str, str, str, str, str]:
        return (self.provider_kind, self.agent_id, self.profile, self.conversation_id, self.session_key)


@dataclass(frozen=True)
class TimelineQuery:
    limit: int = MAX_PAGE_SIZE
    before: tuple[int, str] | None = None
    include_live: bool = True
    candidate_limit: int = MAX_SOURCE_CANDIDATES

    def __post_init__(self) -> None:
        try:
            limit = int(self.limit)
            candidate_limit = int(self.candidate_limit)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("timeline limits must be integers") from exc
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError("timeline limit must be between 1 and 50")
        if not 1 <= candidate_limit <= MAX_SOURCE_CANDIDATES:
            raise ValueError("timeline candidate limit must be between 1 and 1000")
        if not isinstance(self.include_live, bool):
            raise ValueError("timeline include_live must be boolean")
        object.__setattr__(self, "limit", limit)
        object.__setattr__(self, "candidate_limit", candidate_limit)
        if self.before is not None:
            if not isinstance(self.before, tuple) or len(self.before) != 2:
                raise ValueError("timeline cursor must be an epoch/id tuple")
            try:
                epoch_ms = int(self.before[0])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("invalid timeline cursor") from exc
            item_id = str(self.before[1] or "").strip()
            if epoch_ms < 0 or not item_id:
                raise ValueError("invalid timeline cursor")
            object.__setattr__(self, "before", (epoch_ms, item_id))


@dataclass(frozen=True)
class TimelineItem:
    id: str
    version: str
    provider_kind: str
    conversation_id: str
    item_kind: str
    role: str = "assistant"
    text: str = ""
    thinking: str = ""
    status: str = "done"
    epoch_ms: int = 0
    sequence: int = 0
    source: str = ""
    tools: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    provider_run_id: str = ""
    from_name: str = ""
    from_agent_id: str = ""
    to_name: str = ""
    to_agent_id: str = ""
    media: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    attachments: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    reasoning_tokens: int = 0
    approval: Mapping[str, Any] | None = None
    idempotency_key: str = ""
    identity_key: str = ""
    identity_strength: int = 0
    durable: bool = True
    source_priority: int = 0

    def __post_init__(self) -> None:
        if not str(self.id or "") or not str(self.version or ""):
            raise ValueError("timeline item id and version are required")
        object.__setattr__(self, "provider_kind", canonical_provider_kind(self.provider_kind))
        if not str(self.conversation_id or ""):
            raise ValueError("timeline item conversation id is required")
        if self.item_kind not in ITEM_KINDS:
            raise ValueError("unsupported timeline item kind")
        if self.role not in ITEM_ROLES:
            raise ValueError("unsupported timeline item role")
        object.__setattr__(self, "status", normalize_lifecycle(self.status))
        object.__setattr__(self, "epoch_ms", _safe_nonnegative_int(self.epoch_ms))
        object.__setattr__(self, "sequence", _safe_nonnegative_int(self.sequence))
        object.__setattr__(self, "tools", tuple(self.tools or ()))
        object.__setattr__(self, "media", tuple(self.media or ()))
        object.__setattr__(self, "attachments", tuple(self.attachments or ()))
        object.__setattr__(self, "reasoning_tokens", _safe_nonnegative_int(self.reasoning_tokens))
        object.__setattr__(self, "identity_strength", max(0, min(3, _safe_nonnegative_int(self.identity_strength))))
        object.__setattr__(self, "source_priority", _safe_nonnegative_int(self.source_priority))

    def to_public_dict(self) -> dict[str, Any]:
        return sanitize_public_timeline_record(
            {
                "id": self.id,
                "version": self.version,
                "providerKind": self.provider_kind,
                "conversationId": self.conversation_id,
                "providerRunId": self.provider_run_id,
                "itemKind": self.item_kind,
                "role": self.role,
                "text": self.text,
                "thinking": self.thinking,
                "status": self.status,
                "epochMs": self.epoch_ms,
                "sequence": self.sequence,
                "source": self.source,
                "from": self.from_name,
                "fromAgentId": self.from_agent_id,
                "to": self.to_name,
                "toAgentId": self.to_agent_id,
                "media": list(self.media),
                "attachments": list(self.attachments),
                "tools": list(self.tools),
                "reasoningTokens": self.reasoning_tokens,
                "approval": self.approval,
                "idempotencyKey": self.idempotency_key,
            }
        )


@dataclass(frozen=True)
class TimelinePage:
    items: tuple[TimelineItem, ...]
    next_cursor: str = ""
    has_more: bool = False
    session: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        items = tuple(self.items or ())
        if len(items) > MAX_PAGE_SIZE or any(not isinstance(item, TimelineItem) for item in items):
            raise ValueError("timeline page items are invalid")
        object.__setattr__(self, "items", items)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "messages": [item.to_public_dict() for item in self.items],
            "nextCursor": self.next_cursor,
            "hasMore": self.has_more,
            "session": copy.deepcopy(dict(self.session or {})),
        }


@dataclass(frozen=True)
class ReasoningSnapshot:
    key: str
    text: str
    status: str
    epoch_ms: int
    sequence: int
    source: str


class _ReasoningState:
    def __init__(self, event_limit: int) -> None:
        self.text = ""
        self.pending_boundary = False
        self.status = "running"
        self.epoch_ms = 0
        self.sequence = 0
        self.source = ""
        self._event_limit = event_limit
        self._event_order: deque[str] = deque()
        self._event_ids: set[str] = set()

    def remember(self, event_id: str) -> bool:
        if not event_id:
            return True
        if event_id in self._event_ids:
            return False
        self._event_ids.add(event_id)
        self._event_order.append(event_id)
        while len(self._event_order) > self._event_limit:
            self._event_ids.discard(self._event_order.popleft())
        return True


class ReasoningAccumulator:
    """Bounded delta/replace/boundary state shared by all Provider projections."""

    def __init__(self, *, max_states: int = MAX_REASONING_STATES, max_event_ids: int = MAX_REASONING_EVENT_IDS) -> None:
        try:
            normalized_states = int(max_states)
            normalized_event_ids = int(max_event_ids)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("reasoning bounds must be integers") from exc
        if normalized_states < 1 or normalized_event_ids < 1:
            raise ValueError("reasoning bounds must be positive")
        self._max_states = min(normalized_states, MAX_REASONING_STATES)
        self._max_event_ids = min(normalized_event_ids, MAX_REASONING_EVENT_IDS)
        self._states: dict[str, _ReasoningState] = {}
        self._order: deque[str] = deque()

    @staticmethod
    def event_key(event: Mapping[str, Any]) -> str:
        turn = _bounded(event.get("operationId") or event.get("turnId") or event.get("threadId") or "turn", 256)
        item = _bounded(event.get("itemId") or "reasoning", 256)
        return f"{turn}:{item}"

    def apply(self, provider_kind: Any, event: Any) -> ReasoningSnapshot | None:
        if not isinstance(event, Mapping):
            return None
        try:
            provider = canonical_provider_kind(provider_kind)
        except ValueError:
            return None
        key = self.event_key(event)
        state = self._states.get(key)
        if state is None:
            state = _ReasoningState(self._max_event_ids)
            self._states[key] = state
            self._order.append(key)
            while len(self._order) > self._max_states:
                self._states.pop(self._order.popleft(), None)

        if not state.remember(_bounded(event.get("id"), 256)):
            return self._snapshot(key, state) if state.text else None

        incoming = visible_reasoning(provider, event)
        if bool(event.get("replace")) and incoming:
            state.text = incoming
            state.pending_boundary = False
        else:
            if bool(event.get("boundary")) and state.text:
                state.pending_boundary = True
            if incoming:
                if state.pending_boundary and not state.text.endswith("\n\n"):
                    state.text += "\n\n"
                state.text += incoming
                state.pending_boundary = False

        raw_status = event.get("status")
        state.status = normalize_lifecycle(raw_status, default=state.status)
        state.epoch_ms = max(state.epoch_ms, _safe_nonnegative_int(event.get("epochMs") or event.get("ts")))
        state.sequence = max(state.sequence, _safe_nonnegative_int(event.get("sequence")))
        state.source = _bounded(event.get("source") or provider, 80)
        return self._snapshot(key, state) if state.text else None

    def snapshots(self) -> tuple[ReasoningSnapshot, ...]:
        return tuple(
            self._snapshot(key, self._states[key])
            for key in self._order
            if key in self._states and self._states[key].text
        )

    @staticmethod
    def _snapshot(key: str, state: _ReasoningState) -> ReasoningSnapshot:
        return ReasoningSnapshot(key, state.text, state.status, state.epoch_ms, state.sequence, state.source)


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _stable_hash(value: Any, *, length: int = 32) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _record_value(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and value != "":
            return value
    return ""


def _record_role(record: Mapping[str, Any]) -> str:
    role = str(record.get("role") or "").strip().lower()
    if role in ITEM_ROLES:
        return role
    direction = str(record.get("direction") or "").strip().lower()
    from_ref = record.get("from") if isinstance(record.get("from"), Mapping) else {}
    from_id = str(record.get("fromAgentId") or from_ref.get("id") or "")
    from_kind = str(from_ref.get("providerKind") or "").lower()
    return "user" if direction == "request" or from_id == "user" or from_kind == "human" else "assistant"


def _record_party(record: Mapping[str, Any], name: str) -> tuple[str, str]:
    ref = record.get(name)
    if isinstance(ref, Mapping):
        return str(ref.get("name") or ref.get("id") or ""), str(ref.get("id") or "")
    identifier = str(record.get(f"{name}AgentId") or "")
    return str(ref or identifier), identifier


def _record_item_kind(record: Mapping[str, Any]) -> str:
    item_kind = str(record.get("itemKind") or record.get("kind") or "").strip().lower()
    if item_kind in ITEM_KINDS:
        return item_kind
    if record.get("approval"):
        return "approval"
    if record.get("toolCallId") or (record.get("tools") and not record.get("text") and not record.get("thinking")):
        return "tool"
    if record.get("thinking") and not record.get("text"):
        return "reasoning"
    return "message"


def _assert_record_scope(scope: TimelineScope, record: Mapping[str, Any]) -> None:
    raw_provider = record.get("providerKind")
    if raw_provider and canonical_provider_kind(raw_provider) != scope.provider_kind:
        raise ValueError("timeline record provider is outside the requested scope")
    raw_conversation = str(record.get("conversationId") or record.get("sessionKey") or "")
    if raw_conversation and raw_conversation != scope.conversation_ref:
        raise ValueError("timeline record conversation is outside the requested scope")
    raw_agent = str(record.get("agentId") or "")
    if raw_agent and raw_agent != scope.agent_id:
        raise ValueError("timeline record agent is outside the requested scope")


def _identity_for(
    scope: TimelineScope,
    record: Mapping[str, Any],
    *,
    item_kind: str,
    role: str,
    source: str,
    ordinal: int,
    epoch_ms: int,
    sender_id: str,
    text: str,
    thinking: str,
) -> tuple[str, int]:
    native_id = _record_value(record, "messageId", "eventId", "toolCallId", "approvalId", "commEventId", "id")
    scope_key = scope.key()
    if native_id:
        return "native:" + _stable_hash((scope_key, item_kind, str(native_id))), 3
    run_id = _record_value(record, "providerRunId", "runId", "operationId")
    turn_id = _record_value(record, "turnId", "threadId")
    item_id = _record_value(record, "itemId")
    if run_id and (turn_id or item_id):
        return "run:" + _stable_hash((scope_key, item_kind, str(run_id), str(turn_id), str(item_id))), 2
    content_signature = _stable_hash((text[:16_384], thinking[:16_384]), length=24)
    fallback = (scope_key, item_kind, role, sender_id, source, epoch_ms, content_signature, max(0, int(ordinal)))
    return "fallback:" + _stable_hash(fallback), 1


def _render_version(values: Mapping[str, Any]) -> str:
    return _stable_hash(values)


def _timeline_sort_key(item: TimelineItem) -> tuple[Any, ...]:
    if item.sequence:
        return (0, item.sequence, item.epoch_ms, ITEM_KIND_ORDER[item.item_kind], item.id)
    return (1, item.epoch_ms, ITEM_KIND_ORDER[item.item_kind], item.id)


def _item_render_values(item: TimelineItem) -> dict[str, Any]:
    return {
        "role": item.role,
        "itemKind": item.item_kind,
        "text": item.text,
        "thinking": item.thinking,
        "status": item.status,
        "tools": item.tools,
        "media": item.media,
        "attachments": item.attachments,
        "approval": item.approval,
        "from": item.from_name,
        "fromAgentId": item.from_agent_id,
        "to": item.to_name,
        "toAgentId": item.to_agent_id,
        "reasoningTokens": item.reasoning_tokens,
        "source": item.source,
        "idempotencyKey": item.idempotency_key,
    }


def encode_timeline_cursor(epoch_ms: Any, item_id: Any) -> str:
    normalized_id = str(item_id or "")
    if not normalized_id or len(normalized_id) > 512:
        raise ValueError("invalid timeline cursor id")
    payload = json.dumps(
        {"v": 1, "ts": _safe_nonnegative_int(epoch_ms), "id": normalized_id},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_timeline_cursor(cursor: Any) -> tuple[int, str]:
    raw = str(cursor or "").strip()
    if not raw or len(raw) > 1_024:
        raise ValueError("invalid timeline cursor")
    try:
        padding = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode((raw + padding).encode("ascii")).decode("utf-8"))
        epoch_ms = int(payload.get("ts"))
        item_id = str(payload.get("id") or "")
        if not isinstance(payload, dict) or payload.get("v") != 1 or epoch_ms < 0 or not item_id or len(item_id) > 512:
            raise ValueError
        return epoch_ms, item_id
    except Exception as exc:
        raise ValueError("invalid timeline cursor") from exc


class ConversationTimelineService:
    """Pure canonical policies used by source and transport adapters."""

    def item_from_record(
        self,
        scope: TimelineScope,
        record: Mapping[str, Any],
        *,
        source: str,
        ordinal: int = 0,
        durable: bool = True,
    ) -> TimelineItem:
        if not isinstance(record, Mapping):
            raise ValueError("timeline record must be a mapping")
        _assert_record_scope(scope, record)
        role = _record_role(record)
        item_kind = _record_item_kind(record)
        epoch_ms = _safe_nonnegative_int(_record_value(record, "epochMs", "ts", "timestamp"))
        sequence = _safe_nonnegative_int(_record_value(record, "sequence", "providerSequence", "seq"))
        text = str(record.get("text") or "")
        reasoning_record = {
            "thinking": record.get("thinking") or (text if item_kind == "reasoning" else ""),
            "status": record.get("status"),
        }
        thinking = visible_reasoning(scope.provider_kind, reasoning_record)
        if item_kind == "reasoning":
            text = ""
        from_name, from_agent_id = _record_party(record, "from")
        to_name, to_agent_id = _record_party(record, "to")
        normalized_source = _bounded(source or record.get("source") or scope.provider_kind, 80)
        identity_key, identity_strength = _identity_for(
            scope,
            record,
            item_kind=item_kind,
            role=role,
            source=normalized_source,
            ordinal=ordinal,
            epoch_ms=epoch_ms,
            sender_id=from_agent_id,
            text=text,
            thinking=thinking,
        )
        item_id = "tl-" + _stable_hash(identity_key, length=24)
        status = normalize_lifecycle(record.get("status"), default="done" if durable else "running")
        tools = tuple(copy.deepcopy(item) for item in (record.get("tools") or ()) if isinstance(item, Mapping))
        media = tuple(copy.deepcopy(item) for item in (record.get("media") or ()) if isinstance(item, Mapping))
        attachments = tuple(copy.deepcopy(item) for item in (record.get("attachments") or ()) if isinstance(item, Mapping))
        approval = copy.deepcopy(record.get("approval")) if isinstance(record.get("approval"), Mapping) else None
        values = {
            "role": role,
            "itemKind": item_kind,
            "text": text,
            "thinking": thinking,
            "status": status,
            "tools": tools,
            "media": media,
            "attachments": attachments,
            "approval": approval,
            "from": from_name,
            "fromAgentId": from_agent_id,
            "to": to_name,
            "toAgentId": to_agent_id,
            "reasoningTokens": _safe_nonnegative_int(record.get("reasoningTokens")),
            "source": normalized_source,
            "idempotencyKey": str(record.get("idempotencyKey") or ""),
        }
        return TimelineItem(
            id=item_id,
            version=_render_version(values),
            provider_kind=scope.provider_kind,
            conversation_id=scope.conversation_ref,
            provider_run_id=str(_record_value(record, "providerRunId", "runId", "operationId")),
            item_kind=item_kind,
            role=role,
            text=text,
            thinking=thinking,
            status=status,
            epoch_ms=epoch_ms,
            sequence=sequence,
            source=normalized_source,
            tools=tools,
            from_name=from_name,
            from_agent_id=from_agent_id,
            to_name=to_name,
            to_agent_id=to_agent_id,
            media=media,
            attachments=attachments,
            reasoning_tokens=values["reasoningTokens"],
            approval=approval,
            idempotency_key=values["idempotencyKey"],
            identity_key=identity_key,
            identity_strength=identity_strength,
            durable=bool(durable),
            source_priority=_safe_nonnegative_int(record.get("sourcePriority")),
        )

    def normalize_records(
        self,
        scope: TimelineScope,
        records: Iterable[Mapping[str, Any]],
        *,
        source: str,
        durable: bool = True,
        candidate_limit: int = MAX_SOURCE_CANDIDATES,
    ) -> tuple[TimelineItem, ...]:
        try:
            limit = max(1, min(int(candidate_limit), MAX_SOURCE_CANDIDATES))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("timeline candidate limit must be an integer") from exc
        items = []
        for ordinal, record in enumerate(records or ()):
            if ordinal >= limit:
                break
            if not isinstance(record, Mapping):
                continue
            items.append(self.item_from_record(scope, record, source=source, ordinal=ordinal, durable=durable))
        return tuple(items)

    def merge_items(self, scope: TimelineScope, sources: Iterable[Iterable[TimelineItem]]) -> tuple[TimelineItem, ...]:
        merged: dict[str, TimelineItem] = {}
        for source in sources or ():
            for item in source or ():
                if not isinstance(item, TimelineItem):
                    continue
                if item.provider_kind != scope.provider_kind or item.conversation_id != scope.conversation_ref:
                    raise ValueError("timeline item is outside the requested scope")
                key = item.identity_key or item.id
                existing = merged.get(key)
                merged[key] = item if existing is None else self._settle_pair(existing, item)
        return tuple(sorted(merged.values(), key=_timeline_sort_key))

    def page_items(
        self,
        items: Iterable[TimelineItem],
        query: TimelineQuery,
        *,
        session: Mapping[str, Any] | None = None,
    ) -> TimelinePage:
        ordered = tuple(sorted((item for item in items if isinstance(item, TimelineItem)), key=_timeline_sort_key))
        if query.before:
            boundary_index = next(
                (index for index, item in enumerate(ordered) if (item.epoch_ms, item.id) == query.before),
                None,
            )
            if boundary_index is not None:
                ordered = ordered[:boundary_index]
            else:
                ordered = tuple(item for item in ordered if (item.epoch_ms, item.id) < query.before)
        selected = ordered[-query.limit :]
        has_more = len(ordered) > len(selected)
        next_cursor = encode_timeline_cursor(selected[0].epoch_ms, selected[0].id) if selected and has_more else ""
        return TimelinePage(selected, next_cursor, has_more, copy.deepcopy(dict(session or {})))

    def read(
        self,
        scope: TimelineScope,
        query: TimelineQuery,
        sources: Iterable[Iterable[TimelineItem]],
        *,
        session: Mapping[str, Any] | None = None,
    ) -> TimelinePage:
        return self.page_items(self.merge_items(scope, sources), query, session=session)

    def merge_compatibility_records(
        self,
        scope: TimelineScope,
        source_records: Iterable[Iterable[Mapping[str, Any]]],
    ) -> tuple[dict[str, Any], ...]:
        """Select legacy DTOs using canonical scoped identity without reshaping them."""

        selected: dict[str, tuple[int, Mapping[str, Any]]] = {}
        ordinal = 0
        for records in source_records or ():
            for raw in records or ():
                if not isinstance(raw, Mapping):
                    continue
                _assert_record_scope(scope, raw)
                legacy_id = str(raw.get("id") or "")
                if legacy_id:
                    key = "compat:" + _stable_hash((scope.key(), legacy_id))
                else:
                    source = str(raw.get("source") or scope.provider_kind)
                    role = _record_role(raw)
                    item_kind = _record_item_kind(raw)
                    epoch_ms = _safe_nonnegative_int(_record_value(raw, "epochMs", "ts", "timestamp"))
                    _from_name, from_agent_id = _record_party(raw, "from")
                    key, _strength = _identity_for(
                        scope,
                        raw,
                        item_kind=item_kind,
                        role=role,
                        source=_bounded(source, 80),
                        ordinal=ordinal,
                        epoch_ms=epoch_ms,
                        sender_id=from_agent_id,
                        text=str(raw.get("text") or ""),
                        thinking=visible_reasoning(scope.provider_kind, raw),
                    )
                ordinal += 1
                priority = _safe_nonnegative_int(raw.get("sourcePriority"))
                existing = selected.get(key)
                if existing is None or priority > existing[0]:
                    selected[key] = (priority, raw)
        ordered = sorted(
            selected.values(),
            key=lambda pair: (_safe_nonnegative_int(pair[1].get("epochMs")), str(pair[1].get("id") or "")),
        )
        return tuple(copy.deepcopy(dict(payload)) for _, payload in ordered)

    @staticmethod
    def _settle_pair(left: TimelineItem, right: TimelineItem) -> TimelineItem:
        def rank(item: TimelineItem) -> tuple[Any, ...]:
            richness = bool(item.text) + bool(item.thinking) + bool(item.tools) + bool(item.approval)
            return (
                item.source_priority,
                int(item.durable),
                int(item.status in TERMINAL_LIFECYCLES),
                item.sequence,
                item.epoch_ms,
                item.identity_strength,
                richness,
                item.version,
            )

        winner, other = (right, left) if rank(right) > rank(left) else (left, right)
        enriched = replace(
            winner,
            text=winner.text or other.text,
            thinking=winner.thinking or other.thinking,
            tools=winner.tools or other.tools,
            media=winner.media or other.media,
            attachments=winner.attachments or other.attachments,
            approval=winner.approval or other.approval,
            from_name=winner.from_name or other.from_name,
            from_agent_id=winner.from_agent_id or other.from_agent_id,
            to_name=winner.to_name or other.to_name,
            to_agent_id=winner.to_agent_id or other.to_agent_id,
            provider_run_id=winner.provider_run_id or other.provider_run_id,
            idempotency_key=winner.idempotency_key or other.idempotency_key,
            identity_strength=max(winner.identity_strength, other.identity_strength),
            durable=winner.durable or other.durable,
        )
        return replace(enriched, version=_render_version(_item_render_values(enriched)))

    def accumulate_reasoning(self, provider_kind: Any, events: Iterable[Any]) -> tuple[ReasoningSnapshot, ...]:
        accumulator = ReasoningAccumulator()
        for event in events or ():
            accumulator.apply(provider_kind, event)
        return accumulator.snapshots()

    @staticmethod
    def normalize_status(value: Any, *, default: str = "done") -> str:
        return normalize_lifecycle(value, default=default)

    @staticmethod
    def visible_reasoning(provider_kind: Any, record: Mapping[str, Any] | None) -> str:
        return visible_reasoning(provider_kind, record)
