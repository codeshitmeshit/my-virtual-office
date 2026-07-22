"""Provider-neutral, read-only conversation timeline contracts and policies.

This module owns canonical scope, lifecycle, visibility, and reasoning state. It
intentionally has no dependency on the legacy HTTP/server composition root.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


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


class ConversationTimelineService:
    """Pure canonical policies used by source and transport adapters."""

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
