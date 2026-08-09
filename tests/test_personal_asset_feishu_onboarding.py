import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_agent_auth import AuthenticatedPersonalAssetAgent  # noqa: E402
from services.personal_asset_feishu_onboarding import (  # noqa: E402
    PERSONAL_ASSET_FEISHU_FORM_ACTION,
    PersonalAssetFeishuOnboarding,
    build_personal_asset_feishu_form_intent,
)
from feishu_notifications import build_feishu_card  # noqa: E402


def source_body():
    return {
        "requestId": "form-1",
        "expectedRevision": 0,
        "sourceContext": {
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceMessageId": "om_source",
            "conversationId": "feishu:user:chat",
            "feishuChatId": "oc_chat",
            "chatType": "p2p",
            "ownerId": "ou_owner",
        },
    }


def test_form_intent_is_one_grouped_form_with_all_profile_types():
    intent = build_personal_asset_feishu_form_intent(
        agent_id="codex-local",
        request=source_body(),
    )

    assert intent["type"] == "application_form"
    assert intent["actions"][0]["value"]["action"] == PERSONAL_ASSET_FEISHU_FORM_ACTION
    sections = {item["section"] for item in intent["inputs"]}
    assert sections == {
        "基本信息",
        "职业与 VO 方向",
        "兴趣爱好",
        "聊天偏好",
        "办公室目标",
        "其他与可选敏感信息",
    }
    names = {item["name"] for item in intent["inputs"]}
    assert {
        "preferred_name",
        "language",
        "timezone",
        "current_role",
        "vo_direction",
        "interests",
        "chat_preferences",
        "office_goals",
        "financial_focus",
        "additional_profile",
    } <= names
    assert all(item["required"] is False for item in intent["inputs"])
    card = build_feishu_card(intent)
    assert card["msg_type"] == "interactive"


def test_open_form_delivers_card_without_writing_profile():
    delivered = []
    onboarding = PersonalAssetFeishuOnboarding(
        deliver_form=lambda message_id, intent: delivered.append((message_id, intent))
        or {"ok": True, "messageId": "om_card"},
    )

    result = onboarding.open_form(
        AuthenticatedPersonalAssetAgent("codex-local", "codex-local", "vo-runtime"),
        source_body(),
    )

    assert result["status"] == "form_delivered"
    assert result["cardMessageId"] == "om_card"
    assert delivered[0][0] == "om_source"


def test_submit_routes_non_empty_grouped_values_back_to_same_agent_for_confirmation():
    dispatched = []
    replies = []
    updates = []
    onboarding = PersonalAssetFeishuOnboarding(
        deliver_form=lambda *_args: {"ok": True},
        dispatch_agent=lambda agent_id, message, conversation_id, source_meta: dispatched.append(
            (agent_id, message, conversation_id, source_meta)
        )
        or {"ok": True, "reply": "请确认以上个人资产变更。"},
        deliver_reply=lambda message_id, text: replies.append((message_id, text))
        or {"ok": True},
        update_form=lambda message_id, intent: updates.append((message_id, intent))
        or {"ok": True},
        launch=lambda task: task(),
    )
    intent = build_personal_asset_feishu_form_intent("codex-local", source_body())
    value = intent["actions"][0]["value"]
    event = {
        "messageId": "om_card",
        "chatId": "oc_chat",
        "operator": {"openId": "ou_owner"},
        "action": {
            "value": value,
            "formValue": {
                "preferred_name": "小欧",
                "current_role": "产品经理",
                "interests": "编程、阅读",
                "financial_focus": "指数基金",
                "additional_profile": "偏好异步协作",
            },
        },
    }

    outcome = onboarding.handle_action(event, value)

    assert outcome["handled"] is True and outcome["queued"] is True
    assert dispatched[0][0] == "codex-local"
    assert dispatched[0][2] == "feishu:user:chat"
    assert "<personal_asset_form_submission>" in dispatched[0][1]
    assert "小欧" in dispatched[0][1]
    assert "指数基金" in dispatched[0][1]
    assert "confirmation_required" in dispatched[0][1]
    assert "中文 to 简体中文" in dispatched[0][1]
    assert "Asia/Shanghai" in dispatched[0][1]
    assert "original input" in dispatched[0][1]
    assert "inferred additions" in dispatched[0][1]
    assert "Do not guess low-confidence facts" in dispatched[0][1]
    assert replies == [("om_card", "请确认以上个人资产变更。")]
    assert [intent["state"] for _, intent in updates] == ["processing", "submitted"]
    assert updates[0][1]["inputs"] == []
    assert updates[0][1]["actions"] == []
    assert "正在生成确认摘要" in updates[0][1]["summary"]
    assert "等待你的明确确认" in updates[1][1]["summary"]
    for _, status_intent in updates:
        status_card = build_feishu_card(status_intent)
        assert status_card["card"]["schema"] == "2.0"
        assert "body" in status_card["card"]


def test_submit_rejects_wrong_actor_and_empty_form():
    launched = []
    onboarding = PersonalAssetFeishuOnboarding(
        deliver_form=lambda *_args: {"ok": True},
        launch=lambda task: launched.append(task),
    )
    intent = build_personal_asset_feishu_form_intent("codex-local", source_body())
    value = intent["actions"][0]["value"]

    wrong_actor = onboarding.handle_action(
        {
            "messageId": "om_card",
            "operator": {"openId": "ou_other"},
            "action": {"value": value, "formValue": {"preferred_name": "别人"}},
        },
        value,
    )
    empty = onboarding.handle_action(
        {
            "messageId": "om_card",
            "operator": {"openId": "ou_owner"},
            "action": {"value": value, "formValue": {}},
        },
        value,
    )

    assert wrong_actor["status"] == "actor_mismatch"
    assert empty["status"] == "empty_form"
    assert launched == []


def test_summary_failure_updates_card_to_retryable_error_state():
    updates = []
    replies = []
    onboarding = PersonalAssetFeishuOnboarding(
        deliver_form=lambda *_args: {"ok": True},
        dispatch_agent=lambda *_args: (_ for _ in ()).throw(RuntimeError("failed")),
        deliver_reply=lambda message_id, text: replies.append((message_id, text)) or {"ok": True},
        update_form=lambda message_id, intent: updates.append((message_id, intent)) or {"ok": True},
        launch=lambda task: task(),
    )
    value = build_personal_asset_feishu_form_intent("codex-local", source_body())["actions"][0]["value"]
    event = {
        "open_message_id": "om_card",
        "operator": {"open_id": "ou_owner"},
        "action": {"value": value, "form_value": {"preferred_name": "小欧"}},
    }

    outcome = onboarding.handle_action(event, value)

    assert outcome["queued"] is True
    assert updates[0][1]["state"] == "processing"
    assert updates[-1][1]["type"] == "error"
    assert "重新发起" in updates[-1][1]["summary"]
    assert build_feishu_card(updates[-1][1])["card"]["schema"] == "2.0"
    assert replies[-1][1].startswith("表单已收到，但确认摘要暂时无法生成")
