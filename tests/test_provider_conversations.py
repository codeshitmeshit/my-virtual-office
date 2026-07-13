import threading

import pytest

from app.services.provider_conversations import CallableConversationStatePort, CallableQueuedConversationPort, ConversationKey, ProviderConversationService


class MemoryPort:
    def __init__(self, initial=None):
        self.data = initial
        self.saves = 0
        self.fail_load = False
        self.fail_save = False

    def load(self, key):
        if self.fail_load:
            raise OSError("history unavailable")
        return self.data

    def save(self, key, state):
        if self.fail_save:
            raise OSError("history unavailable")
        self.saves += 1
        self.data = dict(state)


def key(**values):
    data = {"provider_kind": "hermes", "agent_id": "agent", "profile": "default", "conversation_id": "conv"}
    data.update(values)
    return ConversationKey(**data)


def test_old_list_and_dict_records_are_normalized_without_format_migration():
    service = ProviderConversationService()
    old_list = MemoryPort([{"role": "user", "text": "old"}])
    snapshot = service.read(key(), old_list)
    assert snapshot.messages == [{"role": "user", "text": "old"}]
    assert snapshot.native_id == ""
    old_dict = MemoryPort({"messages": [{"role": "assistant", "text": "reply"}], "session_id": "native-old", "custom": 1})
    snapshot = service.read(key(conversation_id="legacy"), old_dict)
    assert snapshot.native_id == "native-old"
    assert snapshot.state["custom"] == 1


def test_reads_are_copies_and_scopes_are_isolated():
    service = ProviderConversationService()
    first_port = MemoryPort({"messages": [{"text": "one"}], "sessionId": "native-1"})
    second_port = MemoryPort({"messages": [{"text": "two"}], "sessionId": "native-2"})
    first = service.read(key(conversation_id="one"), first_port)
    second = service.read(key(conversation_id="two"), second_port)
    first.messages[0]["text"] = "mutated"
    assert service.read(key(conversation_id="one"), first_port).messages[0]["text"] == "one"
    assert second.messages[0]["text"] == "two"


def test_reset_fences_stale_continuation_and_clears_native_id():
    ids = iter(("g1", "g2"))
    service = ProviderConversationService(id_factory=ids.__next__)
    port = MemoryPort({"messages": [{"text": "before"}], "sessionId": "native"})
    before = service.read(key(), port)
    reset = service.reset(key(), port)
    stale = service.commit(before.token, port, messages=[{"text": "late"}], native_id="late-native")
    assert reset.messages == []
    assert reset.native_id == ""
    assert stale.applied is False and stale.stale is True
    assert port.data["messages"] == []
    assert "sessionId" not in port.data


def test_generation_commit_allows_own_progress_versions_but_not_reset():
    ids = iter(("g1", "g2"))
    service = ProviderConversationService(id_factory=ids.__next__)
    port = MemoryPort({"messages": []})
    token = service.read(key(), port).token
    service.replace(key(), port, {"messages": [{"text": "progress"}]})
    continued = service.replace_generation(token, port, {"messages": [{"text": "final"}]})
    assert continued.applied is True
    service.reset(key(), port)
    stale = service.replace_generation(token, port, {"messages": [{"text": "late"}]})
    assert stale.stale is True
    assert port.data["messages"] == []


def test_foreign_scope_token_cannot_commit():
    service = ProviderConversationService()
    first_port = MemoryPort({"messages": []})
    other_port = MemoryPort({"messages": []})
    token = service.read(key(conversation_id="one"), first_port).token
    foreign = type(token)(key(conversation_id="two"), token.generation, token.version)
    result = service.commit(foreign, other_port, messages=[{"text": "foreign"}])
    assert result.applied is False
    assert other_port.saves == 0


def test_same_scope_writes_serialize_but_unrelated_scopes_progress():
    service = ProviderConversationService()
    slow_entered = threading.Event()
    slow_release = threading.Event()
    fast_saved = threading.Event()
    slow_data = {"messages": []}
    fast_data = {"messages": []}

    def slow_load(key):
        return slow_data

    def slow_save(key, state):
        slow_entered.set()
        slow_release.wait(1)
        slow_data.update(state)

    def fast_save(key, state):
        fast_data.update(state)
        fast_saved.set()

    slow = CallableConversationStatePort(slow_load, slow_save)
    fast = CallableConversationStatePort(lambda key: fast_data, fast_save)
    thread = threading.Thread(target=lambda: service.overwrite(key(conversation_id="slow"), slow, messages=[{"text": "slow"}]))
    thread.start()
    assert slow_entered.wait(0.5)
    service.overwrite(key(conversation_id="fast"), fast, messages=[{"text": "fast"}])
    assert fast_saved.is_set()
    slow_release.set()
    thread.join()


def test_history_failures_do_not_advance_version_or_partially_commit():
    service = ProviderConversationService()
    port = MemoryPort({"messages": []})
    before = service.read(key(), port)
    port.fail_save = True
    with pytest.raises(OSError):
        service.commit(before.token, port, messages=[{"text": "not saved"}])
    port.fail_save = False
    retry = service.commit(before.token, port, messages=[{"text": "saved"}])
    assert retry.applied is True
    assert port.data["messages"] == [{"text": "saved"}]


def test_context_selection_is_bounded_and_keeps_latest_messages():
    messages = [{"text": str(index) * 10} for index in range(20)]
    selected = ProviderConversationService.select_context(messages, max_messages=3, max_chars=100)
    assert selected == messages[-3:]
    oversized = ProviderConversationService.select_context([{"text": "x" * 100}], max_chars=10)
    assert oversized[0]["text"] == "x" * 10


def test_attachment_descriptors_are_bounded_and_validate_paths(tmp_path):
    allowed = tmp_path / "uploads"
    allowed.mkdir()
    file_path = allowed / "a.txt"
    file_path.write_text("ok")
    descriptors = ProviderConversationService.validate_attachments([
        {"name": "a.txt", "type": "text/plain", "size": 2, "path": str(file_path), "raw": "ignored"}
    ], allowed_roots=(str(allowed),))
    assert descriptors == [{"name": "a.txt", "mimeType": "text/plain", "size": 2, "path": str(file_path)}]
    with pytest.raises(ValueError):
        ProviderConversationService.validate_attachments([{"path": "/etc/passwd"}], allowed_roots=(str(allowed),))
    with pytest.raises(ValueError):
        ProviderConversationService.validate_attachments([{"size": 100 * 1024 * 1024}])
    with pytest.raises(ValueError):
        ProviderConversationService.validate_attachments([{"url": "file:///etc/passwd"}])


def test_queued_delivery_preserves_scope_and_does_not_create_run_state():
    service = ProviderConversationService()
    calls = []
    attachment = {"name": "note.txt", "size": 2}
    port = CallableQueuedConversationPort(
        lambda scope, native_id, message, attachments: calls.append((scope, native_id, message, attachments)) or "reply",
        lambda scope, native_id, action: {"ok": True},
    )
    result = service.deliver_queued(key(provider_kind="openclaw"), "agent:agent:conversation-1", "hello", port, attachments=[attachment])
    attachment["name"] = "mutated"
    assert result == "reply"
    assert calls[0][0] == key(provider_kind="openclaw").normalized()
    assert calls[0][1:] == ("agent:agent:conversation-1", "hello", [{"name": "note.txt", "size": 2}])
    assert service.diagnostics()["scopedConversations"] == 0


def test_queued_control_allows_only_existing_reset_delete_semantics():
    service = ProviderConversationService()
    calls = []
    port = CallableQueuedConversationPort(
        lambda *_args: "",
        lambda scope, native_id, action: calls.append((native_id, action)) or {"ok": True, "secret": [1]},
    )
    outcome = service.control_queued(key(provider_kind="openclaw"), "agent:agent:main", "reset", port)
    outcome["secret"].append(2)
    assert calls == [("agent:agent:main", "reset")]
    with pytest.raises(ValueError):
        service.control_queued(key(provider_kind="openclaw"), "agent:agent:main", "start", port)


def test_scope_owners_are_bounded_and_evicted_tokens_stay_stale():
    ids = iter(("g1", "g2", "g3", "g4", "g5"))
    service = ProviderConversationService(id_factory=ids.__next__, max_scopes=2)
    first_port = MemoryPort({"messages": []})
    stale_token = service.read(key(conversation_id="one"), first_port).token
    service.read(key(conversation_id="two"), MemoryPort({"messages": []}))
    service.read(key(conversation_id="three"), MemoryPort({"messages": []}))
    assert service.diagnostics() == {"scopedConversations": 2, "maxScopedConversations": 2}
    result = service.commit(stale_token, first_port, messages=[{"text": "late"}])
    assert result.stale is True and result.applied is False
    assert first_port.data["messages"] == []


def test_new_service_instance_recovers_persisted_history_and_native_id():
    port = MemoryPort({"messages": [{"text": "persisted"}], "sessionId": "native-persisted"})
    restarted = ProviderConversationService()
    snapshot = restarted.read(key(conversation_id="after-restart"), port)
    assert snapshot.messages == [{"text": "persisted"}]
    assert snapshot.native_id == "native-persisted"
