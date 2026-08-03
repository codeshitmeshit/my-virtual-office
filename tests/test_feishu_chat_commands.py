import threading

from app import feishu_chat_channel
from app.services.feishu_topic_foreground_commands import (
    FeishuTopicForegroundCommandService,
    ForegroundCommand,
    ForegroundCommandContext,
    StaticTopicAgentCatalog,
)


def _message(message_id, chat_id, sender, text, *, group=False, mention=True, resources=None):
    return {
        "event": {
            "sender": {
                "sender_id": {"open_id": sender},
                "sender_name": f"Member {sender}",
                "sender_type": "user",
                "sender_is_bot": False,
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": "group" if group else "p2p",
                "message_type": "text",
                "text": text,
                "mentions": ([{"isBot": True, "openId": "ou-vo"}] if group and mention else []),
                "resources": resources or [],
            },
        }
    }


def _harness(*, locks=None):
    records, dispatches, commands, foreground_commands, sends = [], [], [], [], []
    locks = locks if locks is not None else {}

    def record(row):
        stored = {"id": f"row-{len(records) + 1}", **row}
        records.append(stored)
        return stored

    def idempotency(message_id):
        return next((row for row in reversed(records)
                     if row.get("sourceMessageId") == message_id
                     and row.get("event") in {"turn_completed", "command_completed"}), None)

    def command_callback(command, context):
        commands.append((command, context))
        return {"ok": True, "status": "success", "changed": True, "reply": f"done:{command}"}

    def foreground_command_callback(command, context):
        foreground_commands.append((command, context))
        return {"ok": True, "status": "success", "changed": True, "reply": f"foreground:{command}"}

    def dispatch(agent_id, text, conversation_id, metadata):
        dispatches.append((agent_id, text, conversation_id, metadata))
        return {"ok": True, "reply": f"ordinary:{text}"}

    def send(chat_id, text):
        sends.append((chat_id, text))
        return {"ok": True, "messageId": f"sent-{len(sends)}"}

    def invoke(body):
        return feishu_chat_channel.handle_message_event(
            body,
            cfg={
                "enabled": True,
                "groupChatEnabled": True,
                "appId": "cli-test",
                "appSecret": "secret",
                "representativeAgentId": "codex-local",
                "transportImplementation": "channel-sdk-node",
            },
            bindings={},
            load_records=lambda limit=5000: records[-limit:],
            idempotency_hit=idempotency,
            record_event=record,
            lock_for=lambda key: locks.setdefault(key, threading.Lock()),
            dispatch_agent=dispatch,
            send_text=send,
            reply_text=lambda chat_id, _message_id, text, _thread: send(chat_id, text),
            find_agent=lambda agent_id: {"id": agent_id},
            command_callback=command_callback,
            foreground_command_callback=foreground_command_callback,
        )

    return invoke, records, dispatches, commands, foreground_commands, sends, locks


def test_private_exact_command_uses_trusted_scope_and_skips_agent_dispatch():
    invoke, records, dispatches, commands, _foreground_commands, sends, _locks = _harness()
    body = _message("om-command", "oc-private", "ou-actor", "  /new  ")

    first = invoke(body)
    duplicate = invoke(body)

    assert first["status"] == "success"
    assert duplicate["status"] == "duplicate"
    assert not dispatches
    assert len(commands) == 1
    command, context = commands[0]
    assert command == "/new"
    assert context["sourceSurface"] == "feishu-dm"
    assert context["sender"]["openId"] == "ou-actor"
    assert context["conversationId"].startswith("feishu-dm:")
    assert [row["event"] for row in records] == ["command_started", "command_completed"]
    assert sends == [("oc-private", "done:/new")]


def test_group_command_keeps_mention_gate_and_shares_scope_within_chat_only():
    invoke, _records, dispatches, commands, _foreground_commands, _sends, _locks = _harness()

    ignored = invoke(_message("om-unmentioned", "oc-a", "ou-a", "/new", group=True, mention=False))
    invoke(_message("om-a1", "oc-a", "ou-a", "/new", group=True))
    invoke(_message("om-a2", "oc-a", "ou-b", "/compact", group=True))
    invoke(_message("om-b", "oc-b", "ou-a", "/new", group=True))

    assert ignored["status"] == "ignored_missing_bot_mention"
    assert not dispatches
    contexts = [item[1] for item in commands]
    assert contexts[0]["conversationId"] == contexts[1]["conversationId"]
    assert contexts[0]["conversationId"] != contexts[2]["conversationId"]
    assert contexts[0]["sourceSurface"] == "feishu-group"


def test_non_exact_slash_command_is_rejected_before_agent_dispatch():
    invoke, _records, dispatches, commands, _foreground_commands, _sends, _locks = _harness()

    case_result = invoke(_message("om-case", "oc-private", "ou-a", "/New"))
    args_result = invoke(_message("om-args", "oc-private", "ou-a", "/new now"))

    assert case_result["status"] == "slash_command_blocked"
    assert args_result["status"] == "slash_command_blocked"
    assert not commands
    assert not dispatches


def test_attached_exact_command_remains_an_ordinary_message():
    invoke, _records, dispatches, commands, _foreground_commands, _sends, _locks = _harness()

    invoke(_message("om-resource", "oc-private", "ou-a", "/new", resources=[{"type": "file"}]))

    assert not commands
    assert [item[1] for item in dispatches] == ["/new"]


def test_command_conversation_admission_is_non_blocking():
    locks = {}
    invoke, records, dispatches, commands, _foreground_commands, sends, locks = _harness(locks=locks)
    conversation_id = feishu_chat_channel.group_conversation_id("oc-busy")
    busy_lock = locks.setdefault(conversation_id, threading.Lock())
    busy_lock.acquire()
    try:
        result = invoke(_message("om-busy", "oc-busy", "ou-a", "/compact", group=True))
    finally:
        busy_lock.release()

    assert result["status"] == "busy"
    assert not dispatches and not commands
    assert records[-1]["commandStatus"] == "busy"
    assert sends and "稍后重试" in sends[-1][1]


def test_private_here_foreground_command_delegates_without_agent_dispatch():
    invoke, records, dispatches, commands, foreground_commands, sends, _locks = _harness()
    body = _message("om-here", "oc-private", "ou-actor", "  /here  ")

    first = invoke(body)
    duplicate = invoke(body)

    assert first["status"] == "success"
    assert duplicate["status"] == "duplicate"
    assert not dispatches and not commands
    assert len(foreground_commands) == 1
    command, context = foreground_commands[0]
    assert command == "/here"
    assert context["sourceSurface"] == "feishu-dm"
    assert context["sender"]["openId"] == "ou-actor"
    assert context["conversationId"].startswith("feishu-dm:")
    assert [row["event"] for row in records] == ["command_started", "command_completed"]
    assert sends == [("oc-private", "foreground:/here")]


def test_private_here_remains_ordinary_without_foreground_callback():
    records, dispatches, sends = [], [], []

    def record(row):
        stored = {"id": f"row-{len(records) + 1}", **row}
        records.append(stored)
        return stored

    result = feishu_chat_channel.handle_message_event(
        _message("om-here-ordinary", "oc-private", "ou-actor", "/here"),
        cfg={
            "enabled": True,
            "groupChatEnabled": True,
            "appId": "cli-test",
            "appSecret": "secret",
            "representativeAgentId": "codex-local",
            "transportImplementation": "channel-sdk-node",
        },
        bindings={},
        load_records=lambda limit=5000: records[-limit:],
        idempotency_hit=lambda _message_id: None,
        record_event=record,
        lock_for=lambda _key: threading.Lock(),
        dispatch_agent=lambda agent_id, text, conversation_id, metadata: (
            dispatches.append((agent_id, text, conversation_id, metadata))
            or {"ok": True, "reply": f"ordinary:{text}"}
        ),
        send_text=lambda chat_id, text: sends.append((chat_id, text)) or {"ok": True, "messageId": "sent-1"},
        reply_text=lambda chat_id, _message_id, text, _thread: sends.append((chat_id, text)) or {"ok": True},
        find_agent=lambda agent_id: {"id": agent_id},
        command_callback=lambda _command, _context: {"ok": True, "reply": "unused"},
    )

    assert result["status"] == "completed"
    assert [item[1] for item in dispatches] == ["/here"]
    assert sends == [("oc-private", "ordinary:/here")]


def test_private_change_foreground_command_is_rejected_outside_topic():
    records, dispatches, sends = [], [], []
    service = FeishuTopicForegroundCommandService(
        agent_catalog=StaticTopicAgentCatalog([{"label": "Agent B", "agentId": "agent-b"}]),
        agent_config=type("Config", (), {
            "get_agent": lambda self, topic_id: "",
            "set_agent": lambda self, topic_id, agent_id: {"ok": True},
        })(),
    )

    def record(row):
        stored = {"id": f"row-{len(records) + 1}", **row}
        records.append(stored)
        return stored

    def foreground_callback(command, context):
        result = service.execute(
            ForegroundCommand(command, context.get("argument") or ""),
            ForegroundCommandContext.create(
                surface=context.get("sourceSurface"),
                source_message_id=context.get("sourceMessageId"),
                conversation_id=context.get("conversationId"),
                chat_type=context.get("chatType"),
                source_meta=context,
            ),
        )
        return result.to_dict()

    result = feishu_chat_channel.handle_message_event(
        _message("om-change", "oc-private", "ou-actor", "/change"),
        cfg={
            "enabled": True,
            "groupChatEnabled": True,
            "appId": "cli-test",
            "appSecret": "secret",
            "representativeAgentId": "codex-local",
            "transportImplementation": "channel-sdk-node",
        },
        bindings={},
        load_records=lambda limit=5000: records[-limit:],
        idempotency_hit=lambda _message_id: None,
        record_event=record,
        lock_for=lambda _key: threading.Lock(),
        dispatch_agent=lambda agent_id, text, conversation_id, metadata: (
            dispatches.append((agent_id, text, conversation_id, metadata))
            or {"ok": True, "reply": f"ordinary:{text}"}
        ),
        send_text=lambda chat_id, text: sends.append((chat_id, text)) or {"ok": True, "messageId": "sent-1"},
        reply_text=lambda chat_id, _message_id, text, _thread: sends.append((chat_id, text)) or {"ok": True},
        find_agent=lambda agent_id: {"id": agent_id},
        foreground_command_callback=foreground_callback,
    )

    assert result["status"] == "unsupported_location"
    assert dispatches == []
    assert "只能在已激活的通知话题" in sends[-1][1]
