"""Provider-neutral slash-command parsing and orchestration.

Transport adapters construct trusted scopes and provide persistence/control ports.
This module intentionally has no dependency on the legacy server entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


MAX_PROVIDER_KIND = 80
MAX_AGENT_ID = 160
MAX_PROFILE = 160
MAX_CONVERSATION_ID = 240
MAX_SURFACE = 40
MAX_IDEMPOTENCY_KEY = 256
MAX_OPERATION_ID = 160
MAX_REPLY = 2_000
SUPPORTED_SURFACES = frozenset({"virtual-office", "feishu-dm", "feishu-group"})
TERMINAL_STATUSES = frozenset({"success", "no_op", "busy", "unsupported", "failed", "stale", "indeterminate"})


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


class ChatCommand(str, Enum):
    NEW = "/new"
    COMPACT = "/compact"


def parse_chat_command(text: Any, attachments: Sequence[Mapping[str, Any]] | None = None) -> ChatCommand | None:
    """Return an exact attachment-free command, otherwise preserve ordinary chat."""

    if attachments:
        return None
    candidate = str(text or "").strip()
    try:
        return ChatCommand(candidate)
    except ValueError:
        return None


@dataclass(frozen=True)
class CommandScope:
    provider_kind: str
    agent_id: str
    profile: str
    conversation_id: str
    surface: str

    @classmethod
    def create(
        cls,
        provider_kind: Any,
        agent_id: Any,
        profile: Any,
        conversation_id: Any,
        surface: Any,
    ) -> "CommandScope":
        provider = _bounded(provider_kind, MAX_PROVIDER_KIND).lower()
        if provider in {"claude", "claudecode"}:
            provider = "claude-code"
        agent = _bounded(agent_id, MAX_AGENT_ID)
        normalized_profile = _bounded(profile, MAX_PROFILE)
        conversation = _bounded(conversation_id, MAX_CONVERSATION_ID)
        normalized_surface = _bounded(surface, MAX_SURFACE).lower()
        if not provider or not agent or not normalized_profile or not conversation:
            raise ValueError("provider kind, agent id, profile, and conversation id are required")
        if normalized_surface not in SUPPORTED_SURFACES:
            raise ValueError("unsupported command surface")
        return cls(provider, agent, normalized_profile, conversation, normalized_surface)

    def key(self) -> tuple[str, str, str, str]:
        return (self.provider_kind, self.agent_id, self.profile, self.conversation_id)


@dataclass(frozen=True)
class CommandRequest:
    command: ChatCommand
    scope: CommandScope
    idempotency_key: str
    source_message_id: str = ""

    @classmethod
    def create(
        cls,
        command: ChatCommand | str,
        scope: CommandScope,
        idempotency_key: Any,
        source_message_id: Any = "",
    ) -> "CommandRequest":
        normalized_command = command if isinstance(command, ChatCommand) else ChatCommand(str(command or "").strip())
        key = _bounded(idempotency_key, MAX_IDEMPOTENCY_KEY)
        if not key:
            raise ValueError("idempotency key is required")
        return cls(normalized_command, scope, key, _bounded(source_message_id, MAX_IDEMPOTENCY_KEY))

    def audit_key(self) -> str:
        scope = "\x1f".join((*self.scope.key(), self.scope.surface))
        return f"{scope}\x1f{self.idempotency_key}"


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    status: str
    command: ChatCommand
    conversation_id: str
    reply: str
    changed: bool = False
    operation_id: str = ""
    next_conversation_id: str = ""
    next_session_key: str = ""
    duration_ms: int = 0
    duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = {
            "ok": bool(self.ok),
            "status": self.status,
            "command": self.command.value,
            "conversationId": self.conversation_id,
            "reply": self.reply,
            "changed": bool(self.changed),
            "operationId": self.operation_id,
            "durationMs": max(0, int(self.duration_ms or 0)),
            "duplicate": bool(self.duplicate),
        }
        if self.next_conversation_id:
            data["nextConversationId"] = self.next_conversation_id
        if self.next_session_key:
            data["nextSessionKey"] = self.next_session_key
        return data


class ProviderCommandPort(Protocol):
    def execute(self, command: ChatCommand, scope: CommandScope) -> Mapping[str, Any]: ...


class CommandReservationPort(Protocol):
    def try_acquire(self, scope: CommandScope) -> bool: ...

    def release(self, scope: CommandScope) -> None: ...


class CommandAuditPort(Protocol):
    def lookup(self, request: CommandRequest) -> Mapping[str, Any] | CommandResult | None: ...

    def record_started(self, request: CommandRequest, operation_id: str, started_at_ms: int) -> None: ...

    def record_terminal(self, request: CommandRequest, result: CommandResult) -> None: ...


class CommandIdPort(Protocol):
    def new_id(self) -> str: ...


class CommandClockPort(Protocol):
    def now_ms(self) -> int: ...


def _default_reply(command: ChatCommand, status: str, surface: str) -> str:
    if status == "success":
        if command is ChatCommand.NEW:
            return "已创建新会话" if surface.startswith("feishu-") else "New conversation created"
        return "上下文已压缩" if surface.startswith("feishu-") else "Context compacted"
    return {
        "no_op": "No compactable context",
        "busy": "Conversation is busy",
        "unsupported": "Command is not supported by this provider",
        "stale": "Conversation changed before the command could commit",
        "indeterminate": "Command outcome is indeterminate; it was not repeated",
        "failed": "Command failed",
    }[status]


def _normalize_provider_result(
    request: CommandRequest,
    operation_id: str,
    started_at_ms: int,
    finished_at_ms: int,
    outcome: Mapping[str, Any],
) -> CommandResult:
    raw_status = _bounded(outcome.get("status"), 64).lower().replace("-", "_")
    aliases = {
        "ok": "success",
        "completed": "success",
        "created": "success",
        "reset": "success",
        "compacted": "success",
        "noop": "no_op",
        "not_found": "no_op",
        "unavailable": "unsupported",
        "error": "failed",
    }
    status = aliases.get(raw_status, raw_status)
    if status not in TERMINAL_STATUSES:
        status = "success" if outcome.get("ok") is True else "failed"
    ok = status in {"success", "no_op"} and outcome.get("ok", status == "success") is not False
    reply = _bounded(outcome.get("reply") or outcome.get("error"), MAX_REPLY)
    if not reply:
        reply = _default_reply(request.command, status, request.scope.surface)
    return CommandResult(
        ok=ok,
        status=status,
        command=request.command,
        conversation_id=request.scope.conversation_id,
        reply=reply,
        changed=bool(outcome.get("changed", ok and status == "success")),
        operation_id=_bounded(operation_id, MAX_OPERATION_ID),
        next_conversation_id=_bounded(outcome.get("nextConversationId"), MAX_CONVERSATION_ID),
        next_session_key=_bounded(outcome.get("nextSessionKey"), MAX_CONVERSATION_ID),
        duration_ms=max(0, int(finished_at_ms) - int(started_at_ms)),
    )


def _result_from_audit(request: CommandRequest, stored: Mapping[str, Any] | CommandResult) -> CommandResult:
    if isinstance(stored, CommandResult):
        return CommandResult(**{**stored.__dict__, "duplicate": True})
    state = _bounded(stored.get("state"), 32).lower()
    status = _bounded(stored.get("status"), 64).lower()
    if state == "started" or status in {"started", "processing"}:
        status = "indeterminate"
    if status not in TERMINAL_STATUSES:
        status = "failed"
    return CommandResult(
        ok=bool(stored.get("ok")) and status in {"success", "no_op"},
        status=status,
        command=request.command,
        conversation_id=request.scope.conversation_id,
        reply=_bounded(stored.get("reply"), MAX_REPLY) or _default_reply(request.command, status, request.scope.surface),
        changed=bool(stored.get("changed")),
        operation_id=_bounded(stored.get("operationId"), MAX_OPERATION_ID),
        next_conversation_id=_bounded(stored.get("nextConversationId"), MAX_CONVERSATION_ID),
        next_session_key=_bounded(stored.get("nextSessionKey"), MAX_CONVERSATION_ID),
        duration_ms=max(0, int(stored.get("durationMs") or 0)),
        duplicate=True,
    )


class ChatCommandService:
    def __init__(
        self,
        provider: ProviderCommandPort,
        reservation: CommandReservationPort,
        audit: CommandAuditPort,
        ids: CommandIdPort,
        clock: CommandClockPort,
    ) -> None:
        self._provider = provider
        self._reservation = reservation
        self._audit = audit
        self._ids = ids
        self._clock = clock

    def execute(self, request: CommandRequest) -> CommandResult:
        try:
            stored = self._audit.lookup(request)
        except Exception:
            return self._failure(request, "Command audit lookup failed")
        if stored is not None:
            return _result_from_audit(request, stored)

        if not self._reservation.try_acquire(request.scope):
            return CommandResult(
                False,
                "busy",
                request.command,
                request.scope.conversation_id,
                _default_reply(request.command, "busy", request.scope.surface),
            )

        operation_id = _bounded(self._ids.new_id(), MAX_OPERATION_ID)
        started_at = int(self._clock.now_ms())
        try:
            try:
                self._audit.record_started(request, operation_id, started_at)
            except Exception:
                return self._failure(request, "Command audit start failed", operation_id=operation_id)

            try:
                outcome = self._provider.execute(request.command, request.scope)
                if not isinstance(outcome, Mapping):
                    outcome = {"ok": False, "status": "failed", "error": "Invalid provider command result"}
            except Exception:
                outcome = {"ok": False, "status": "failed", "error": "Provider command failed"}

            result = _normalize_provider_result(
                request,
                operation_id,
                started_at,
                int(self._clock.now_ms()),
                outcome,
            )
            try:
                self._audit.record_terminal(request, result)
            except Exception:
                return CommandResult(
                    False,
                    "indeterminate",
                    request.command,
                    request.scope.conversation_id,
                    _default_reply(request.command, "indeterminate", request.scope.surface),
                    changed=result.changed,
                    operation_id=operation_id,
                    duration_ms=result.duration_ms,
                )
            return result
        finally:
            self._reservation.release(request.scope)

    @staticmethod
    def _failure(request: CommandRequest, reply: str, *, operation_id: str = "") -> CommandResult:
        return CommandResult(
            False,
            "failed",
            request.command,
            request.scope.conversation_id,
            _bounded(reply, MAX_REPLY),
            operation_id=_bounded(operation_id, MAX_OPERATION_ID),
        )
