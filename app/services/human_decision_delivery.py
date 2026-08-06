"""Feishu delivery adapter for human decision requests.

This module deliberately reuses the common notification card renderer, sender
and updater. It only owns decision-specific intent shaping and bot routing.
"""

from __future__ import annotations

from typing import Any, Callable

from .human_decision_continuation_receipt import build_continuation_receipt_intent

try:  # server.py executes with app/ on sys.path; package tests import app.*
    from feishu_notifications import send_feishu_notification, update_feishu_notification
except ModuleNotFoundError:  # pragma: no cover - exercised by package-style tests
    from app.feishu_notifications import send_feishu_notification, update_feishu_notification


JsonDict = dict[str, Any]


def _text(value: Any, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _detail(label: str, value: str) -> JsonDict:
    return {"label": label, "value": value}


def _option_details(decision: JsonDict) -> list[JsonDict]:
    details = []
    recommended = _text((decision.get("recommendation") or {}).get("optionId"), 1)
    for option in decision.get("options") or []:
        if not isinstance(option, dict):
            continue
        option_id = _text(option.get("id"), 1)
        if not option_id:
            continue
        marker = "（VO 推荐）" if option_id == recommended else ""
        details.append(_detail(
            f"{option_id}｜{_text(option.get('label'), 400)}{marker}",
            f"影响：{_text(option.get('impact'), 700)}",
        ))
    return details


def build_decision_intent(decision: JsonDict, *, terminal: bool = False, application: str = "") -> JsonDict:
    source = decision.get("source") if isinstance(decision.get("source"), dict) else {}
    detail = decision.get("taskDetail") if isinstance(decision.get("taskDetail"), dict) else {}
    recommendation = decision.get("recommendation") if isinstance(decision.get("recommendation"), dict) else {}
    resolution = decision.get("resolution") if isinstance(decision.get("resolution"), dict) else {}
    decision_id = _text(decision.get("id"), 120)
    summary = _text(decision.get("situation"), 1000)
    details = [
        _detail("来源", f"{_text(source.get('type'), 20)} · {_text(source.get('label'), 200)}"),
        _detail("情景", summary),
        _detail("为什么需要你决定", _text(decision.get("reason"), 1000)),
        _detail("风险 / 紧急度", f"{_text(decision.get('risk'), 20)} / {_text(decision.get('urgency'), 20)}"),
        {"type": "divider"},
        *_option_details(decision),
        {"type": "divider"},
        _detail("VO 推荐", f"{_text(recommendation.get('optionId'), 1)} · {_text(recommendation.get('reason'), 1000)}"),
        _detail("任务详情", _text(detail.get("summary"), 1000)),
        _detail("决策后下一步", _text(detail.get("nextStep"), 1000)),
        _detail("超时处理", _text(decision.get("timeoutConsequence"), 1000)),
    ]
    if terminal:
        details = {
            "最终决策": _text(resolution.get("answer"), 1000),
            "处理入口": _text(resolution.get("channel"), 40),
            "处理时间": _text(resolution.get("resolvedAt"), 80),
            "VO 下一步": _text(resolution.get("nextAction"), 1000),
        }
    actions = []
    inputs = []
    if not terminal:
        inputs = [{
            "name": "custom_answer",
            "label": "如果 A-D 都不符合，请输入你的决定（填写后优先采用）",
            "placeholder": "输入你的自定义决定；留空则采用所点击的 A-D 选项",
            "multiline": True,
            "required": False,
        }]
        for option_id in ("A", "B", "C", "D"):
            actions.append({
                "category": "confirm",
                "text": option_id,
                "value": {"action": "human_decision_submit", "decision_id": decision_id, "option_id": option_id},
            })
        actions.append({
            "category": "confirm",
            "text": "提交自定义",
            "value": {"action": "human_decision_submit", "decision_id": decision_id, "option_id": ""},
        })
    else:
        # Feishu cannot PATCH a schema-2 form card into a schema-1 card. Keep one
        # inert field so the terminal card remains schema 2.0, but remove every
        # submit action; editing this local field cannot produce a callback.
        inputs = [{
            "name": "final_result",
            "label": "最终决策（已处理，不可重复提交）",
            "placeholder": _text(resolution.get("answer"), 1000) or "已处理",
            "default_value": _text(resolution.get("answer"), 1000),
            "multiline": True,
            "required": False,
        }]
    return {
        "id": f"human-decision:{decision_id}",
        "type": "application_form",
        "state": "approved" if terminal else "pending",
        "title": ("决策已处理：" if terminal else "需要你的决策：") + _text(decision.get("title"), 160),
        "summary": _text(resolution.get("answer"), 1000) if terminal else summary,
        "related": {"type": _text(source.get("type"), 40) or "task", "id": _text(source.get("id"), 240), "title": _text(source.get("label"), 240)},
        "details": details,
        "inputs": inputs,
        "actions": actions,
        "target": "feishu-human-decision",
        "audit": {"routeId": decision_id, "application": application, "operation": "update" if terminal else "send"},
    }


def _configured(config: JsonDict, *, require_receive_id: bool = True) -> bool:
    if not isinstance(config, dict):
        return False
    return bool(config.get("appId") and config.get("appSecret") and (config.get("receiveId") or not require_receive_id))


class HumanDecisionDelivery:
    def __init__(
        self,
        *,
        send: Callable[..., JsonDict] = send_feishu_notification,
        update: Callable[..., JsonDict] = update_feishu_notification,
        status_dir: str | None = None,
    ):
        self._send = send
        self._update = update
        self._status_dir = status_dir

    def _deliver_intent(
        self,
        intent: JsonDict,
        *,
        notification_config: JsonDict,
        chat_config: JsonDict,
        fallback_chat_id: str,
    ) -> JsonDict:
        application = ""
        app_config: JsonDict = {}
        if _configured(notification_config):
            application = "notification"
            app_config = dict(notification_config)
        elif _configured(chat_config, require_receive_id=False) and _text(fallback_chat_id, 240):
            application = "chat"
            app_config = {
                **dict(chat_config),
                "receiveIdType": "chat_id",
                "receiveId": _text(fallback_chat_id, 240),
            }
        else:
            return {"ok": False, "status": "missing_app_config", "application": ""}

        routed_intent = {**intent, "audit": {**dict(intent.get("audit") or {}), "application": application}}
        result = self._send(
            routed_intent,
            app_config=app_config,
            status_dir=self._status_dir,
            allow_webhook=False,
        )
        return {**dict(result or {}), "application": application}

    def deliver(
        self,
        decision: JsonDict,
        *,
        notification_config: JsonDict,
        chat_config: JsonDict,
        fallback_chat_id: str,
    ) -> JsonDict:
        application = "notification" if _configured(notification_config) else "chat"
        return self._deliver_intent(
            build_decision_intent(decision, application=application),
            notification_config=notification_config,
            chat_config=chat_config,
            fallback_chat_id=fallback_chat_id,
        )

    def deliver_continuation_receipt(
        self,
        decision: JsonDict,
        *,
        kind: str,
        notification_config: JsonDict,
        chat_config: JsonDict,
        fallback_chat_id: str,
    ) -> JsonDict:
        return self._deliver_intent(
            build_continuation_receipt_intent(decision, kind=kind),
            notification_config=notification_config,
            chat_config=chat_config,
            fallback_chat_id=fallback_chat_id,
        )

    def update_terminal(
        self,
        decision: JsonDict,
        delivery_records: list[JsonDict],
        *,
        notification_config: JsonDict,
        chat_config: JsonDict,
    ) -> list[JsonDict]:
        results = []
        configs = {"notification": notification_config, "chat": chat_config}
        for record in delivery_records:
            message_id = _text(record.get("messageId"), 300)
            application = _text(record.get("application"), 40)
            config = configs.get(application) or {}
            if not message_id or not _configured(config, require_receive_id=False):
                continue
            result = self._update(
                message_id,
                build_decision_intent(decision, terminal=True, application=application),
                app_config=config,
                status_dir=self._status_dir,
            )
            results.append({**dict(result or {}), "application": application, "messageId": message_id})
        return results
