#!/usr/bin/env python3
"""Feishu rich post messages with text are handled as normal chat input."""

import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-feishu-rich-post-import-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CODEX_CHAT_FAST_PATH_ENABLED", "0")

import server  # noqa: E402


def test_feishu_worker_rich_post_text_dispatches_as_chat_message():
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-rich-post-")
    body = {
        "schema": "vo.feishu-chat.inbound/v1",
        "requestId": "req-rich-post",
        "workerInstanceId": "worker-rich-post",
        "transport": "channel-sdk-node",
        "attempt": 1,
        "receivedAt": 1785504050000,
        "message": {
            "messageId": "om_rich_post_text",
            "chatId": "oc_rich_post_text",
            "chatType": "p2p",
            "content": {
                "title": "",
                "content": [
                    [{"tag": "text", "text": "他这次回复里没有列出 "}],
                    [
                        {"tag": "text", "text": "tushare-data"},
                        {"tag": "text", "text": "、valuation-calculator、wechat-feeds"},
                    ],
                    [{"tag": "text", "text": "你帮我确认一下？"}],
                ],
            },
            "rawContentType": "post",
            "resources": [],
            "sender": {
                "openId": "ou_rich_post_user",
                "name": "Rich Post User",
                "type": "user",
                "isBot": False,
            },
        },
        "source": {"eventId": "evt-rich-post"},
    }

    adapted, _ = server._adapt_feishu_chat_inbound_envelope(body)
    message = adapted["event"]["message"]
    assert message["message_type"] == "text"
    assert "tushare-data" in message["text"]
    assert "你帮我确认一下" in message["text"]

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "groupChatEnabled": False,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "codex-local",
                "transportImplementation": "channel-sdk-node",
            },
            "bindings": {},
        },
    }
    dispatches = []

    def fake_dispatch(agent_id, text, conversation_id, source_meta):
        dispatches.append({
            "agentId": agent_id,
            "text": text,
            "conversationId": conversation_id,
            "sourceMeta": source_meta,
        })
        return {"ok": True, "reply": "确认回复", "conversationId": conversation_id}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event(
            adapted,
            send_text=lambda chat_id, text: {"ok": True, "status": "sent", "messageId": "om_rich_reply"},
        )
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["status"] == "completed"
    assert dispatches[0]["agentId"] == "codex-local"
    assert "tushare-data" in dispatches[0]["text"]
    assert dispatches[0]["sourceMeta"]["messageType"] == "text"
