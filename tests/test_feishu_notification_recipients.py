import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.feishu_notification_recipients import (  # noqa: E402
    app_config_for_notification_recipient,
    recipient_from_intent,
)


BASE_APP_CONFIG = {
    "appId": "cli_demo",
    "appSecret": "secret",
    "receiveIdType": "chat_id",
    "receiveId": "oc_default",
}


def test_fixed_policy_keeps_configured_chat_target():
    result = app_config_for_notification_recipient(
        BASE_APP_CONFIG,
        {"notificationRecipientPolicy": "fixed"},
        {"sourceActor": {"openId": "ou_actor"}},
    )

    assert result["receiveIdType"] == "chat_id"
    assert result["receiveId"] == "oc_default"


def test_originating_user_policy_overrides_to_explicit_dm_recipient():
    result = app_config_for_notification_recipient(
        BASE_APP_CONFIG,
        {"notificationRecipientPolicy": "originating_user_dm"},
        {
            "feishuRecipient": {
                "receiveIdType": "open_id",
                "receiveId": "ou_explicit",
            },
            "sourceActor": {"unionId": "on_actor"},
        },
    )

    assert result["receiveIdType"] == "open_id"
    assert result["receiveId"] == "ou_explicit"


def test_originating_user_policy_prefers_cross_app_identity_fields():
    result = app_config_for_notification_recipient(
        BASE_APP_CONFIG,
        {"notificationRecipientPolicy": "originating_user_dm"},
        {
            "sourceActor": {
                "openId": "ou_actor",
                "userId": "u_actor",
                "unionId": "on_actor",
            },
        },
    )

    assert result["receiveIdType"] == "union_id"
    assert result["receiveId"] == "on_actor"


def test_originating_user_policy_reads_nested_sender_identity():
    result = recipient_from_intent({
        "sender": {
            "sender_id": {
                "open_id": "ou_sender",
            },
        },
    })

    assert result is not None
    assert result.receive_id_type == "open_id"
    assert result.receive_id == "ou_sender"


def test_originating_user_policy_clears_fixed_target_when_identity_missing():
    result = app_config_for_notification_recipient(
        BASE_APP_CONFIG,
        {"notificationRecipientPolicy": "originating_user_dm"},
        {"related": {"type": "project", "id": "p1"}},
    )

    assert result["receiveIdType"] == "chat_id"
    assert result["receiveId"] == ""
