"""Scoped Provider conversation/history coordination over persistence ports."""

from __future__ import annotations

import copy
from contextlib import contextmanager
import os
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


MAX_MESSAGES = 500
MAX_CONTEXT_CHARS = 120_000
MAX_ATTACHMENTS = 20
MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024
MAX_SCOPED_CONVERSATIONS = 4_096


@dataclass(frozen=True)
class ConversationKey:
    provider_kind: str
    agent_id: str
    profile: str
    conversation_id: str = ""

    def normalized(self) -> "ConversationKey":
        provider = str(self.provider_kind or "").strip().lower()[:80]
        agent = str(self.agent_id or "").strip()[:160]
        profile = str(self.profile or "").strip()[:160]
        conversation = str(self.conversation_id or "").strip()[:240]
        if not provider or not agent or not profile:
            raise ValueError("provider kind, agent id, and profile are required")
        return ConversationKey(provider, agent, profile, conversation)


@dataclass(frozen=True)
class ConversationToken:
    key: ConversationKey
    generation: str
    version: int


@dataclass(frozen=True)
class ConversationSnapshot:
    token: ConversationToken
    messages: list[dict[str, Any]]
    native_id: str
    state: dict[str, Any]


@dataclass(frozen=True)
class ConversationCommit:
    applied: bool
    stale: bool
    snapshot: ConversationSnapshot


class ConversationStatePort(Protocol):
    def load(self, key: ConversationKey) -> Mapping[str, Any] | list[Any] | None: ...
    def save(self, key: ConversationKey, state: Mapping[str, Any]) -> None: ...


class QueuedConversationPort(Protocol):
    """Provider adapter boundary for existing queued conversation semantics."""

    def deliver(
        self,
        key: ConversationKey,
        native_id: str,
        message: str,
        attachments: list[dict[str, Any]],
    ) -> str: ...

    def control(self, key: ConversationKey, native_id: str, action: str) -> Mapping[str, Any]: ...


class CallableConversationStatePort:
    def __init__(self, load: Callable[[ConversationKey], Any], save: Callable[[ConversationKey, Mapping[str, Any]], None]) -> None:
        self._load = load
        self._save = save

    def load(self, key: ConversationKey):
        return self._load(key)

    def save(self, key: ConversationKey, state: Mapping[str, Any]) -> None:
        self._save(key, state)


class CallableQueuedConversationPort:
    def __init__(
        self,
        deliver: Callable[[ConversationKey, str, str, list[dict[str, Any]]], str],
        control: Callable[[ConversationKey, str, str], Mapping[str, Any]],
    ) -> None:
        self._deliver = deliver
        self._control = control

    def deliver(self, key: ConversationKey, native_id: str, message: str, attachments: list[dict[str, Any]]) -> str:
        return self._deliver(key, native_id, message, copy.deepcopy(attachments))

    def control(self, key: ConversationKey, native_id: str, action: str) -> Mapping[str, Any]:
        return self._control(key, native_id, action)


@dataclass
class _KeyState:
    lock: threading.RLock
    generation: str
    version: int = 0
    active: int = 0
    last_used_ns: int = 0


class ProviderConversationService:
    def __init__(self, *, id_factory: Callable[[], str] | None = None, max_scopes: int = MAX_SCOPED_CONVERSATIONS) -> None:
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._max_scopes = max(1, int(max_scopes))
        self._states: dict[ConversationKey, _KeyState] = {}
        self._states_lock = threading.Lock()

    def _owner(self, key: ConversationKey) -> tuple[ConversationKey, _KeyState]:
        key = key.normalized()
        with self._states_lock:
            owner = self._states.get(key)
            if owner is None:
                owner = _KeyState(threading.RLock(), self._id_factory(), 0, 0, time.monotonic_ns())
                self._states[key] = owner
            owner.active += 1
            owner.last_used_ns = time.monotonic_ns()
            self._prune_locked(exclude=key)
            return key, owner

    def _prune_locked(self, *, exclude: ConversationKey | None = None) -> None:
        excess = len(self._states) - self._max_scopes
        if excess <= 0:
            return
        candidates = sorted(
            ((state.last_used_ns, key) for key, state in self._states.items() if key != exclude and state.active == 0),
            key=lambda item: item[0],
        )
        for _last_used, key in candidates[:excess]:
            self._states.pop(key, None)

    def _release(self, key: ConversationKey, owner: _KeyState) -> None:
        with self._states_lock:
            current = self._states.get(key)
            if current is owner:
                owner.active = max(0, owner.active - 1)
                owner.last_used_ns = time.monotonic_ns()
            self._prune_locked()

    @contextmanager
    def _owned(self, key: ConversationKey):
        normalized, owner = self._owner(key)
        try:
            yield normalized, owner
        finally:
            self._release(normalized, owner)

    @staticmethod
    def _normalize_state(raw: Mapping[str, Any] | list[Any] | None, key: ConversationKey) -> dict[str, Any]:
        if isinstance(raw, list):
            state: dict[str, Any] = {"messages": raw}
        elif isinstance(raw, Mapping):
            state = copy.deepcopy(dict(raw))
        else:
            state = {}
        messages = state.get("messages") if isinstance(state.get("messages"), list) else []
        state["messages"] = [copy.deepcopy(item) for item in messages if isinstance(item, dict)][-MAX_MESSAGES:]
        state.setdefault("profile", key.profile)
        if key.conversation_id:
            state.setdefault("conversationId", key.conversation_id)
        return state

    @staticmethod
    def _native_id(state: Mapping[str, Any]) -> str:
        value = state.get("nativeId") or state.get("sessionId") or state.get("threadId") or state.get("session_id") or ""
        return str(value).strip()[:240]

    @staticmethod
    def _snapshot(key: ConversationKey, owner: _KeyState, state: dict[str, Any]) -> ConversationSnapshot:
        return ConversationSnapshot(
            ConversationToken(key, owner.generation, owner.version),
            copy.deepcopy(state.get("messages") or []),
            ProviderConversationService._native_id(state),
            copy.deepcopy(state),
        )

    def read(self, key: ConversationKey, port: ConversationStatePort) -> ConversationSnapshot:
        with self._owned(key) as (key, owner):
            with owner.lock:
                state = self._normalize_state(port.load(key), key)
                return self._snapshot(key, owner, state)

    def overwrite(
        self,
        key: ConversationKey,
        port: ConversationStatePort,
        *,
        messages: list[dict[str, Any]] | None = None,
        native_id: str | None = None,
        updates: Mapping[str, Any] | None = None,
    ) -> ConversationCommit:
        with self._owned(key) as (key, owner):
            with owner.lock:
                state = self._normalize_state(port.load(key), key)
                self._merge(state, messages=messages, native_id=native_id, updates=updates)
                port.save(key, state)
                owner.version += 1
                return ConversationCommit(True, False, self._snapshot(key, owner, state))

    def replace(self, key: ConversationKey, port: ConversationStatePort, state: Mapping[str, Any] | list[Any]) -> ConversationCommit:
        with self._owned(key) as (key, owner):
            with owner.lock:
                normalized = self._normalize_state(state, key)
                port.save(key, normalized)
                owner.version += 1
                return ConversationCommit(True, False, self._snapshot(key, owner, normalized))

    def replace_generation(self, token: ConversationToken, port: ConversationStatePort, state: Mapping[str, Any] | list[Any]) -> ConversationCommit:
        with self._owned(token.key) as (key, owner):
            with owner.lock:
                current = self._normalize_state(port.load(key), key)
                if token.key.normalized() != key or token.generation != owner.generation:
                    return ConversationCommit(False, True, self._snapshot(key, owner, current))
                normalized = self._normalize_state(state, key)
                port.save(key, normalized)
                owner.version += 1
                return ConversationCommit(True, False, self._snapshot(key, owner, normalized))

    def commit(
        self,
        token: ConversationToken,
        port: ConversationStatePort,
        *,
        messages: list[dict[str, Any]] | None = None,
        native_id: str | None = None,
        updates: Mapping[str, Any] | None = None,
    ) -> ConversationCommit:
        with self._owned(token.key) as (key, owner):
            with owner.lock:
                current = self._normalize_state(port.load(key), key)
                if token.key.normalized() != key or token.generation != owner.generation or token.version != owner.version:
                    return ConversationCommit(False, True, self._snapshot(key, owner, current))
                self._merge(current, messages=messages, native_id=native_id, updates=updates)
                port.save(key, current)
                owner.version += 1
                return ConversationCommit(True, False, self._snapshot(key, owner, current))

    def reset(self, key: ConversationKey, port: ConversationStatePort, *, preserve: Mapping[str, Any] | None = None) -> ConversationSnapshot:
        with self._owned(key) as (key, owner):
            with owner.lock:
                owner.generation = self._id_factory()
                owner.version += 1
                state = self._normalize_state(dict(preserve or {}), key)
                state["messages"] = []
                for field in ("nativeId", "sessionId", "threadId", "session_id", "activeRunId", "activeSessionId", "runId"):
                    state.pop(field, None)
                port.save(key, state)
                return self._snapshot(key, owner, state)

    def deliver_queued(
        self,
        key: ConversationKey,
        native_id: str,
        message: str,
        port: QueuedConversationPort,
        *,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str:
        """Deliver through a queued provider adapter without synthesizing run state.

        Provider work intentionally occurs outside the scoped state lock. The
        service only enforces the normalized conversation scope and bounded DTOs;
        authentication and protocol fallback remain adapter responsibilities.
        """
        key = key.normalized()
        native = str(native_id or "").strip()[:240]
        if not native:
            raise ValueError("native conversation id is required")
        text = str(message or "")
        bounded_attachments = [copy.deepcopy(item) for item in (attachments or []) if isinstance(item, dict)][:MAX_ATTACHMENTS]
        return str(port.deliver(key, native, text, bounded_attachments) or "")

    def control_queued(
        self,
        key: ConversationKey,
        native_id: str,
        action: str,
        port: QueuedConversationPort,
    ) -> dict[str, Any]:
        key = key.normalized()
        native = str(native_id or "").strip()[:240]
        normalized_action = str(action or "").strip().lower()
        if not native:
            raise ValueError("native conversation id is required")
        if normalized_action not in {"reset", "delete"}:
            raise ValueError("unsupported queued conversation action")
        result = port.control(key, native, normalized_action)
        return copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {"ok": False, "error": "invalid adapter response"}

    @staticmethod
    def _merge(state: dict[str, Any], *, messages, native_id, updates) -> None:
        if messages is not None:
            state["messages"] = [copy.deepcopy(item) for item in messages if isinstance(item, dict)][-MAX_MESSAGES:]
        if native_id is not None:
            if native_id:
                state["nativeId"] = str(native_id)[:240]
            else:
                state.pop("nativeId", None)
                state.pop("sessionId", None)
                state.pop("threadId", None)
                state.pop("session_id", None)
        if updates:
            for field, value in updates.items():
                if field in {"messages", "profile", "conversationId"}:
                    continue
                state[str(field)[:80]] = copy.deepcopy(value)

    @staticmethod
    def select_context(messages: list[dict[str, Any]], *, max_messages: int = 80, max_chars: int = MAX_CONTEXT_CHARS) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        used = 0
        for item in reversed([entry for entry in messages if isinstance(entry, dict)]):
            size = len(str(item.get("text") or item.get("content") or ""))
            if selected and (len(selected) >= max(1, int(max_messages)) or used + size > max(1, int(max_chars))):
                break
            if not selected and size > max_chars:
                item = {**item, "text": str(item.get("text") or item.get("content") or "")[-max_chars:]}
                size = max_chars
            selected.append(copy.deepcopy(item))
            used += size
        selected.reverse()
        return selected

    @staticmethod
    def validate_attachments(attachments: Any, *, allowed_roots: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        if attachments in (None, ""):
            return []
        if not isinstance(attachments, list):
            raise ValueError("attachments must be a list")
        roots = tuple(Path(root).expanduser().resolve() for root in allowed_roots if str(root or "").strip())
        result = []
        for raw in attachments[:MAX_ATTACHMENTS]:
            if not isinstance(raw, Mapping):
                raise ValueError("attachment descriptor must be an object")
            name = str(raw.get("name") or raw.get("filename") or "attachment").strip()[:240]
            media_type = str(raw.get("mimeType") or raw.get("contentType") or raw.get("type") or "application/octet-stream").strip()[:160]
            size = int(raw.get("size") or 0)
            if size < 0 or size > MAX_ATTACHMENT_SIZE:
                raise ValueError("attachment size is outside the supported bound")
            descriptor = {"name": name, "mimeType": media_type, "size": size}
            identifier = str(raw.get("id") or raw.get("attachmentId") or "").strip()[:240]
            if identifier:
                descriptor["id"] = identifier
            path_value = str(raw.get("path") or raw.get("filePath") or "").strip()
            if path_value:
                resolved = Path(os.path.expanduser(path_value)).resolve()
                if not roots or not any(resolved == root or root in resolved.parents for root in roots):
                    raise ValueError("attachment path is outside allowed roots")
                descriptor["path"] = str(resolved)
            url = str(raw.get("url") or raw.get("mediaUrl") or "").strip()[:2048]
            if url:
                parsed = urllib.parse.urlparse(url)
                if not (url.startswith("/chat-media") or parsed.scheme in {"http", "https"}):
                    raise ValueError("attachment URL scheme is not allowed")
                descriptor["url"] = url
            result.append(descriptor)
        return result

    def diagnostics(self) -> dict[str, int]:
        with self._states_lock:
            return {"scopedConversations": len(self._states), "maxScopedConversations": self._max_scopes}
