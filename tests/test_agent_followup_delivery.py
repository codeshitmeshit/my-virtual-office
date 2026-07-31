import os
import sys
import threading


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import feishu_chat_channel  # noqa: E402
from app.services import agent_followup_delivery  # noqa: E402


def test_prepare_followup_delivery_keeps_fast_long_reply_in_chat():
    reply = "结论：" + ("长文本" * 360)
    delivery = agent_followup_delivery.prepare_followup_delivery(
        agent_id="market-analyst",
        conversation_id="conv-1",
        prompt_text="分析一下公司近况",
        reply=reply,
        source_meta={"sourceApp": "feishu", "sourceMessageId": "om-1"},
        result={"ok": True, "status": "completed"},
        elapsed_ms=3_000,
    )

    assert delivery.should_notify is False


def test_prepare_followup_delivery_routes_slow_feishu_reply_to_notification():
    reply = "分析结果已经完成。"
    delivery = agent_followup_delivery.prepare_followup_delivery(
        agent_id="market-analyst",
        conversation_id="conv-1",
        prompt_text="分析一下公司近况",
        reply=reply,
        source_meta={"sourceApp": "feishu", "sourceMessageId": "om-1"},
        result={"ok": True, "status": "completed"},
        elapsed_ms=181_000,
    )

    assert delivery.should_notify is True
    assert delivery.reason == "long_task"
    assert "通知应用" in delivery.chat_reply
    assert "### 完整回复" in delivery.markdown
    assert reply in delivery.markdown


def test_prepare_followup_delivery_keeps_short_feishu_reply_in_chat():
    delivery = agent_followup_delivery.prepare_followup_delivery(
        agent_id="market-analyst",
        conversation_id="conv-1",
        prompt_text="一句话说明",
        reply="已经处理完成。",
        source_meta={"sourceApp": "feishu", "sourceMessageId": "om-1"},
        result={"ok": True, "status": "completed"},
    )

    assert delivery.should_notify is False
    assert delivery.chat_reply == ""


def test_prepare_followup_delivery_routes_late_reply_even_when_short():
    delivery = agent_followup_delivery.prepare_followup_delivery(
        agent_id="market-analyst",
        conversation_id="conv-1",
        prompt_text="稍后给我结果",
        reply="这是迟到的完整结果。",
        source_meta={"sourceApp": "feishu", "sourceMessageId": "om-1"},
        result={"ok": True, "status": "completed"},
        late=True,
    )

    assert delivery.should_notify is True
    assert delivery.reason == "late_reply"


def test_feishu_chat_channel_prefers_short_chat_reply_from_agent_result():
    sent = []
    records = []

    def record_event(record):
        stored = {"id": f"record-{len(records) + 1}", **record}
        records.append(stored)
        return stored

    result = feishu_chat_channel.handle_message_event(
        {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om-long",
                    "chat_id": "oc-chat",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": {"text": "请分析这家公司"},
                },
            }
        },
        cfg={
            "enabled": True,
            "appId": "cli_test",
            "appSecret": "secret",
            "representativeAgentId": "market-analyst",
        },
        bindings={},
        load_records=lambda: [],
        idempotency_hit=lambda _message_id: None,
        record_event=record_event,
        lock_for=lambda _conversation_id: threading.Lock(),
        dispatch_agent=lambda *_args: {
            "ok": True,
            "reply": "完整结果" * 300,
            "feishuChatReply": "处理时间较长，完整结果已发送到通知应用。",
        },
        send_text=lambda _chat_id, text: sent.append(text) or {"ok": True, "messageId": "om-reply"},
        reply_text=None,
        find_agent=lambda _agent_id: {"id": "market-analyst", "name": "分析师"},
        add_reaction=lambda *_args: {"ok": True, "reactionId": "reaction-1"},
        delete_reaction=lambda *_args: {"ok": True},
    )

    assert result["ok"] is True
    assert sent == ["处理时间较长，完整结果已发送到通知应用。"]
    completed = next(record for record in records if record.get("event") == "turn_completed")
    assert completed["feishuReply"] == "处理时间较长，完整结果已发送到通知应用。"
    assert completed["reply"].startswith("完整结果")


if __name__ == "__main__":
    test_prepare_followup_delivery_keeps_fast_long_reply_in_chat()
    test_prepare_followup_delivery_routes_slow_feishu_reply_to_notification()
    test_prepare_followup_delivery_keeps_short_feishu_reply_in_chat()
    test_prepare_followup_delivery_routes_late_reply_even_when_short()
    test_feishu_chat_channel_prefers_short_chat_reply_from_agent_result()
