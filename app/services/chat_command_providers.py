"""Provider control adapters for chat slash commands.

The adapter depends on explicit conversation-state and provider callbacks. Server
wiring supplies the provider-specific ports without reversing the dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from services.chat_commands import ChatCommand, CommandScope
from services.provider_conversations import ConversationKey, ConversationStatePort, ProviderConversationService


SCOPED_STATE_PROVIDERS = frozenset({"codex", "hermes", "claude-code"})
SUPPORTED_PROVIDERS = frozenset({*SCOPED_STATE_PROVIDERS, "openclaw"})


class ConversationIdentityPort(Protocol):
    def new_conversation_id(self, scope: CommandScope) -> str: ...

    def new_session_key(self, scope: CommandScope) -> str: ...


class ProviderStatePortResolver(Protocol):
    def resolve(self, scope: CommandScope) -> ConversationStatePort: ...


class ProviderConversationKeyResolver(Protocol):
    def resolve(self, scope: CommandScope) -> ConversationKey: ...


class ExternalResetPort(Protocol):
    def reset(self, scope: CommandScope) -> Mapping[str, Any]: ...


NativeCleanup = Callable[[CommandScope, str], Mapping[str, Any] | None]


class CodexCompactRuntime(Protocol):
    def thread_id(self, scope: CommandScope) -> str: ...

    def try_acquire(self, scope: CommandScope) -> bool: ...

    def release(self, scope: CommandScope) -> None: ...

    def compact(self, scope: CommandScope, thread_id: str) -> Mapping[str, Any]: ...


class CodexCompactAdapter:
    def __init__(self, runtime: CodexCompactRuntime) -> None:
        self._runtime = runtime

    def compact(self, scope: CommandScope) -> Mapping[str, Any]:
        if scope.provider_kind != "codex":
            return {"ok": False, "status": "unsupported", "error": "Context compaction is unavailable"}
        thread_id = str(self._runtime.thread_id(scope) or "").strip()
        if not thread_id:
            return {"ok": True, "status": "no_op", "changed": False, "reply": "No compactable context"}
        if not self._runtime.try_acquire(scope):
            return {"ok": False, "status": "busy", "error": "Conversation is busy"}
        try:
            try:
                result = self._runtime.compact(scope, thread_id)
            except TimeoutError:
                return {"ok": False, "status": "failed", "error": "Context compaction timed out"}
            except Exception:
                return {"ok": False, "status": "failed", "error": "Context compaction failed"}
            if not isinstance(result, Mapping):
                return {"ok": False, "status": "failed", "error": "Invalid compaction result"}
            normalized = dict(result)
            normalized.setdefault("status", "success" if normalized.get("ok") else "failed")
            normalized.setdefault("changed", bool(normalized.get("ok")))
            return normalized
        finally:
            self._runtime.release(scope)


@dataclass(frozen=True)
class ResetOutcome:
    changed: bool
    previous_native_id: str = ""
    cleanup_warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {"ok": True, "status": "success", "changed": self.changed}
        if self.cleanup_warning:
            result["cleanupWarning"] = self.cleanup_warning[:512]
        return result


class ScopedConversationResetAdapter:
    """Advance a provider conversation generation through its existing state port."""

    def __init__(
        self,
        conversations: ProviderConversationService,
        keys: ProviderConversationKeyResolver,
        ports: ProviderStatePortResolver,
        cleanup: Mapping[str, NativeCleanup] | None = None,
    ) -> None:
        self._conversations = conversations
        self._keys = keys
        self._ports = ports
        self._cleanup = dict(cleanup or {})

    def reset(self, scope: CommandScope) -> ResetOutcome:
        if scope.provider_kind not in SCOPED_STATE_PROVIDERS:
            raise ValueError("provider does not use a scoped state port")
        key = self._keys.resolve(scope).normalized()
        port = self._ports.resolve(scope)
        before = self._conversations.read(key, port)
        self._conversations.reset(key, port)
        warning = ""
        cleanup = self._cleanup.get(scope.provider_kind)
        if cleanup and before.native_id:
            try:
                result = cleanup(scope, before.native_id)
                if isinstance(result, Mapping) and result.get("ok") is False:
                    warning = str(result.get("error") or "native cleanup failed")
            except Exception:
                warning = "native cleanup failed"
        return ResetOutcome(
            changed=bool(before.native_id or before.messages),
            previous_native_id=before.native_id,
            cleanup_warning=warning,
        )


class ChatProviderCommandAdapter:
    """Apply surface-specific `/new` semantics and expose a compact seam."""

    def __init__(
        self,
        identities: ConversationIdentityPort,
        scoped_reset: ScopedConversationResetAdapter,
        openclaw_reset: ExternalResetPort,
        compact: Callable[[CommandScope], Mapping[str, Any]] | None = None,
    ) -> None:
        self._identities = identities
        self._scoped_reset = scoped_reset
        self._openclaw_reset = openclaw_reset
        self._compact = compact

    def execute(self, command: ChatCommand, scope: CommandScope) -> Mapping[str, Any]:
        if scope.provider_kind not in SUPPORTED_PROVIDERS:
            return {"ok": False, "status": "unsupported", "error": "Unsupported chat provider"}
        if command is ChatCommand.COMPACT:
            if self._compact is None:
                return {"ok": False, "status": "unsupported", "error": "Context compaction is unavailable"}
            return self._safe_call(lambda: self._compact(scope))
        if command is not ChatCommand.NEW:
            return {"ok": False, "status": "unsupported", "error": "Unsupported chat command"}
        if scope.surface == "virtual-office":
            return self._create_vo_identity(scope)
        return self._reset_fixed_scope(scope)

    def _create_vo_identity(self, scope: CommandScope) -> Mapping[str, Any]:
        try:
            if scope.provider_kind == "openclaw":
                session_key = str(self._identities.new_session_key(scope) or "").strip()
                if not session_key:
                    raise ValueError("session identity was not created")
                return {
                    "ok": True,
                    "status": "success",
                    "changed": True,
                    "nextSessionKey": session_key,
                }
            conversation_id = str(self._identities.new_conversation_id(scope) or "").strip()
            if not conversation_id:
                raise ValueError("conversation identity was not created")
            return {
                "ok": True,
                "status": "success",
                "changed": True,
                "nextConversationId": conversation_id,
            }
        except Exception:
            return {"ok": False, "status": "failed", "error": "Conversation identity creation failed"}

    def _reset_fixed_scope(self, scope: CommandScope) -> Mapping[str, Any]:
        if scope.provider_kind == "openclaw":
            return self._safe_call(lambda: self._openclaw_reset.reset(scope))
        try:
            return self._scoped_reset.reset(scope).to_dict()
        except Exception:
            return {"ok": False, "status": "failed", "error": "Conversation reset failed"}

    @staticmethod
    def _safe_call(callback: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
        try:
            result = callback()
        except Exception:
            return {"ok": False, "status": "failed", "error": "Provider control failed"}
        if not isinstance(result, Mapping):
            return {"ok": False, "status": "failed", "error": "Invalid provider control result"}
        return dict(result)
