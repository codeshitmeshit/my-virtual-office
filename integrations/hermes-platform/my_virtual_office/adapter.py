"""My Virtual Office platform adapter for Hermes Agent.

Install this directory as a Hermes platform plugin:

    mkdir -p ~/.hermes/plugins/my_virtual_office
    cp plugin.yaml adapter.py ~/.hermes/plugins/my_virtual_office/

The adapter uses the official Hermes plugin interface: it subclasses
BasePlatformAdapter, registers with ctx.register_platform(), builds
MessageEvent objects for inbound messages, and sends replies through the
Virtual Office bridge API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover - httpx ships with Hermes
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore[assignment]

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

PLATFORM_NAME = "my_virtual_office"
PLUGIN_VERSION = "1.0.0"
MAX_MESSAGE_LENGTH = 12000
DEFAULT_POLL_SECONDS = 2.0


def _clean_base_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _float_value(value: Any, default: float) -> float:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _configured_values(config=None) -> dict:
    extra = getattr(config, "extra", {}) or {}
    base_url = _clean_base_url(os.getenv("MY_VIRTUAL_OFFICE_URL") or extra.get("base_url") or extra.get("url") or "")
    token = str(os.getenv("MY_VIRTUAL_OFFICE_TOKEN") or extra.get("token") or "").strip()
    adapter_id = str(os.getenv("MY_VIRTUAL_OFFICE_ADAPTER_ID") or extra.get("adapter_id") or "hermes-gateway").strip() or "hermes-gateway"
    poll_seconds = _float_value(os.getenv("MY_VIRTUAL_OFFICE_POLL_SECONDS") or extra.get("poll_seconds"), DEFAULT_POLL_SECONDS)
    return {
        "base_url": base_url,
        "token": token,
        "adapter_id": adapter_id,
        "poll_seconds": poll_seconds,
    }


def _auth_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": f"Hermes-MyVirtualOffice/{PLUGIN_VERSION}",
    }


def check_requirements() -> bool:
    cfg = _configured_values()
    return bool(HTTPX_AVAILABLE and cfg["base_url"] and cfg["token"])


def validate_config(config) -> bool:
    cfg = _configured_values(config)
    return bool(HTTPX_AVAILABLE and cfg["base_url"] and cfg["token"])


def is_connected(config) -> bool:
    return validate_config(config)


def _env_enablement() -> dict | None:
    cfg = _configured_values()
    if not (cfg["base_url"] and cfg["token"]):
        return None
    seed = {
        "base_url": cfg["base_url"],
        "token": cfg["token"],
        "adapter_id": cfg["adapter_id"],
        "poll_seconds": cfg["poll_seconds"],
    }
    home = os.getenv("MY_VIRTUAL_OFFICE_HOME_CHANNEL", "").strip()
    if home:
        seed["home_channel"] = {
            "chat_id": home,
            "name": os.getenv("MY_VIRTUAL_OFFICE_HOME_CHANNEL_NAME", home),
        }
    return seed


class MyVirtualOfficeAdapter(BasePlatformAdapter):
    """Hermes platform adapter for My Virtual Office."""

    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH
    supports_code_blocks = True

    def __init__(self, config: PlatformConfig):
        super().__init__(config=config, platform=Platform(PLATFORM_NAME))
        cfg = _configured_values(config)
        self.base_url: str = cfg["base_url"]
        self.token: str = cfg["token"]
        self.adapter_id: str = cfg["adapter_id"]
        self.poll_seconds: float = cfg["poll_seconds"]
        self._http_client: Optional["httpx.AsyncClient"] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._last_typing_heartbeat = 0.0

    @property
    def name(self) -> str:
        return "My Virtual Office"

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        if not HTTPX_AVAILABLE:
            self._set_fatal_error("missing_httpx", "httpx is required for My Virtual Office", retryable=False)
            logger.warning("[%s] httpx not installed", self.name)
            return False
        if not self.base_url or not self.token:
            self._set_fatal_error("config_missing", "MY_VIRTUAL_OFFICE_URL and MY_VIRTUAL_OFFICE_TOKEN are required", retryable=False)
            logger.warning("[%s] MY_VIRTUAL_OFFICE_URL and MY_VIRTUAL_OFFICE_TOKEN are required", self.name)
            return False

        self._http_client = httpx.AsyncClient(timeout=30.0, headers=_auth_headers(self.token))
        self._running = True
        heartbeat = await self._heartbeat("connected")
        if not heartbeat.get("ok"):
            await self.disconnect()
            self._set_fatal_error("heartbeat_failed", heartbeat.get("error") or "Virtual Office heartbeat failed", retryable=True)
            return False

        self._poll_task = asyncio.create_task(self._poll_loop())
        self._mark_connected()
        logger.info("[%s] Connected to %s", self.name, self.base_url)
        return True

    async def disconnect(self) -> None:
        self._running = False
        self._mark_disconnected()
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._http_client:
            try:
                await self._heartbeat("disconnected")
            except Exception:
                pass
            await self._http_client.aclose()
        self._http_client = None
        self._poll_task = None

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._http_client:
            return SendResult(success=False, error="Not connected")
        payload = {
            "adapterId": self.adapter_id,
            "chatId": chat_id,
            "message": content,
            "replyToMessageId": reply_to or "",
            "metadata": metadata or {},
        }
        result = await self._post_json("/api/hermes-platform/reply", payload)
        if result.get("ok"):
            return SendResult(success=True, message_id=result.get("replyMessageId") or result.get("messageId"))
        return SendResult(success=False, error=result.get("error") or "Virtual Office reply failed")

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        now = time.monotonic()
        if now - self._last_typing_heartbeat < 15:
            return
        self._last_typing_heartbeat = now
        await self._heartbeat("working")

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id or "Virtual Office", "type": "dm", "chat_id": chat_id}

    async def _poll_loop(self) -> None:
        backoff = self.poll_seconds
        while self._running:
            try:
                messages = await self._poll_once()
                backoff = self.poll_seconds
                if not messages:
                    await asyncio.sleep(self.poll_seconds)
                    continue
                for item in messages:
                    await self._dispatch_queued_message(item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[%s] Poll loop error: %s", self.name, exc)
                await asyncio.sleep(min(max(backoff, self.poll_seconds), 30.0))
                backoff = min(backoff * 2, 30.0)

    async def _poll_once(self) -> List[dict]:
        result = await self._get_json(
            "/api/hermes-platform/poll",
            params={
                "adapterId": self.adapter_id,
                "version": PLUGIN_VERSION,
                "limit": "5",
            },
        )
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "Virtual Office poll failed")
        messages = result.get("messages") or []
        return messages if isinstance(messages, list) else []

    async def _dispatch_queued_message(self, item: dict) -> None:
        message_id = str(item.get("id") or item.get("messageId") or "")
        lease_id = str(item.get("leaseId") or "")
        try:
            text = str(item.get("text") or "").strip()
            if not text:
                await self._ack_message(message_id, lease_id, ok=False, error="empty message")
                return
            source = self.build_source(
                chat_id=str(item.get("chatId") or item.get("conversationId") or "virtual-office"),
                chat_name=str(item.get("chatName") or item.get("chatId") or "Virtual Office"),
                chat_type=str(item.get("chatType") or "dm"),
                user_id=str(item.get("userId") or "user"),
                user_name=str(item.get("userName") or "User"),
                thread_id=str(item.get("threadId") or item.get("conversationId") or ""),
                message_id=message_id,
            )
            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                raw_message=item,
                message_id=message_id,
                metadata={
                    **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    "my_virtual_office_message_id": message_id,
                    "my_virtual_office_lease_id": lease_id,
                },
            )
            await self.handle_message(event)
            await self._ack_message(message_id, lease_id, ok=True)
        except Exception as exc:
            logger.warning("[%s] Failed to dispatch message %s: %s", self.name, message_id, exc)
            await self._ack_message(message_id, lease_id, ok=False, error=str(exc))

    async def _ack_message(self, message_id: str, lease_id: str, *, ok: bool, error: str = "") -> dict:
        if not message_id:
            return {"ok": False, "error": "missing message id"}
        return await self._post_json(
            "/api/hermes-platform/ack",
            {"adapterId": self.adapter_id, "messageId": message_id, "leaseId": lease_id, "ok": ok, "error": error},
        )

    async def _heartbeat(self, status: str) -> dict:
        if not self._http_client:
            return {"ok": False, "error": "not connected"}
        return await self._post_json(
            "/api/hermes-platform/heartbeat",
            {"adapterId": self.adapter_id, "status": status, "version": PLUGIN_VERSION},
        )

    async def _get_json(self, path: str, params: Optional[dict] = None) -> dict:
        if not self._http_client:
            return {"ok": False, "error": "not connected"}
        response = await self._http_client.get(self.base_url + path, params=params or {})
        try:
            data = response.json()
        except Exception:
            data = {"ok": False, "error": response.text[:500]}
        if response.status_code >= 400:
            data.setdefault("ok", False)
            data.setdefault("error", f"HTTP {response.status_code}")
        return data

    async def _post_json(self, path: str, payload: dict) -> dict:
        if not self._http_client:
            return {"ok": False, "error": "not connected"}
        response = await self._http_client.post(self.base_url + path, json=payload)
        try:
            data = response.json()
        except Exception:
            data = {"ok": False, "error": response.text[:500]}
        if response.status_code >= 400:
            data.setdefault("ok", False)
            data.setdefault("error", f"HTTP {response.status_code}")
        return data


async def _standalone_send(
    pconfig,
    chat_id: str,
    message: str,
    *,
    thread_id: Optional[str] = None,
    media_files: Optional[List[str]] = None,
    force_document: bool = False,
) -> Dict[str, Any]:
    cfg = _configured_values(pconfig)
    if not HTTPX_AVAILABLE:
        return {"error": "My Virtual Office standalone send: httpx is not installed"}
    if not cfg["base_url"] or not cfg["token"]:
        return {"error": "My Virtual Office standalone send: URL and token are required"}
    payload = {
        "adapterId": cfg["adapter_id"],
        "chatId": chat_id or os.getenv("MY_VIRTUAL_OFFICE_HOME_CHANNEL", "virtual-office"),
        "message": message,
        "threadId": thread_id or "",
        "metadata": {"standalone": True},
    }
    async with httpx.AsyncClient(timeout=30.0, headers=_auth_headers(cfg["token"])) as client:
        response = await client.post(cfg["base_url"] + "/api/hermes-platform/reply", json=payload)
        try:
            data = response.json()
        except Exception:
            data = {"ok": False, "error": response.text[:500]}
        if response.status_code >= 400 or not data.get("ok"):
            return {"error": data.get("error") or f"HTTP {response.status_code}"}
        return {"success": True, "message_id": data.get("replyMessageId") or data.get("messageId") or ""}


def register(ctx) -> None:
    """Plugin entry point called by the Hermes plugin system."""
    ctx.register_platform(
        name=PLATFORM_NAME,
        label="My Virtual Office",
        adapter_factory=lambda cfg: MyVirtualOfficeAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["MY_VIRTUAL_OFFICE_URL", "MY_VIRTUAL_OFFICE_TOKEN"],
        install_hint="Copy this plugin directory to ~/.hermes/plugins/my_virtual_office and set MY_VIRTUAL_OFFICE_URL/MY_VIRTUAL_OFFICE_TOKEN.",
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="MY_VIRTUAL_OFFICE_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        allowed_users_env="MY_VIRTUAL_OFFICE_ALLOWED_USERS",
        allow_all_env="MY_VIRTUAL_OFFICE_ALLOW_ALL_USERS",
        max_message_length=MAX_MESSAGE_LENGTH,
        pii_safe=False,
        allow_update_command=True,
        platform_hint=(
            "You are chatting through My Virtual Office. It renders normal "
            "markdown in chat bubbles and shows your replies as visible office "
            "conversation events. Keep replies clear and conversational."
        ),
    )
