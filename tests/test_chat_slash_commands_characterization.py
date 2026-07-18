"""Pre-change characterization for chat controls and Feishu slash-like traffic."""

from __future__ import annotations

import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import feishu_chat_channel
from services.provider_conversations import ConversationKey, ProviderConversationService


class MemoryStatePort:
    def __init__(self):
        self.states = {}

    def load(self, key):
        return self.states.get(key.normalized())

    def save(self, key, state):
        self.states[key.normalized()] = dict(state)


def _feishu_harness():
    records = []
    dispatches = []
    sends = []
    locks = {}

    def record_event(row):
        stored = {"id": f"record-{len(records) + 1}", **row}
        records.append(stored)
        return stored

    def idempotency_hit(source_message_id):
        return next(
            (row for row in reversed(records) if row.get("sourceMessageId") == source_message_id),
            None,
        )

    def dispatch(agent_id, text, conversation_id, source_meta):
        dispatches.append({
            "agentId": agent_id,
            "text": text,
            "conversationId": conversation_id,
            "sourceMessageId": source_meta.get("sourceMessageId"),
        })
        return {"ok": True, "reply": f"ordinary:{text}", "conversationId": conversation_id}

    def send(chat_id, text):
        sends.append({"chatId": chat_id, "text": text})
        return {"ok": True, "status": "sent", "messageId": f"sent-{len(sends)}"}

    def invoke(body):
        return feishu_chat_channel.handle_message_event(
            body,
            cfg={
                "enabled": True,
                "groupChatEnabled": True,
                "appId": "cli-characterization",
                "appSecret": "secret",
                "representativeAgentId": "codex-local",
                "transportImplementation": "channel-sdk-node",
            },
            bindings={},
            load_records=lambda limit=5000: list(records[-limit:]),
            idempotency_hit=idempotency_hit,
            record_event=record_event,
            lock_for=lambda conversation_id: locks.setdefault(conversation_id, threading.Lock()),
            dispatch_agent=dispatch,
            send_text=send,
            reply_text=lambda chat_id, _source_id, text, _thread: send(chat_id, text),
            find_agent=lambda agent_id: {"id": agent_id, "name": "Codex"},
        )

    return invoke, records, dispatches, sends


def _message(message_id, chat_id, sender_id, text, *, chat_type="p2p", mention=False):
    return {
        "event": {
            "sender": {
                "sender_id": {"open_id": sender_id},
                "sender_name": f"Member {sender_id}",
                "sender_type": "user",
                "sender_is_bot": False,
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "text",
                "text": text,
                "mentions": ([{"openId": "ou_vo", "name": "VO", "isBot": True}] if mention else []),
            },
        }
    }


def test_unknown_slash_private_message_is_ordinary_and_redelivery_is_idempotent():
    invoke, records, dispatches, sends = _feishu_harness()
    body = _message("om-private-unknown", "oc-private", "ou-user", "/status")

    first = invoke(body)
    duplicate = invoke(body)

    assert first["status"] == "completed"
    assert duplicate["status"] == "duplicate"
    assert [item["text"] for item in dispatches] == ["/status"]
    assert [item["text"] for item in sends] == ["ordinary:/status"]
    assert [row["event"] for row in records] == ["user_message", "turn_completed"]
    assert records[0]["conversationId"] == records[1]["conversationId"]
    assert records[0]["conversationId"].startswith("feishu-dm:")


def test_unknown_slash_group_message_keeps_mention_gate_and_chat_scope():
    invoke, _records, dispatches, _sends = _feishu_harness()

    ignored = invoke(_message(
        "om-group-unmentioned", "oc-group-a", "ou-a", "/status", chat_type="group"
    ))
    first = invoke(_message(
        "om-group-a1", "oc-group-a", "ou-a", "/status", chat_type="group", mention=True
    ))
    second = invoke(_message(
        "om-group-a2", "oc-group-a", "ou-b", "/status", chat_type="group", mention=True
    ))
    other = invoke(_message(
        "om-group-b", "oc-group-b", "ou-a", "/status", chat_type="group", mention=True
    ))

    assert ignored["status"] == "ignored_missing_bot_mention"
    assert first["status"] == second["status"] == other["status"] == "completed"
    assert len(dispatches) == 3
    assert dispatches[0]["conversationId"] == dispatches[1]["conversationId"]
    assert dispatches[0]["conversationId"] != dispatches[2]["conversationId"]
    assert dispatches[0]["conversationId"].startswith("feishu-group:")


def test_private_and_group_conversation_identity_dimensions_are_stable():
    private_a = feishu_chat_channel.representative_conversation_id("user-a", "oc-private")
    private_a_again = feishu_chat_channel.representative_conversation_id("user-a", "oc-private")
    private_other_user = feishu_chat_channel.representative_conversation_id("user-b", "oc-private")
    private_other_chat = feishu_chat_channel.representative_conversation_id("user-a", "oc-other")
    group_a = feishu_chat_channel.group_conversation_id("oc-group")
    group_a_again = feishu_chat_channel.group_conversation_id("oc-group")
    group_b = feishu_chat_channel.group_conversation_id("oc-other-group")

    assert private_a == private_a_again
    assert private_a not in {private_other_user, private_other_chat, group_a}
    assert group_a == group_a_again
    assert group_a != group_b


def test_provider_conversation_reset_only_fences_the_target_scope():
    service = ProviderConversationService()
    port = MemoryStatePort()
    target = ConversationKey("codex", "codex-local", "local", "conversation-a")
    neighbor = ConversationKey("codex", "codex-local", "local", "conversation-b")

    target_before = service.replace(
        target,
        port,
        {"nativeId": "thread-a", "messages": [{"role": "user", "text": "a"}]},
    ).snapshot
    service.replace(
        neighbor,
        port,
        {"nativeId": "thread-b", "messages": [{"role": "user", "text": "b"}]},
    )

    reset = service.reset(target, port)
    stale = service.commit(
        target_before.token,
        port,
        native_id="late-thread",
        messages=[{"role": "assistant", "text": "late"}],
    )

    assert reset.native_id == ""
    assert reset.messages == []
    assert stale.applied is False and stale.stale is True
    assert service.read(neighbor, port).native_id == "thread-b"
    assert service.read(neighbor, port).messages == [{"role": "user", "text": "b"}]
