"""Prompt values for bridge interim status notices."""

from __future__ import annotations

from typing import Any, Mapping

from services import bridge_input_output_formatting as prompt_formatter


def original_channel_interim_notice_values(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return trusted rules for optional interim updates on the source channel."""

    source_app = str(metadata.get("source_app") or "virtual-office").strip() or "virtual-office"
    source_surface = str(metadata.get("source_surface") or "chat-window").strip() or "chat-window"
    source_label = str(metadata.get("source_label") or "").strip()
    source_message_id = str(metadata.get("source_message_id") or "").strip()
    conversation_id = str(metadata.get("conversation_id") or "").strip()
    feishu_chat_id = str(metadata.get("feishu_chat_id") or "").strip()
    chat_type = str(metadata.get("chat_type") or "").strip()
    return {
        "trigger": prompt_formatter.trusted_text(
            "If this request requires contacting another VO Agent, send a brief "
            "user-visible interim status update on the original channel before "
            "calling the VO agent communication endpoint. This applies even when "
            "the other Agent is expected to reply quickly."
        ),
        "channel": prompt_formatter.section(
            "channel",
            prompt_formatter.untrusted_text(source_label),
            attrs={"app": source_app, "surface": source_surface},
        ),
        "source_context": prompt_formatter.section(
            "source_context",
            "",
            attrs={
                "sourceMessageId": source_message_id,
                "conversationId": conversation_id,
                "feishuChatId": feishu_chat_id,
                "chatType": chat_type,
            },
        ),
        "feishu_endpoint": prompt_formatter.trusted_text(
            "When source_context app/surface indicate Feishu and feishuChatId is present, "
            "POST the interim text to `/api/feishu-chat/original-channel-notice` before "
            "contacting the other VO Agent. Include sourceApp, sourceSurface, "
            "sourceMessageId, conversationId, feishuChatId, chatType, and text from this prompt context."
        ),
        "agent_communication_context": prompt_formatter.trusted_text(
            "When you subsequently call `/api/agent-platform-communications/send`, carry the same "
            "sourceApp, sourceSurface, sourceMessageId, feishuChatId, chatType, sourceLabel, and "
            "original Feishu conversationId in that request. Put them at top level when possible, "
            "or inside metadata if the calling tool only allows metadata. This lets VO route timeout "
            "and late-completion behavior back to the original Feishu conversation instead of letting "
            "the calling Agent answer on behalf of the requested Agent."
        ),
        "agent_reply_presentation": prompt_formatter.trusted_text(
            "When the requested VO Agent returns a completed reply, present that Agent's result as "
            "the primary source. Quote or preserve the Agent's key original conclusion first, clearly "
            "label it as the requested Agent's reply, and only then add your own brief follow-up "
            "thinking in a separate section. Do not silently rewrite the Agent reply as if it were "
            "your own conclusion."
        ),
        "action": prompt_formatter.trusted_text(
            "Use the same original communication channel that delivered this message "
            "when the runtime provides that route."
        ),
        "message_shape": prompt_formatter.trusted_text(
            "Keep the interim update brief and user-visible: say the sender should "
            "wait while you work, or say that the message has been sent to the "
            "relevant VO/Agent."
        ),
        "skip_rule": prompt_formatter.trusted_text(
            "Do not send an interim update only for direct replies that do not contact "
            "another VO Agent, or when no source-channel route/context is available."
        ),
    }


__all__ = ["original_channel_interim_notice_values"]
