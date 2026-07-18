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
    monkeypatch.setenv("VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED", "1")


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


def test_disabled_feishu_flag_preserves_ordinary_message_behavior(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED", "0")
    dispatches = []
    monkeypatch.setattr(server, "_dispatch_representative_agent_message", lambda *args: dispatches.append(args) or {"ok": True, "reply": "ordinary"})

    result = server._handle_feishu_chat_message_event(
        _body(message_id="om-disabled"),
        send_text=lambda *_args: {"ok": True, "messageId": "reply"},
    )

    assert result["status"] == "completed"
    assert len(dispatches) == 1 and dispatches[0][1] == "/new"


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
    assert status["feishuEnabled"] is True
    assert set(status["reservations"]) == {"scopes", "locked"}
    assert isinstance(status["metrics"], list)
    assert config["chatCommands"] == status
    assert "message" not in str(status).lower()
