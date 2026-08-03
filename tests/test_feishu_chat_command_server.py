import os
import sys
import tempfile
from pathlib import Path

import pytest


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

_IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-feishu-command-import-")
os.environ["VO_STATUS_DIR"] = _IMPORT_STATUS_DIR
os.environ["VO_CONFIG"] = str(Path(_IMPORT_STATUS_DIR) / "vo-config.json")

import feishu_chat_channel
import server


def _body(message_id="om-command", chat_id="oc-private", text="/new", *, group=False):
    return {
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou-actor"},
                "sender_name": "Actor",
                "sender_type": "user",
                "sender_is_bot": False,
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": "group" if group else "p2p",
                "message_type": "text",
                "text": text,
                "mentions": ([{"isBot": True, "openId": "ou-vo"}] if group else []),
            },
        }
    }


def _configure(monkeypatch, tmp_path, *, provider="codex"):
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_FEISHU_NOTIFICATION_TOPIC_SERVICE", None)
    monkeypatch.setattr(server, "_FEISHU_NOTIFICATION_TOPIC_STORE", None)
    monkeypatch.setattr(server, "_FEISHU_TOPIC_FOREGROUND_COMMAND_SERVICE", None)
    monkeypatch.setattr(server, "VO_CONFIG", {
        **server.VO_CONFIG,
        "notifications": {
            **((server.VO_CONFIG.get("notifications") or {}) if isinstance(server.VO_CONFIG.get("notifications"), dict) else {}),
            "feishuEnabled": True,
            "feishuAppId": "cli-test",
            "feishuAppSecret": "secret",
            "recipientPolicy": "originating_user_dm",
            "topicConversationsEnabled": True,
            "topicConversationModels": [
                {"label": "默认", "model": "default"},
                {"label": "专业", "model": "pro-model", "aliases": ["pro"]},
            ],
        },
    })
    monkeypatch.setattr(server, "_sync_feishu_channel_record_to_comm_ledger", lambda _row: None)
    monkeypatch.setattr(server, "_feishu_chat_app_config", lambda: {
        "enabled": True,
        "groupChatEnabled": True,
        "appId": "cli-test",
        "appSecret": "secret",
        "representativeAgentId": "representative",
        "transportImplementation": "channel-sdk-node",
    })
    monkeypatch.setattr(server, "_find_agent_record", lambda agent_id: {
        "id": agent_id,
        "statusKey": agent_id,
        "providerKind": provider,
        "profile": "local",
    })
    monkeypatch.setenv("VO_CHAT_SLASH_COMMANDS_ENABLED", "1")


def test_server_wires_trusted_feishu_command_and_persistent_redelivery(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    calls, dispatches, sends = [], [], []

    def command(command, context):
        calls.append((command, context))
        return {"ok": True, "status": "success", "changed": True, "reply": "已创建新会话"}

    monkeypatch.setattr(server, "_dispatch_feishu_chat_command", command)
    monkeypatch.setattr(server, "_dispatch_representative_agent_message", lambda *args: dispatches.append(args))
    send = lambda chat_id, text: sends.append((chat_id, text)) or {"ok": True, "messageId": "om-reply"}

    first = server._handle_feishu_chat_message_event(_body(), send_text=send)
    duplicate = server._handle_feishu_chat_message_event(_body(), send_text=send)

    assert first["status"] == "success"
    assert duplicate["status"] == "duplicate"
    assert len(calls) == 1 and not dispatches
    assert calls[0][1]["representativeAgentId"] == "representative"
    assert calls[0][1]["conversationId"].startswith("feishu-dm:")
    assert sends == [("oc-private", "已创建新会话")]
    indexed = feishu_chat_channel.load_source_index(str(tmp_path), "om-command")
    assert indexed["state"] == "completed"
    assert indexed["record"]["event"] == "command_completed"


def test_server_wires_private_here_to_foreground_notification_sender(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    dispatches, notifications, sends = [], [], []
    monkeypatch.setattr(server, "_dispatch_representative_agent_message", lambda *args: dispatches.append(args) or {
        "ok": True,
        "reply": "上一条回复",
        "feishuChatReply": "上一条回复",
    })
    monkeypatch.setattr(server, "_send_here_branch_notification", lambda intent: notifications.append(intent) or {
        "ok": True,
        "status": "success",
        "messageId": "om-here-card",
    })
    send = lambda chat_id, text: sends.append((chat_id, text)) or {"ok": True, "messageId": f"reply-{len(sends)}"}

    normal = server._handle_feishu_chat_message_event(
        _body(message_id="om-before", text="请分析一下这条消息"),
        send_text=send,
    )
    here = server._handle_feishu_chat_message_event(
        _body(message_id="om-here", text="/here"),
        send_text=send,
    )

    assert normal["status"] == "completed"
    assert here["status"] == "success"
    assert len(dispatches) == 1
    assert len(notifications) == 1
    assert notifications[0]["topicContext"]["parentSourceMessageId"] == "om-here"
    assert notifications[0]["topicContext"]["context"][-1]["messageId"] == "om-before"
    assert sends[-1] == ("oc-private", "已发送到通知话题。")


def test_server_wires_private_change_to_topic_foreground_rejection(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    dispatches, notifications, sends = [], [], []
    monkeypatch.setattr(server, "_dispatch_representative_agent_message", lambda *args: dispatches.append(args) or {"ok": True, "reply": "ordinary"})
    monkeypatch.setattr(server, "_send_here_branch_notification", lambda intent: notifications.append(intent) or {"ok": True})

    result = server._handle_feishu_chat_message_event(
        _body(message_id="om-change", text="/change pro"),
        send_text=lambda chat_id, text: sends.append((chat_id, text)) or {"ok": True, "messageId": "reply-change"},
    )

    assert result["status"] == "unsupported_location"
    assert not dispatches
    assert not notifications
    assert "已激活的通知话题" in sends[-1][1]


def test_server_topic_agent_catalog_uses_roster_without_placeholder_defaults(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "refresh_agent_maps", lambda: None)
    monkeypatch.setattr(server, "get_roster", lambda: [
        {"id": "agent-a", "statusKey": "agent-a", "name": "Agent A"},
        {"id": "agent-b", "statusKey": "agent-b", "name": "Agent B", "profile": "profile-b"},
    ])

    assert server._configured_feishu_topic_agent_choices() == [
        {"label": "Agent A", "agentId": "agent-a"},
        {"label": "Agent B", "agentId": "agent-b", "aliases": ["profile-b"]},
    ]


def test_global_slash_flag_blocks_feishu_exact_command_before_agent_dispatch(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("VO_CHAT_SLASH_COMMANDS_ENABLED", "0")
    dispatches = []
    monkeypatch.setattr(server, "_dispatch_representative_agent_message", lambda *args: dispatches.append(args) or {"ok": True, "reply": "ordinary"})

    result = server._handle_feishu_chat_message_event(
        _body(message_id="om-disabled"),
        send_text=lambda *_args: {"ok": True, "messageId": "reply"},
    )

    assert result["status"] == "disabled"
    assert not dispatches
    assert "未发送给 Agent" in result["reply"]


def test_feishu_non_exact_slash_blocks_before_agent_dispatch(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    dispatches = []
    monkeypatch.setattr(server, "_dispatch_representative_agent_message", lambda *args: dispatches.append(args) or {"ok": True, "reply": "ordinary"})

    result = server._handle_feishu_chat_message_event(
        _body(message_id="om-slash-args", text="/new now"),
        send_text=lambda *_args: {"ok": True, "messageId": "reply"},
    )

    assert result["status"] == "slash_command_blocked"
    assert not dispatches
    assert "未发送给 Agent" in result["reply"]


def test_representative_bridge_blocks_slash_before_provider_bridge(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, provider="openclaw")
    monkeypatch.setattr(server.PROVIDER_CONVERSATION_SERVICE, "deliver_queued", lambda *args, **kwargs: pytest.fail("provider dispatch should not run"))

    result = server._dispatch_representative_agent_message(
        "representative",
        "/new",
        "feishu-dm:scope",
        {"sender": {"openId": "ou-actor"}, "sourceSurface": "feishu-dm"},
    )

    assert result["status"] == "slash_command_blocked"
    assert "was not sent to the Agent" in result["reply"]


def test_provider_entry_bridge_blocks_slash_before_specialized_bridge(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    calls = []

    def specialized(body):
        calls.append(body)
        return {"ok": True}

    for body in (
        {"agentId": "missing-codex", "conversationId": "conv", "message": "/new"},
        {"agentId": "missing-hermes", "conversationId": "conv", "message": "/new now"},
        {"agentId": "missing-claude", "conversationId": "conv", "message": "/compact"},
    ):
        result = server._handle_provider_chat_entry(body, specialized)
        assert result["status"] == "slash_command_blocked"
        assert result["_status"] == 400
    assert not calls


def test_orphaned_command_is_finalized_indeterminate_without_reexecution(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    started = {
        "id": "started-1",
        "event": "command_started",
        "sourceMessageId": "om-orphan",
        "conversationId": "feishu-dm:scope",
        "feishuChatId": "oc-private",
        "representativeAgentId": "representative",
        "chatType": "p2p",
        "messageType": "text",
        "command": "/compact",
    }
    feishu_chat_channel.save_source_index(
        str(tmp_path), started, now=lambda: 1, lock=server._FEISHU_CHANNEL_RECORD_LOCK, owner_id="old-owner"
    )
    monkeypatch.setattr(server, "_FEISHU_PROCESS_OWNER_ID", "new-owner")
    monkeypatch.setattr(server, "_feishu_chat_app_text_send", lambda *_args: {"ok": True, "messageId": "feedback"})
    recorded = []
    monkeypatch.setattr(server, "_record_feishu_channel_event", lambda row: recorded.append(row) or row)
    adapted = _body(message_id="om-orphan", text="/compact")

    result = server._finalize_orphaned_feishu_worker_message(
        adapted, {"messageId": "om-orphan", "requestId": "request-1"}
    )

    assert result["event"] == "command_completed"
    assert result["commandStatus"] == "indeterminate"
    assert result["commandResult"]["changed"] is False
    indexed = feishu_chat_channel.load_source_index(str(tmp_path), "om-orphan")
    assert indexed["state"] == "completed"


def test_feedback_failure_is_terminal_and_counted(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, provider="codex")
    monkeypatch.setattr(server, "_dispatch_feishu_chat_command", lambda *_args: {
        "ok": True, "status": "success", "changed": True, "reply": "已创建新会话"
    })
    before = list(server._CHAT_COMMAND_METRICS.snapshot())

    result = server._handle_feishu_chat_message_event(
        _body(message_id="om-feedback-failed"),
        send_text=lambda *_args: {"ok": False, "status": "timeout"},
    )

    assert result["status"] == "delivery_failed"
    indexed = feishu_chat_channel.load_source_index(str(tmp_path), "om-feedback-failed")
    assert indexed["state"] == "completed"
    after = server._CHAT_COMMAND_METRICS.snapshot()
    assert sum(row["count"] for row in after if row["status"] == "feedback_failed") > sum(
        row["count"] for row in before if row["status"] == "feedback_failed"
    )


def test_worker_accepts_command_completed_as_durable_terminal(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "_finalize_orphaned_feishu_worker_message", lambda *_args: None)
    monkeypatch.setattr(server, "_claim_feishu_source_message", lambda _message_id: True)
    monkeypatch.setattr(server, "_release_feishu_source_message", lambda _message_id: None)
    monkeypatch.setattr(server, "_handle_feishu_chat_message_event", lambda *_args, **_kwargs: {
        "ok": True,
        "status": "success",
        "record": {"id": "row-1", "event": "command_completed", "sourceMessageId": "om-worker"},
    })
    envelope = {
        "schema": "vo.feishu-chat.inbound/v1",
        "requestId": "request-1",
        "workerInstanceId": "worker-1",
        "transport": "channel-sdk-node",
        "attempt": 1,
        "message": {
            "messageId": "om-worker",
            "chatId": "oc-private",
            "chatType": "p2p",
            "rawContentType": "text",
            "content": "/new",
            "sender": {"openId": "ou-actor", "type": "user", "isBot": False},
        },
        "source": {},
    }

    result = server._handle_feishu_chat_worker_envelope(envelope)

    assert result["durable"] is True
    assert result["state"] == "success"


@pytest.mark.parametrize("provider", ["codex", "hermes", "claude-code", "openclaw"])
def test_representative_provider_matrix_uses_authoritative_agent_scope(monkeypatch, tmp_path, provider):
    _configure(monkeypatch, tmp_path, provider=provider)
    scopes = []

    class ProviderAdapter:
        def execute(self, command, scope):
            scopes.append((command.value, scope))
            return {"ok": True, "status": "success", "changed": True, "reply": "已创建新会话"}

    monkeypatch.setattr(server, "_chat_command_provider_adapter", lambda: ProviderAdapter())
    monkeypatch.setattr(server, "_chat_command_audit_lookup", lambda _request: None)
    monkeypatch.setattr(server, "_chat_command_audit_append", lambda _row: None)

    result = server._dispatch_feishu_chat_command("/new", {
        "sourceMessageId": f"om-{provider}",
        "sourceSurface": "feishu-group",
        "representativeAgentId": "representative",
        "conversationId": "feishu-group:trusted",
    })

    assert result["ok"] is True
    assert scopes[0][0] == "/new"
    assert scopes[0][1].provider_kind == provider
    assert scopes[0][1].agent_id == "representative"
    assert scopes[0][1].conversation_id == "feishu-group:trusted"
    assert scopes[0][1].surface == "feishu-group"


def test_public_status_exposes_only_bounded_command_flags_and_metrics(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    status = server._chat_command_status_response()
    config = server._feishu_chat_config_response(include_ok=False)

    assert status["enabled"] is True
    assert set(status["reservations"]) == {"scopes", "locked"}
    assert isinstance(status["metrics"], list)
    assert config["chatCommands"] == status
    assert "message" not in str(status).lower()
