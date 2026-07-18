from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.chat_command_providers import CodexCompactAdapter, ChatProviderCommandAdapter, ScopedConversationResetAdapter
from services.chat_commands import ChatCommand, CommandScope
from services.provider_conversations import ConversationKey, ProviderConversationService


class MemoryPort:
    def __init__(self, fail_save=False):
        self.state = {}
        self.fail_save = fail_save

    def load(self, key):
        return self.state.get(key.normalized())

    def save(self, key, state):
        if self.fail_save:
            raise OSError("state write failed")
        self.state[key.normalized()] = dict(state)


class PortResolver:
    def __init__(self, ports):
        self.ports = ports

    def resolve(self, scope):
        return self.ports[scope.key()]


class KeyResolver:
    def resolve(self, scope):
        return key(scope)


class Identities:
    def __init__(self):
        self.calls = []

    def new_conversation_id(self, scope):
        self.calls.append(("conversation", scope))
        return f"next-{scope.provider_kind}"

    def new_session_key(self, scope):
        self.calls.append(("session", scope))
        return f"agent:{scope.agent_id}:conversation-next"


class OpenClawReset:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome or {"ok": True, "status": "success", "changed": True}
        self.error = error
        self.calls = []

    def reset(self, scope):
        self.calls.append(scope)
        if self.error:
            raise self.error
        return self.outcome


class CompactRuntime:
    def __init__(self, thread_id="thread-1", acquired=True, outcome=None, error=None):
        self.selected_thread = thread_id
        self.acquired = acquired
        self.outcome = outcome or {"ok": True, "reply": "compacted"}
        self.error = error
        self.calls = []
        self.released = []

    def thread_id(self, scope):
        return self.selected_thread

    def try_acquire(self, scope):
        return self.acquired

    def release(self, scope):
        self.released.append(scope)

    def compact(self, scope, thread_id):
        self.calls.append((scope, thread_id))
        if self.error:
            raise self.error
        return self.outcome


def scope(provider, surface="virtual-office", conversation="conversation-a"):
    return CommandScope.create(provider, f"{provider}-agent", "main", conversation, surface)


def key(value):
    return ConversationKey(value.provider_kind, value.agent_id, value.profile, value.conversation_id)


def adapter_for(scopes, *, cleanup=None, openclaw=None, compact=None):
    conversations = ProviderConversationService(id_factory=lambda: "new-generation")
    ports = {item.key(): MemoryPort() for item in scopes if item.provider_kind != "openclaw"}
    resetter = ScopedConversationResetAdapter(conversations, KeyResolver(), PortResolver(ports), cleanup=cleanup)
    identities = Identities()
    openclaw = openclaw or OpenClawReset()
    return ChatProviderCommandAdapter(identities, resetter, openclaw, compact), conversations, ports, identities, openclaw


@pytest.mark.parametrize("provider", ["codex", "hermes", "claude-code"])
def test_vo_new_creates_identity_without_mutating_old_provider_state(provider):
    selected = scope(provider)
    adapter, conversations, ports, identities, _openclaw = adapter_for([selected])
    port = ports[selected.key()]
    conversations.replace(key(selected), port, {
        "nativeId": f"native-{provider}",
        "messages": [{"role": "user", "text": "preserve me"}],
    })

    result = adapter.execute(ChatCommand.NEW, selected)

    assert result == {
        "ok": True,
        "status": "success",
        "changed": True,
        "nextConversationId": f"next-{provider}",
    }
    assert conversations.read(key(selected), port).native_id == f"native-{provider}"
    assert conversations.read(key(selected), port).messages[0]["text"] == "preserve me"
    assert identities.calls == [("conversation", selected)]


def test_vo_openclaw_new_creates_agent_session_without_resetting_old_session():
    selected = scope("openclaw")
    adapter, _conversations, _ports, identities, openclaw = adapter_for([selected])
    result = adapter.execute(ChatCommand.NEW, selected)
    assert result["nextSessionKey"] == "agent:openclaw-agent:conversation-next"
    assert result["changed"] is True
    assert identities.calls == [("session", selected)]
    assert openclaw.calls == []


@pytest.mark.parametrize("provider", ["codex", "hermes", "claude-code"])
def test_feishu_new_resets_only_target_generation_and_fences_late_commit(provider):
    target = scope(provider, "feishu-group", "group-a")
    neighbor = scope(provider, "feishu-group", "group-b")
    adapter, conversations, ports, _identities, _openclaw = adapter_for([target, neighbor])
    target_port = ports[target.key()]
    neighbor_port = ports[neighbor.key()]
    before = conversations.replace(key(target), target_port, {
        "nativeId": "target-native",
        "messages": [{"role": "user", "text": "target"}],
    }).snapshot
    conversations.replace(key(neighbor), neighbor_port, {
        "nativeId": "neighbor-native",
        "messages": [{"role": "user", "text": "neighbor"}],
    })

    result = adapter.execute(ChatCommand.NEW, target)
    late = conversations.commit(before.token, target_port, native_id="late-native")

    assert result["ok"] is True and result["changed"] is True
    assert conversations.read(key(target), target_port).native_id == ""
    assert conversations.read(key(target), target_port).messages == []
    assert late.applied is False and late.stale is True
    assert conversations.read(key(neighbor), neighbor_port).native_id == "neighbor-native"


def test_native_cleanup_failure_does_not_undo_committed_generation_reset():
    target = scope("hermes", "feishu-dm")
    cleanup_calls = []
    adapter, conversations, ports, _identities, _openclaw = adapter_for(
        [target],
        cleanup={"hermes": lambda actual_scope, native_id: cleanup_calls.append((actual_scope, native_id)) or {
            "ok": False, "error": "delete failed"
        }},
    )
    port = ports[target.key()]
    conversations.replace(key(target), port, {"nativeId": "hermes-native", "messages": []})

    result = adapter.execute(ChatCommand.NEW, target)

    assert result["ok"] is True and result["cleanupWarning"] == "delete failed"
    assert conversations.read(key(target), port).native_id == ""
    assert cleanup_calls == [(target, "hermes-native")]


def test_state_write_failure_returns_failure_without_claiming_reset_success():
    target = scope("claude-code", "feishu-dm")
    conversations = ProviderConversationService()
    port = MemoryPort()
    port.state[key(target).normalized()] = {"nativeId": "claude-native", "messages": []}
    resetter = ScopedConversationResetAdapter(conversations, KeyResolver(), PortResolver({target.key(): port}))
    adapter = ChatProviderCommandAdapter(Identities(), resetter, OpenClawReset())
    port.fail_save = True

    result = adapter.execute(ChatCommand.NEW, target)

    assert result == {"ok": False, "status": "failed", "error": "Conversation reset failed"}
    assert port.state[key(target).normalized()]["nativeId"] == "claude-native"


def test_feishu_openclaw_reset_uses_external_port_and_propagates_failure():
    target = scope("openclaw", "feishu-group")
    openclaw = OpenClawReset({"ok": False, "status": "failed", "error": "gateway reset failed"})
    adapter, _conversations, _ports, identities, actual_port = adapter_for([target], openclaw=openclaw)
    result = adapter.execute(ChatCommand.NEW, target)
    assert result["ok"] is False and result["error"] == "gateway reset failed"
    assert actual_port.calls == [target]
    assert identities.calls == []


def test_unknown_provider_and_compact_are_explicitly_unsupported():
    target = scope("openclaw")
    adapter, *_rest = adapter_for([target])
    unknown = CommandScope.create("future-provider", "agent", "main", "conversation", "virtual-office")
    assert adapter.execute(ChatCommand.NEW, unknown)["status"] == "unsupported"
    assert adapter.execute(ChatCommand.COMPACT, target)["status"] == "unsupported"


def test_codex_compact_keeps_logical_identity_and_releases_runtime_lock():
    target = scope("codex", "feishu-group")
    runtime = CompactRuntime()
    adapter, conversations, ports, identities, openclaw = adapter_for([target], compact=CodexCompactAdapter(runtime).compact)
    result = adapter.execute(ChatCommand.COMPACT, target)
    assert result == {"ok": True, "reply": "compacted", "status": "success", "changed": True}
    assert runtime.calls == [(target, "thread-1")]
    assert runtime.released == [target]


@pytest.mark.parametrize("runtime, expected", [
    (CompactRuntime(thread_id=""), "no_op"),
    (CompactRuntime(acquired=False), "busy"),
    (CompactRuntime(error=TimeoutError()), "failed"),
    (CompactRuntime(error=RuntimeError("secret")), "failed"),
])
def test_codex_compact_boundary_outcomes(runtime, expected):
    target = scope("codex")
    adapter, _conversations, _ports, identities, openclaw = adapter_for([target], compact=CodexCompactAdapter(runtime).compact)
    result = adapter.execute(ChatCommand.COMPACT, target)
    assert result["status"] == expected
    if expected in {"no_op", "busy"}:
        assert runtime.calls == []


@pytest.mark.parametrize("provider", ["hermes", "claude-code", "openclaw"])
def test_non_codex_compact_never_calls_codex_runtime(provider):
    target = scope(provider)
    runtime = CompactRuntime()
    adapter, _conversations, _ports, identities, openclaw = adapter_for([target], compact=CodexCompactAdapter(runtime).compact)
    result = adapter.execute(ChatCommand.COMPACT, target)
    assert result["status"] == "unsupported"
    assert runtime.calls == []
