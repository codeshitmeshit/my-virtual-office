"""Delivery policy for Feishu notification App and webhook sends."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.feishu_notification_recipients import (
    ORIGINATING_USER_DM_POLICY,
    app_config_for_notification_recipient,
    normalize_recipient_policy,
)
from feishu_notifications import (
    send_feishu_markdown_message,
    send_feishu_notification,
)


def notification_delivery_options(
    *,
    base_app_config: Mapping[str, Any],
    notification_config: Mapping[str, Any],
    intent: Mapping[str, Any],
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Resolve the only allowed notification delivery target for an intent."""
    app_config = app_config_for_notification_recipient(
        base_app_config,
        notification_config,
        intent if isinstance(intent, Mapping) else {},
    )
    resolved_webhook_url = webhook_url or notification_config.get("feishuWebhook") or None
    policy = normalize_recipient_policy(
        notification_config.get("notificationRecipientPolicy")
        or notification_config.get("feishuRecipientPolicy")
    )
    if policy == ORIGINATING_USER_DM_POLICY and not app_config.get("receiveId"):
        resolved_webhook_url = None
    return {
        "app_config": app_config,
        "webhook_url": resolved_webhook_url,
    }


def send_notification_card(
    intent: Mapping[str, Any],
    *,
    notification_config: Mapping[str, Any],
    base_app_config: Mapping[str, Any],
    status_dir: str | None = None,
    webhook_url: str | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """Send a Feishu notification card through the centralized target policy."""
    delivery = notification_delivery_options(
        base_app_config=base_app_config,
        notification_config=notification_config,
        intent=intent,
        webhook_url=webhook_url,
    )
    return send_feishu_notification(
        dict(intent or {}),
        webhook_url=delivery["webhook_url"],
        app_config=delivery["app_config"],
        status_dir=status_dir,
        timeout=timeout,
    )


def send_notification_markdown(
    text: Any,
    *,
    notification_config: Mapping[str, Any],
    base_app_config: Mapping[str, Any],
    recipient_intent: Mapping[str, Any],
    timeout: int = 10,
) -> dict[str, Any]:
    """Send a Feishu markdown notification through the centralized target policy."""
    delivery = notification_delivery_options(
        base_app_config=base_app_config,
        notification_config=notification_config,
        intent=recipient_intent,
        webhook_url=notification_config.get("feishuWebhook") or None,
    )
    app_config = delivery["app_config"]
    return send_feishu_markdown_message(
        text,
        app_config=app_config,
        receive_id=app_config.get("receiveId") or "",
        receive_id_type=app_config.get("receiveIdType") or "chat_id",
        timeout=timeout,
    )
