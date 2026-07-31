#!/usr/bin/env python3
"""Feishu original-channel progress notice endpoint service coverage."""

from app.services.feishu_original_channel_notice import send_original_channel_notice


def test_private_notice_sends_to_feishu_chat_id_and_records():
    calls = []
    records = []

    result = send_original_channel_notice(
        {
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "feishuChatId": "oc_dm",
            "sourceMessageId": "om_dm",
            "conversationId": "feishu-dm:demo",
            "text": "我去问分析师，请稍等。",
        },
        command_sender=lambda op, payload: calls.append((op, payload)) or {"ok": True, "status": "sent", "messageId": "om_notice"},
        record_event=lambda row: records.append(row) or {"id": "row-1", **row},
    )

    assert result["ok"] is True
    assert calls == [("send", {"to": "oc_dm", "content": "我去问分析师，请稍等。", "contentType": "text"})]
    assert records[0]["event"] == "original_channel_notice"
    assert records[0]["feishuChatId"] == "oc_dm"
    assert records[0]["conversationId"] == "feishu-dm:demo"
    assert records[0]["sourceSurface"] == "feishu-dm"


def test_group_notice_replies_to_source_message():
    calls = []

    result = send_original_channel_notice(
        {
            "sourceApp": "feishu",
            "sourceSurface": "feishu-group",
            "chatType": "group",
            "feishuChatId": "oc_group",
            "sourceMessageId": "om_group",
            "text": "我去问 Hermes，请稍等。",
            "replyInThread": True,
        },
        command_sender=lambda op, payload: calls.append((op, payload)) or {"ok": True, "status": "sent"},
    )

    assert result["ok"] is True
    assert calls == [(
        "reply",
        {
            "to": "oc_group",
            "content": "我去问 Hermes，请稍等。",
            "contentType": "text",
            "messageId": "om_group",
            "replyInThread": True,
        },
    )]


def test_notice_requires_safe_source_context():
    assert send_original_channel_notice({"sourceApp": "slack", "feishuChatId": "oc", "text": "x"}, command_sender=lambda *_: {})["status"] == "unsupported_source_app"
    assert send_original_channel_notice({"sourceApp": "feishu", "text": "x"}, command_sender=lambda *_: {})["status"] == "missing_feishu_chat_id"
    assert send_original_channel_notice({"sourceApp": "feishu", "sourceSurface": "feishu-group", "feishuChatId": "oc", "text": "x"}, command_sender=lambda *_: {})["status"] == "missing_source_message_id"
