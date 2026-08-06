"""User-facing receipt emitted after a human-decision continuation resumes."""

from __future__ import annotations

from typing import Any, Callable, Protocol


JsonDict = dict[str, Any]


class ReceiptDelivery(Protocol):
    def deliver_continuation_receipt(self, decision: JsonDict, **options: Any) -> JsonDict: ...


def _text(value: Any, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def build_continuation_receipt_intent(decision: JsonDict, *, kind: str) -> JsonDict:
    source = decision.get("source") if isinstance(decision.get("source"), dict) else {}
    resolution = decision.get("resolution") if isinstance(decision.get("resolution"), dict) else {}
    answer = _text(resolution.get("answer"), 1000) or "已完成决策"
    scene = {"chat": "会话", "meeting": "会议", "task": "项目任务"}.get(str(kind), "流程")
    source_label = _text(source.get("label"), 240) or _text(source.get("id"), 240) or "未命名"
    decision_id = _text(decision.get("id"), 120)
    return {
        "id": f"human-decision-resumed:{decision_id}",
        "type": "notification",
        "state": "approved",
        "title": "决策已完成，VO 已恢复运行",
        "summary": f"已按你的决策恢复{scene}：{answer}",
        "related": {
            "type": _text(source.get("type"), 40) or str(kind or "task"),
            "id": _text(source.get("id"), 240),
            "title": source_label,
        },
        "details": {
            "决策结果": answer,
            "恢复场景": f"{scene} · {source_label}",
            "运行状态": "原流程已恢复正常运行",
        },
        "actions": [],
        "target": "feishu-human-decision",
        "audit": {
            "routeId": decision_id,
            "application": "human-decision-continuation",
            "operation": "send",
        },
    }


class HumanDecisionContinuationReceipt:
    def __init__(
        self,
        *,
        delivery: ReceiptDelivery,
        notification_config: Callable[[], JsonDict],
        chat_config: Callable[[], JsonDict],
        fallback_chat_id: Callable[[], str],
    ):
        self._delivery = delivery
        self._notification_config = notification_config
        self._chat_config = chat_config
        self._fallback_chat_id = fallback_chat_id

    def send(self, claim: Any) -> JsonDict:
        return self._delivery.deliver_continuation_receipt(
            claim.decision,
            kind=str(claim.kind or ""),
            notification_config=self._notification_config() or {},
            chat_config=self._chat_config() or {},
            fallback_chat_id=self._fallback_chat_id() or "",
        )


__all__ = ["HumanDecisionContinuationReceipt", "build_continuation_receipt_intent"]
