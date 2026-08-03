"""Application workflow joining decision authority and Feishu delivery."""

from __future__ import annotations

from typing import Any, Callable

from .human_decision_delivery import HumanDecisionDelivery
from .human_decisions import HumanDecisionStore


JsonDict = dict[str, Any]


class HumanDecisionWorkflow:
    def __init__(
        self,
        *,
        store: HumanDecisionStore,
        delivery: HumanDecisionDelivery,
        notification_config: Callable[[], JsonDict],
        chat_config: Callable[[], JsonDict],
        fallback_chat_id: Callable[[], str],
        chat_continuation: Any | None = None,
        continuation: Any | None = None,
        continuation_binding: Callable[[JsonDict, str], JsonDict | None] | None = None,
        continuation_kick: Callable[[], None] | None = None,
    ):
        self.store = store
        self.delivery = delivery
        self._notification_config = notification_config
        self._chat_config = chat_config
        self._fallback_chat_id = fallback_chat_id
        self._continuation = continuation or chat_continuation
        self._continuation_binding = continuation_binding
        self._continuation_kick = continuation_kick

    def _configs(self) -> JsonDict:
        return {
            "notification_config": self._notification_config() or {},
            "chat_config": self._chat_config() or {},
        }

    def snapshot(self) -> JsonDict:
        return self.store.snapshot()

    def create(self, payload: JsonDict, *, agent_id: str = "") -> JsonDict:
        result = self.store.create(payload)
        source = result["decision"].get("source") if isinstance(result["decision"].get("source"), dict) else {}
        if source.get("type") == "chat" and str(agent_id or "").strip():
            result["decision"] = self.store.bind_chat_continuation(
                result["decision"]["id"],
                agent_id=str(agent_id),
                conversation_id=str(source.get("id") or ""),
            )
        elif self._continuation_binding is not None and str(agent_id or "").strip():
            native = self._continuation_binding(result["decision"], str(agent_id))
            if isinstance(native, dict) and native.get("kind") and isinstance(native.get("binding"), dict):
                result["decision"] = self.store.bind_continuation(
                    result["decision"]["id"],
                    kind=str(native["kind"]),
                    agent_id=str(agent_id),
                    binding=native["binding"],
                )
        if result["created"]:
            delivery_result = self.delivery.deliver(
                result["decision"],
                **self._configs(),
                fallback_chat_id=self._fallback_chat_id() or "",
            )
            recorded = self.store.record_delivery(
                result["decision"]["id"],
                application=str(delivery_result.get("application") or ""),
                result=delivery_result,
            )
            result["decision"] = recorded["decision"]
            result["delivery"] = {
                key: delivery_result.get(key)
                for key in ("ok", "status", "application")
            }
        result["snapshot"] = self.snapshot()
        return result

    def _queue_continuation(self, decision_id: str) -> None:
        if self._continuation is None:
            return
        queued = self._continuation.queue(decision_id)
        if queued.get("queued") and self._continuation_kick is not None:
            try:
                self._continuation_kick()
            except Exception:
                pass

    def resolve(self, decision_id: str, payload: JsonDict, *, channel: str, actor: JsonDict | None = None) -> JsonDict:
        body = payload if isinstance(payload, dict) else {}
        result = self.store.resolve(
            decision_id,
            option_id=body.get("optionId") or body.get("option_id"),
            custom_answer=body.get("customAnswer") if body.get("customAnswer") is not None else body.get("custom_answer"),
            channel=channel,
            actor=actor,
        )
        if not result["idempotent"]:
            self._queue_continuation(decision_id)
            result["cardUpdates"] = self.delivery.update_terminal(
                result["decision"],
                self.store.delivery_records(decision_id),
                **self._configs(),
            )
        result["snapshot"] = self.snapshot()
        return result

    def reopen(self, decision_id: str) -> JsonDict:
        result = self.store.reopen(decision_id)
        result["snapshot"] = self.snapshot()
        return result

    def mark_execution_started(self, decision_id: str, payload: JsonDict) -> JsonDict:
        body = payload if isinstance(payload, dict) else {}
        result = self.store.mark_execution_started(decision_id, impact=body.get("impact") or "")
        if not result.get("idempotent"):
            result["cardUpdates"] = self.delivery.update_terminal(
                result["decision"],
                self.store.delivery_records(decision_id),
                **self._configs(),
            )
        result["snapshot"] = self.snapshot()
        return result

    def handle_feishu_action(self, value: JsonDict, form: JsonDict, actor: JsonDict) -> JsonDict:
        if not isinstance(value, dict) or value.get("action") != "human_decision_submit":
            return {"handled": False}
        decision_id = str(value.get("decision_id") or "").strip()
        payload = {
            "optionId": value.get("option_id"),
            "customAnswer": (form or {}).get("custom_answer") if isinstance(form, dict) else "",
        }
        result = self.resolve(decision_id, payload, channel="feishu", actor=actor)
        return {"handled": True, **result}

    def process_due(self, now: str | None = None) -> list[JsonDict]:
        events = self.store.process_due(now)
        configs = self._configs()
        for event in events:
            decision = event["decision"]
            if event["kind"] == "reminder":
                delivery_result = self.delivery.deliver(
                    decision,
                    **configs,
                    fallback_chat_id=self._fallback_chat_id() or "",
                )
                self.store.record_delivery(
                    decision["id"],
                    application=str(delivery_result.get("application") or ""),
                    result=delivery_result,
                )
            elif event["kind"] == "timeout_resolved":
                self._queue_continuation(decision["id"])
                self.delivery.update_terminal(
                    decision,
                    self.store.delivery_records(decision["id"]),
                    **configs,
                )
        if self._continuation is not None:
            self._continuation.process_due(now=now)
        return events
