"""Routing policy for detailed agent follow-up replies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_LONG_TASK_THRESHOLD_MS = 180_000
DEFAULT_SUMMARY_LIMIT = 360


@dataclass(frozen=True)
class FollowupDelivery:
    should_notify: bool
    reason: str
    chat_reply: str
    markdown: str


def _text(value: Any, limit: int = 0) -> str:
    text = str(value or "").strip()
    if limit > 0:
        return text[:limit]
    return text


def _is_feishu_source(source_meta: dict[str, Any]) -> bool:
    return _text(source_meta.get("sourceApp")).lower() == "feishu"


def _first_paragraph(text: str, limit: int) -> str:
    compact = " ".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."


def _field(label: str, value: Any) -> str:
    text = _text(value)
    return f"- **{label}**：{text}" if text else ""


def build_followup_markdown(
    *,
    agent_id: str,
    conversation_id: str,
    prompt_text: str,
    reply: str,
    source_meta: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    late: bool = False,
) -> str:
    source_meta = source_meta if isinstance(source_meta, dict) else {}
    result = result if isinstance(result, dict) else {}
    lines = [
        "## Agent 详细结果",
        "",
        _field("Agent", agent_id),
        _field("会话", conversation_id),
        _field("状态", result.get("status") or ("completed" if result.get("ok", True) else "failed")),
        _field("来源", source_meta.get("sourceLabel") or source_meta.get("sourceSurface") or source_meta.get("channel")),
        _field("原消息", source_meta.get("sourceMessageId")),
        _field("投递类型", "迟到完整回复" if late else "长耗时分流"),
        "",
        "### 原始请求",
        "",
        _text(prompt_text) or "（无文本）",
        "",
        "### 完整回复",
        "",
        _text(reply) or "（无文本）",
    ]
    return "\n".join(line for line in lines if line is not None)


def prepare_followup_delivery(
    *,
    agent_id: str,
    conversation_id: str,
    prompt_text: str,
    reply: str,
    source_meta: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    late: bool = False,
    elapsed_ms: int | float | None = None,
    long_task_threshold_ms: int = DEFAULT_LONG_TASK_THRESHOLD_MS,
    summary_limit: int = DEFAULT_SUMMARY_LIMIT,
) -> FollowupDelivery:
    source_meta = source_meta if isinstance(source_meta, dict) else {}
    result = result if isinstance(result, dict) else {}
    reply_text = _text(reply)
    if not _is_feishu_source(source_meta) or not reply_text:
        return FollowupDelivery(False, "", "", "")
    duration_ms = 0.0
    try:
        duration_ms = float(elapsed_ms or result.get("elapsedMs") or result.get("durationMs") or 0)
    except (TypeError, ValueError):
        duration_ms = 0.0
    reason = "late_reply" if late else ("long_task" if duration_ms >= long_task_threshold_ms else "")
    if not reason:
        return FollowupDelivery(False, "", "", "")
    summary = _first_paragraph(reply_text, summary_limit)
    chat_reply = (
        "分析师这次处理时间较长，完整结果已转到通知应用；这里保留简版：\n\n"
        f"{summary}"
    )
    markdown = build_followup_markdown(
        agent_id=agent_id,
        conversation_id=conversation_id,
        prompt_text=prompt_text,
        reply=reply_text,
        source_meta=source_meta,
        result=result,
        late=late,
    )
    return FollowupDelivery(True, reason, chat_reply, markdown)


def with_notification_status(chat_reply: str, notification_result: dict[str, Any] | None) -> str:
    result = notification_result if isinstance(notification_result, dict) else {}
    if result.get("ok"):
        return chat_reply
    status = _text(result.get("status") or result.get("error") or "未配置通知应用", 80)
    return f"{chat_reply}\n\n通知应用暂时未送达（{status}），完整结果已保留在 VO 记录里。"
