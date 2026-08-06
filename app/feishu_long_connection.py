"""Feishu long-connection card action and chat message receiver."""

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
        action_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        message_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        name: str = "feishu-long-connection",
    ) -> None:
        self.app_id = str(app_id or "").strip()
        self.app_secret = str(app_secret or "").strip()
        self.action_handler = action_handler
        self.message_handler = message_handler
        self.name = str(name or "feishu-long-connection")
        self._thread: threading.Thread | None = None
        self._client: Any | None = None
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
        self._thread = threading.Thread(target=self._run, daemon=True, name=self.name)
        self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            client = self._client
            self._status.update(enabled=False, running=False, status="stopped", lastError="")
        for method_name in ("stop", "close", "shutdown", "disconnect"):
            method = getattr(client, method_name, None)
            if not callable(method):
                continue
            try:
                method()
                break
            except Exception as exc:
                self._set_status(lastError=f"{type(exc).__name__}: {exc}")
        return self.status()

    def _handle_card_action_event(self, data: Any) -> dict[str, Any]:
        body = self._event_to_body(data)
        result = self.action_handler(body) if self.action_handler else {"ok": True}
        self._set_status(status="running", running=True, lastEventAt=int(time.time()), lastError="")
        toast = result.get("toast") if isinstance(result, dict) else None
        if not isinstance(toast, dict):
            toast = {"type": "success", "content": "操作已收到"}
        return toast

    def _handle_message_event(self, data: Any) -> None:
        body = self._message_event_to_body(data)
        if self.message_handler:
            self.message_handler(body)
        self._set_status(status="running", running=True, lastEventAt=int(time.time()), lastError="")

    def _handle_bot_p2p_chat_entered_event(self, data: Any) -> None:
        self._set_status(status="running", running=True, lastEventAt=int(time.time()), lastError="")

    def _run(self) -> None:
        try:
            import lark_oapi as lark
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTrigger,
                P2CardActionTriggerResponse,
            )

            def on_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
                try:
                    toast = self._handle_card_action_event(data)
                    return P2CardActionTriggerResponse({"toast": toast})
                except Exception as exc:
                    self._set_status(
                        status="handler_error",
                        running=True,
                        lastEventAt=int(time.time()),
                        lastError=f"{type(exc).__name__}: {exc}",
                    )
                    print(f"[FeishuLongConnection] card action handler failed: {type(exc).__name__}: {exc}")
                    return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "操作已收到，后台处理中"}})

            builder = lark.EventDispatcherHandler.builder("", "", lark.LogLevel.INFO)
            if self.action_handler:
                builder = builder.register_p2_card_action_trigger(on_card_action)
            if self.message_handler and hasattr(builder, "register_p2_im_message_receive_v1"):
                def on_message(data: Any) -> None:
                    try:
                        self._handle_message_event(data)
                    except Exception as exc:
                        self._set_status(
                            status="handler_error",
                            running=True,
                            lastEventAt=int(time.time()),
                            lastError=f"{type(exc).__name__}: {exc}",
                        )
                        print(f"[FeishuLongConnection] message handler failed: {type(exc).__name__}: {exc}")
                builder = builder.register_p2_im_message_receive_v1(on_message)
            elif self.message_handler:
                self._set_status(status="missing_message_event_handler", running=True, lastError="register_p2_im_message_receive_v1 is unavailable")
            if hasattr(builder, "register_p2_im_chat_access_event_bot_p2p_chat_entered_v1"):
                def on_bot_p2p_chat_entered(data: Any) -> None:
                    try:
                        self._handle_bot_p2p_chat_entered_event(data)
                    except Exception as exc:
                        self._set_status(
                            status="handler_error",
                            running=True,
                            lastEventAt=int(time.time()),
                            lastError=f"{type(exc).__name__}: {exc}",
                        )
                        print(f"[FeishuLongConnection] bot p2p entered handler failed: {type(exc).__name__}: {exc}")
                builder = builder.register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(on_bot_p2p_chat_entered)
            handler = builder.build()
            self._set_status(status="connecting", running=True, lastError="")
            client = lark.ws.Client(self.app_id, self.app_secret, event_handler=handler)
            self._client = client
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
        finally:
            self._client = None

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

    @staticmethod
    def _message_event_to_body(data: Any) -> dict[str, Any]:
        event = getattr(data, "event", None)
        header = getattr(data, "header", None)
        message = getattr(event, "message", None)
        sender = getattr(event, "sender", None)
        sender_id = getattr(sender, "sender_id", None)
        sender_type = str(getattr(sender, "sender_type", "") or getattr(sender, "type", "") or "")[:40]
        chat_type = str(getattr(message, "chat_type", "") or "")
        message_type = str(getattr(message, "message_type", "") or getattr(message, "msg_type", "") or "")
        content = getattr(message, "content", None) or ""
        text = ""
        parsed_content: Any = content
        if isinstance(content, str):
            try:
                parsed_content = json.loads(content) if content else {}
            except json.JSONDecodeError:
                parsed_content = {"text": content}
        if isinstance(parsed_content, dict):
            text = str(parsed_content.get("text") or parsed_content.get("content") or "")
        else:
            text = str(parsed_content or "")
        try:
            message_create_time = int(getattr(message, "create_time", 0) or 0)
        except (TypeError, ValueError):
            message_create_time = 0

        def object_dict(value: Any, *, limit: int = 100) -> list[dict[str, Any]]:
            result = []
            for item in value if isinstance(value, (list, tuple)) else []:
                if isinstance(item, dict):
                    source = item
                else:
                    source = {
                        key: getattr(item, key, None)
                        for key in (
                            "key", "id", "name", "tenant_key", "open_id", "user_id",
                            "file_key", "image_key", "file_name", "file_size", "mime_type", "type",
                        )
                        if getattr(item, key, None) not in (None, "")
                    }
                result.append({str(key)[:80]: value for key, value in source.items() if value not in (None, "")})
                if len(result) >= limit:
                    break
            return result

        mentions = object_dict(getattr(message, "mentions", None), limit=100)
        resources = object_dict(getattr(message, "resources", None), limit=10)
        if isinstance(parsed_content, dict):
            for resource_type, key_name in (("image", "image_key"), ("file", "file_key")):
                key = parsed_content.get(key_name)
                if key and not any(item.get("file_key") == key or item.get("image_key") == key for item in resources):
                    resources.append({"resource_type": resource_type, key_name: str(key)[:500]})
        return {
            "schema": "2.0",
            "header": {
                "event_type": "im.message.receive_v1",
                "event_id": str(getattr(header, "event_id", "") or ""),
                "tenant_key": str(getattr(header, "tenant_key", "") or "")[:300],
                "create_time": str(getattr(header, "create_time", "") or "")[:40],
            },
            "event": {
                "sender": {
                    "sender_type": sender_type,
                    "is_bot": sender_type.lower() in {"bot", "app"},
                    "sender_id": {
                        "open_id": str(getattr(sender_id, "open_id", "") or ""),
                        "user_id": str(getattr(sender_id, "user_id", "") or ""),
                        "union_id": str(getattr(sender_id, "union_id", "") or ""),
                    }
                },
                "message": {
                    "message_id": str(getattr(message, "message_id", "") or ""),
                    "chat_id": str(getattr(message, "chat_id", "") or ""),
                    "chat_type": chat_type,
                    "message_type": message_type,
                    "content": parsed_content,
                    "text": text,
                    "root_id": str(getattr(message, "root_id", "") or "")[:300],
                    "thread_id": str(getattr(message, "thread_id", "") or "")[:300],
                    "parent_id": str(getattr(message, "parent_id", "") or "")[:300],
                    "reply_to_message_id": str(getattr(message, "reply_to_message_id", "") or getattr(message, "parent_id", "") or "")[:300],
                    "create_time": message_create_time,
                    "mentions": mentions,
                    "resources": resources[:10],
                },
            },
        }
