#!/usr/bin/env python3
"""Feishu original-channel notices are visible in the VO communication ledger."""

import json
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-feishu-notice-sync-import-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CODEX_CHAT_FAST_PATH_ENABLED", "0")

import server  # noqa: E402


def _comm_rows(status_dir):
    path = os.path.join(status_dir, "agent-platform-communications.jsonl")
    with open(path, "r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def test_original_channel_notice_syncs_to_visible_vo_reply_without_conversation_id():
    old_status_dir = server.STATUS_DIR
    with tempfile.TemporaryDirectory() as status_dir:
        server.STATUS_DIR = status_dir
        try:
            request = server._record_feishu_channel_event({
                "event": "user_message",
                "sourceMessageId": "om_notice",
                "conversationId": "feishu-dm:notice-user",
                "feishuChatId": "oc_notice",
                "representativeAgentId": "codex-local",
                "chatType": "p2p",
                "sourceSurface": "feishu-dm",
                "text": "问问分析师他现在有哪些 skill?",
                "sender": {"openId": "ou_notice_user", "name": "Notice User"},
            })
            notice = server._record_feishu_channel_event({
                "event": "original_channel_notice",
                "sourceMessageId": "om_notice",
                "feishuChatId": "oc_notice",
                "chatType": "p2p",
                "sourceSurface": "feishu-dm",
                "text": "我去问分析师他当前有哪些 skill，请稍等。",
                "sendResult": {"ok": True, "messageId": "om_notice_sent"},
            })
            server._record_feishu_channel_event({
                "event": "turn_completed",
                "sourceMessageId": "om_notice",
                "conversationId": "feishu-dm:notice-user",
                "feishuChatId": "oc_notice",
                "representativeAgentId": "codex-local",
                "chatType": "p2p",
                "sourceSurface": "feishu-dm",
                "text": "问问分析师他现在有哪些 skill?",
                "reply": "分析师当前有这些 skills。",
                "sendResult": {"ok": True, "messageId": "om_final_sent"},
                "agentResult": {"ok": True},
            })

            rows = _comm_rows(status_dir)
            notice_rows = [
                row for row in rows
                if row.get("direction") == "reply"
                and row.get("text") == "我去问分析师他当前有哪些 skill，请稍等。"
            ]
            assert request["conversationId"] == "feishu-dm:notice-user"
            assert notice["conversationId"] == "feishu-dm:notice-user"
            assert len(notice_rows) == 1
            assert notice_rows[0]["visibleInOffice"] is True
            assert notice_rows[0]["inReplyTo"]
            assert notice_rows[0]["metadata"]["event"] == "original_channel_notice"
            assert notice_rows[0]["metadata"]["feishuNoticeMessageId"] == "om_notice_sent"
            assert any(
                row.get("direction") == "reply"
                and row.get("text") == "分析师当前有这些 skills。"
                for row in rows
            )
            deliveries = [
                row for row in rows
                if row.get("type") == "operation"
                and row.get("operation") == "feishu_delivery"
            ]
            assert {row["metadata"].get("event") for row in deliveries} >= {
                "original_channel_notice",
                "turn_completed",
            }
        finally:
            server.STATUS_DIR = old_status_dir
