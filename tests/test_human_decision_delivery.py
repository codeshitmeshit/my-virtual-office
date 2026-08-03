from __future__ import annotations

from app.feishu_notifications import build_feishu_card
from app.services.human_decision_delivery import (
    HumanDecisionDelivery,
    build_decision_intent,
)

from tests.test_human_decisions import request_payload
from app.services.human_decisions import HumanDecisionStore


def decision(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    return store.create(request_payload())["decision"]


def test_pending_card_contains_abcd_custom_input_and_context(tmp_path):
    intent = build_decision_intent(decision(tmp_path))
    card = build_feishu_card(intent)
    assert intent["type"] == "application_form"
    assert [action["text"] for action in intent["actions"]] == ["A", "B", "C", "D", "提交自定义"]
    assert intent["inputs"][0]["name"] == "custom_answer"
    assert next(item["value"] for item in intent["details"] if item.get("label") == "情景") == "自测完成，需要决定上线范围。"
    form = next(item for item in card["card"]["body"]["elements"] if item["tag"] == "form")
    assert any(item.get("tag") == "input" for item in form["elements"])


def test_pending_card_renders_each_option_as_a_distinct_detail_block(tmp_path):
    card = build_feishu_card(build_decision_intent(decision(tmp_path)))
    markdown_blocks = [
        element["content"]
        for element in card["card"]["body"]["elements"]
        if element.get("tag") == "markdown"
    ]
    option_blocks = [
        content
        for content in markdown_blocks
        if any(content.startswith(f"**{option_id}｜") for option_id in "ABCD")
    ]

    assert option_blocks == [
        "**A｜全量**：影响：最快但风险最高",
        "**B｜灰度（VO 推荐）**：影响：先验证再扩大",
        "**C｜内部**：影响：风险最低",
        "**D｜暂缓**：影响：继续等待",
    ]
    for content in option_blocks:
        assert sum(f"**{option_id}｜" in content for option_id in "ABCD") == 1


def test_pending_card_separates_option_group_from_surrounding_details(tmp_path):
    elements = build_feishu_card(build_decision_intent(decision(tmp_path)))["card"]["body"]["elements"]

    risk_index = next(index for index, item in enumerate(elements) if item.get("content", "").startswith("**风险 / 紧急度**"))
    option_a_index = next(index for index, item in enumerate(elements) if item.get("content", "").startswith("**A｜"))
    option_d_index = next(index for index, item in enumerate(elements) if item.get("content", "").startswith("**D｜"))
    recommendation_index = next(index for index, item in enumerate(elements) if item.get("content", "").startswith("**VO 推荐**"))

    assert elements[risk_index + 1] == {"tag": "hr"}
    assert option_a_index == risk_index + 2
    assert elements[option_d_index + 1] == {"tag": "hr"}
    assert recommendation_index == option_d_index + 2


def test_notification_bot_is_preferred_without_duplicate_chat_send(tmp_path):
    calls = []

    def send(intent, **kwargs):
        calls.append(kwargs["app_config"])
        return {"ok": True, "status": "sent", "messageId": "om_notification"}

    delivery = HumanDecisionDelivery(send=send, update=lambda *args, **kwargs: {})
    result = delivery.deliver(
        decision(tmp_path),
        notification_config={"appId": "notification", "appSecret": "secret", "receiveIdType": "chat_id", "receiveId": "oc_notification"},
        chat_config={"appId": "chat", "appSecret": "secret"},
        fallback_chat_id="oc_chat",
    )
    assert result["application"] == "notification"
    assert [item["appId"] for item in calls] == ["notification"]


def test_missing_notification_bot_falls_back_to_chat_bot(tmp_path):
    calls = []

    def send(intent, **kwargs):
        calls.append(kwargs["app_config"])
        return {"ok": True, "status": "sent", "messageId": "om_chat"}

    delivery = HumanDecisionDelivery(send=send, update=lambda *args, **kwargs: {})
    result = delivery.deliver(
        decision(tmp_path),
        notification_config={"appId": "notification", "appSecret": ""},
        chat_config={"appId": "chat", "appSecret": "secret"},
        fallback_chat_id="oc_chat",
    )
    assert result["application"] == "chat"
    assert calls == [{"appId": "chat", "appSecret": "secret", "receiveIdType": "chat_id", "receiveId": "oc_chat"}]


def test_configured_notification_failure_does_not_cross_send(tmp_path):
    calls = []

    def send(intent, **kwargs):
        calls.append(kwargs["app_config"]["appId"])
        return {"ok": False, "status": "network_error"}

    result = HumanDecisionDelivery(send=send, update=lambda *args, **kwargs: {}).deliver(
        decision(tmp_path),
        notification_config={"appId": "notification", "appSecret": "secret", "receiveId": "oc_notification"},
        chat_config={"appId": "chat", "appSecret": "secret"},
        fallback_chat_id="oc_chat",
    )
    assert result["application"] == "notification"
    assert calls == ["notification"]


def test_terminal_update_removes_actions_and_uses_original_application(tmp_path):
    updates = []

    def update(message_id, intent, **kwargs):
        updates.append((message_id, intent, kwargs["app_config"]))
        return {"ok": True, "status": "updated"}

    store = HumanDecisionStore(tmp_path / "state.json")
    item = store.create(request_payload())["decision"]
    item = store.resolve(item["id"], option_id="B", channel="feishu")["decision"]
    delivery = HumanDecisionDelivery(send=lambda *args, **kwargs: {}, update=update)
    results = delivery.update_terminal(
        item,
        [{"application": "chat", "messageId": "om_chat"}],
        notification_config={"appId": "notification", "appSecret": "n"},
        chat_config={"appId": "chat", "appSecret": "c"},
    )
    assert results[0]["ok"] is True
    assert updates[0][0] == "om_chat"
    assert updates[0][1]["actions"] == []
    assert updates[0][1]["inputs"], "terminal card must remain schema 2.0 so Feishu can patch the original form card"
    assert build_feishu_card(updates[0][1])["card"]["schema"] == "2.0"
    assert updates[0][2]["appId"] == "chat"
