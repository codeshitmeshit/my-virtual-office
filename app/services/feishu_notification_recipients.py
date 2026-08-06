"""Recipient policy for Feishu notification App sends."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


FIXED_RECIPIENT_POLICY = "fixed"
ORIGINATING_USER_DM_POLICY = "originating_user_dm"
SUPPORTED_RECIPIENT_POLICIES = frozenset(
    {FIXED_RECIPIENT_POLICY, ORIGINATING_USER_DM_POLICY}
)
SUPPORTED_RECEIVE_ID_TYPES = frozenset(
    {"open_id", "user_id", "union_id", "email", "chat_id"}
)


@dataclass(frozen=True, slots=True)
class FeishuNotificationRecipient:
    receive_id_type: str
    receive_id: str
    source: str

    def to_app_config(self, base: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(base or {})
        result["receiveIdType"] = self.receive_id_type
        result["receiveId"] = self.receive_id
        return result


def normalize_recipient_policy(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SUPPORTED_RECIPIENT_POLICIES else FIXED_RECIPIENT_POLICY


def _text(value: Any, limit: int = 300) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _explicit_recipient(intent: Mapping[str, Any]) -> FeishuNotificationRecipient | None:
    raw = _mapping(intent.get("feishuRecipient") or intent.get("notificationRecipient"))
    receive_id_type = _text(raw.get("receiveIdType") or raw.get("receive_id_type"), 40)
    receive_id = _text(raw.get("receiveId") or raw.get("receive_id"), 300)
    if receive_id_type in SUPPORTED_RECEIVE_ID_TYPES and receive_id:
        return FeishuNotificationRecipient(receive_id_type, receive_id, "explicit")
    return None


def _identity_candidates(intent: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    candidates: list[tuple[str, Mapping[str, Any]]] = []
    for key in (
        "sourceActor",
        "actorIds",
        "sender",
        "operator",
        "user",
        "requester",
        "recipient",
    ):
        value = _mapping(intent.get(key))
        if value:
            candidates.append((key, value))

    topic_context = _mapping(intent.get("topicContext"))
    for key in ("sourceActor", "actorIds", "sender", "user"):
        value = _mapping(topic_context.get(key))
        if value:
            candidates.append((f"topicContext.{key}", value))

    return tuple(candidates)


def _nested_identity(identity: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = _mapping(identity.get("sender_id") or identity.get("senderId"))
    return nested or identity


def recipient_from_intent(intent: Mapping[str, Any]) -> FeishuNotificationRecipient | None:
    explicit = _explicit_recipient(intent)
    if explicit:
        return explicit

    for source, raw_identity in _identity_candidates(intent):
        identity = _nested_identity(raw_identity)
        for receive_id_type, keys in (
            ("union_id", ("unionId", "union_id")),
            ("user_id", ("userId", "user_id")),
            ("open_id", ("openId", "open_id")),
            ("email", ("email",)),
        ):
            for key in keys:
                value = _text(identity.get(key), 300)
                if value:
                    return FeishuNotificationRecipient(receive_id_type, value, source)
    return None


def app_config_for_notification_recipient(
    base_app_config: Mapping[str, Any],
    notification_config: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    base = dict(base_app_config or {})
    policy = normalize_recipient_policy(
        notification_config.get("notificationRecipientPolicy")
        or notification_config.get("feishuRecipientPolicy")
    )
    if policy != ORIGINATING_USER_DM_POLICY:
        return base

    recipient = recipient_from_intent(intent if isinstance(intent, Mapping) else {})
    if not recipient:
        base["receiveId"] = ""
        return base
    return recipient.to_app_config(base)
