"""Pre-render promotion layer for provider-visible bridge prompts."""

from __future__ import annotations

from typing import Any, Mapping


_PROVIDER_LABELS = {
    "openclaw": "OpenClaw",
    "hermes": "Hermes",
    "codex": "Codex",
    "claude-code": "Claude Code",
}


def provider_label(provider_kind: object) -> str:
    value = str(provider_kind or "").strip().lower()
    return _PROVIDER_LABELS.get(value, value.replace("-", " ").title() or "Agent")


def bridge_source_label(source_app: object, source_surface: object, source_label: object = "") -> str:
    label = str(source_label or "").strip()
    if label:
        return label
    app = str(source_app or "virtual-office").strip() or "virtual-office"
    surface = str(source_surface or "chat-window").strip() or "chat-window"
    if app == "virtual-office" and surface in {"chat-window", "chat"}:
        return "Virtual Office Chat"
    return f"{app.replace('-', ' ').title()} {surface.replace('-', ' ').title()}".strip()


def agent_sender_label(agent_ref: Mapping[str, Any]) -> str:
    label = provider_label(agent_ref.get("providerKind"))
    base_name = f"{agent_ref.get('name') or agent_ref.get('id') or 'Agent'} {agent_ref.get('emoji') or ''}".strip()
    return f"{label}: {base_name}" if label else base_name


def promote_bridge_prompt_input(
    *,
    provider_kind: object = "",
    message: object,
    from_id: object = "user",
    from_name: object = "User",
    to_id: object = "",
    is_user: bool = True,
    source_app: object = "virtual-office",
    source_surface: object = "chat-window",
    source_label: object = "",
    source_message_id: object = "",
    reply_instruction: object = "Reply directly to the sender. Keep the reply concise unless detail is needed.",
    include_vo_routing_guidance: bool = False,
    attachments: object = "",
    body: Mapping[str, Any] | None = None,
    agent: Mapping[str, Any] | None = None,
    agent_key: object = "",
) -> dict[str, Any]:
    """Promote loose business inputs into the canonical bridge prompt shape."""

    body = body if isinstance(body, Mapping) else {}
    app = str(body.get("sourceApp") or body.get("app") or source_app or "virtual-office").strip() or "virtual-office"
    surface = str(body.get("sourceSurface") or body.get("surface") or source_surface or "chat-window").strip() or "chat-window"
    label = bridge_source_label(app, surface, body.get("sourceLabel") or source_label)
    sender_name = str(
        body.get("fromDisplayName")
        or body.get("displayName")
        or body.get("fromName")
        or from_name
        or "User"
    ).strip() or "User"
    sender_id = body.get("fromId") or body.get("fromUserId") or from_id or "user"
    target_id = (agent or {}).get("id") or agent_key or body.get("agentId") or to_id or ""
    promoted: dict[str, Any] = {
        "provider_kind": str(provider_kind or "").strip().lower(),
        "metadata": {
            "from_id": sender_id,
            "from_name": sender_name,
            "to_id": target_id,
            "is_user": bool(is_user),
            "source_app": app,
            "source_surface": surface,
            "source_label": label,
            "source_message_id": body.get("sourceMessageId") or source_message_id or "",
            "conversation_id": body.get("conversationId") or "",
            "feishu_chat_id": body.get("feishuChatId") or "",
            "chat_type": body.get("chatType") or "",
        },
        "message": message,
        "reply_instruction": str(reply_instruction or "").strip()
        or "Reply directly to the sender. Keep the reply concise unless detail is needed.",
        "include_vo_routing_guidance": bool(include_vo_routing_guidance),
        "attachments": attachments,
    }
    if surface == "feishu-group":
        promoted["feishu_group"] = {
            "speaker_name": body.get("fromDisplayName") or sender_name or "Feishu User",
            "speaker_id": body.get("fromUserId") or sender_id or "feishu-user",
            "source_message_id": body.get("sourceMessageId") or source_message_id or "",
        }
    return promoted


def promote_provider_delivery_prompt(
    provider_kind: object,
    message: object,
    body: Mapping[str, Any] | None = None,
    *,
    agent: Mapping[str, Any] | None = None,
    agent_key: object = "",
    attachment_context: object = "",
) -> dict[str, Any]:
    """Promote provider-chat request data before common bridge rendering."""

    return promote_bridge_prompt_input(
        provider_kind=provider_kind,
        message=message,
        body=body,
        agent=agent,
        agent_key=agent_key,
        from_id=(body or {}).get("fromUserId") if isinstance(body, Mapping) else "user",
        from_name=(body or {}).get("fromDisplayName") if isinstance(body, Mapping) else "User",
        to_id=(agent or {}).get("id") or agent_key,
        is_user=True,
        reply_instruction=(
            "Reply directly to the user. Do not assume the user's name unless they identify themselves."
        ),
        include_vo_routing_guidance=True,
        attachments=attachment_context,
    )


__all__ = [
    "agent_sender_label",
    "bridge_source_label",
    "promote_bridge_prompt_input",
    "promote_provider_delivery_prompt",
    "provider_label",
]
