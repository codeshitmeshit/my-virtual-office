"""Feishu long-connection card action receiver."""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Any, Callable


class FeishuLongConnectionReceiver:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        action_handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.app_id = str(app_id or "").strip()
        self.app_secret = str(app_secret or "").strip()
        self.action_handler = action_handler
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "enabled": False,
            "running": False,
            "status": "not_started",
            "startedAt": 0,
            "lastEventAt": 0,
            "lastError": "",
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)

    def start(self) -> dict[str, Any]:
        if not self.app_id or not self.app_secret:
            self._set_status(enabled=False, running=False, status="missing_app_credentials")
            return self.status()
        if self._thread and self._thread.is_alive():
            return self.status()
        self._set_status(enabled=True, running=True, status="starting", startedAt=int(time.time()), lastError="")
        self._thread = threading.Thread(target=self._run, daemon=True, name="feishu-long-connection")
        self._thread.start()
        return self.status()

    def _run(self) -> None:
        try:
            import lark_oapi as lark
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                CallBackToast,
                P2CardActionTrigger,
                P2CardActionTriggerResponse,
            )

            def on_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
                body = self._event_to_body(data)
                result = self.action_handler(body)
                self._set_status(status="running", running=True, lastEventAt=int(time.time()), lastError="")
                toast = result.get("toast") if isinstance(result, dict) else None
                if not isinstance(toast, dict):
                    toast = {"type": "success", "content": "操作已收到"}
                return P2CardActionTriggerResponse({"toast": CallBackToast(toast)})

            handler = (
                lark.EventDispatcherHandler.builder("", "", lark.LogLevel.INFO)
                .register_p2_card_action_trigger(on_card_action)
                .build()
            )
            self._set_status(status="connecting", running=True, lastError="")
            client = lark.ws.Client(self.app_id, self.app_secret, event_handler=handler)
            self._set_status(status="running", running=True, lastError="")
            client.start()
        except Exception as exc:
            self._set_status(
                status="error",
                running=False,
                lastError=f"{type(exc).__name__}: {exc}",
                traceback=traceback.format_exc(limit=5),
            )
            print(f"[FeishuLongConnection] stopped: {type(exc).__name__}: {exc}")

    @staticmethod
    def _event_to_body(data: Any) -> dict[str, Any]:
        event = getattr(data, "event", None)
        action = getattr(event, "action", None)
        operator = getattr(event, "operator", None)
        context = getattr(event, "context", None)
        header = getattr(data, "header", None)
        value = getattr(action, "value", None) or {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = {"raw": value}
        if not isinstance(value, dict):
            value = {"raw": value}
        return {
            "schema": "2.0",
            "header": {
                "event_type": "card.action.trigger",
                "event_id": str(getattr(header, "event_id", "") or ""),
            },
            "event": {
                "operator": {
                    "open_id": str(getattr(operator, "open_id", "") or ""),
                    "user_id": str(getattr(operator, "user_id", "") or ""),
                    "union_id": str(getattr(operator, "union_id", "") or ""),
                },
                "open_message_id": str(getattr(context, "open_message_id", "") or ""),
                "open_chat_id": str(getattr(context, "open_chat_id", "") or ""),
                "action": {
                    "value": value,
                    "tag": str(getattr(action, "tag", "") or ""),
                    "option": str(getattr(action, "option", "") or ""),
                    "name": str(getattr(action, "name", "") or ""),
                    "form_value": getattr(action, "form_value", None) or {},
                },
            },
        }
