"""Common Feishu notification cards for Virtual Office."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable


NOTIFICATION_TYPES = {"application_form", "notification", "warning", "error"}
APPLICATION_STATES = {
    "pending",
    "submitted",
    "processing",
    "approved",
    "rejected",
    "expired",
    "cancelled",
    "no_longer_actionable",
}
ACTION_CATEGORIES = {"confirm", "cancel", "jump", "request_more_info"}
ERROR_VARIANTS = {"user_facing", "admin_facing"}
AUDIENCES = {"user", "admin", "both"}

_TYPE_TEMPLATE = {
    "application_form": "blue",
    "notification": "green",
    "warning": "orange",
    "error": "red",
}
_STATE_LABELS = {
    "pending": "待处理",
    "submitted": "已提交处理",
    "processing": "处理中",
    "approved": "已同意",
    "rejected": "已拒绝",
    "expired": "已过期",
    "cancelled": "已取消",
    "no_longer_actionable": "不再可处理",
}
_CATEGORY_LABELS = {
    "application_form": "申请表单",
    "notification": "通知",
    "warning": "警告",
    "error": "错误",
}
_SECRET_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|webhook)\s*[:=]\s*([^\s,;]+)"
)
_HOOK_RE = re.compile(r"(https://open\.(?:feishu|larksuite)\.cn/open-apis/bot/v2/hook/)[A-Za-z0-9_-]+")
_HOOK_TOKEN_RE = re.compile(r"(?i)(hook/)?token-[A-Za-z0-9_-]+")
_RECORD_LOCK = threading.Lock()
_TOKEN_CACHE: dict[str, dict[str, Any]] = {}


class FeishuNotificationError(ValueError):
    """Raised when a notification intent cannot be rendered safely."""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _compact_text(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "...[truncated]"


def redact_sensitive(value: Any) -> str:
    text = _compact_text(value, 4000)
    text = _SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _HOOK_RE.sub(r"\1[REDACTED]", text)
    text = _HOOK_TOKEN_RE.sub("[REDACTED]", text)
    return text


def _string(value: Any, limit: int = 300) -> str:
    return _compact_text(value, limit)


def _normalize_details(raw: Any) -> list[tuple[str, str]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for item in raw:
            if isinstance(item, dict):
                items.append((item.get("label") or item.get("key") or item.get("name"), item.get("value")))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                items.append((item[0], item[1]))
    else:
        return [("详情", raw)]
    details = []
    for key, value in items:
        label = _string(key, 80)
        text = _string(value, 500)
        if label and text:
            details.append((label, text))
    return details[:20]


def _normalize_related(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    related = {}
    for key in ("type", "id", "title"):
        value = _string(raw.get(key), 160)
        if value:
            related[key] = value
    return related


def _button_style(category: str) -> str:
    if category == "confirm":
        return "primary"
    if category == "cancel":
        return "danger"
    return "default"


def validate_notification_intent(intent: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(intent, dict):
        raise FeishuNotificationError("notification intent must be a dict")
    kind = _string(intent.get("type"), 80)
    if kind not in NOTIFICATION_TYPES:
        raise FeishuNotificationError(f"unsupported notification type: {kind or '<empty>'}")
    title = _string(intent.get("title"), 160)
    summary = _string(intent.get("summary"), 1800)
    if not title:
        raise FeishuNotificationError("notification title is required")
    if not summary:
        raise FeishuNotificationError("notification summary is required")

    audience = _string(intent.get("audience") or "both", 40)
    if audience not in AUDIENCES:
        raise FeishuNotificationError(f"unsupported audience: {audience}")
    error_variant = _string(intent.get("error_variant") or "user_facing", 40)
    if kind == "error" and error_variant not in ERROR_VARIANTS:
        raise FeishuNotificationError(f"unsupported error variant: {error_variant}")

    state = _string(intent.get("state") or ("pending" if kind == "application_form" else ""), 80)
    if kind == "application_form" and state not in APPLICATION_STATES:
        raise FeishuNotificationError(f"unsupported application form state: {state}")
    if kind != "application_form":
        state = ""

    actions = []
    for idx, action in enumerate(intent.get("actions") or []):
        if not isinstance(action, dict):
            raise FeishuNotificationError(f"action {idx} must be a dict")
        category = _string(action.get("category"), 80)
        if category not in ACTION_CATEGORIES:
            raise FeishuNotificationError(f"unsupported action category: {category or '<empty>'}")
        if kind != "application_form" and category != "jump":
            raise FeishuNotificationError("non-application notifications only support jump actions")
        text = _string(action.get("text") or action.get("label"), 80)
        if not text:
            raise FeishuNotificationError(f"action {idx} text is required")
        url = _string(action.get("url"), 1000)
        value = action.get("value") if isinstance(action.get("value"), dict) else {}
        if category == "jump" and not url:
            raise FeishuNotificationError(f"jump action {idx} requires url")
        if category != "jump" and url:
            raise FeishuNotificationError(f"decision action {idx} cannot use url")
        actions.append({
            "category": category,
            "text": text,
            "url": url,
            "value": value,
        })

    return {
        "id": _string(intent.get("id") or str(uuid.uuid4()), 120),
        "type": kind,
        "title": title,
        "summary": summary,
        "details": _normalize_details(intent.get("details")),
        "related": _normalize_related(intent.get("related")),
        "audience": audience,
        "error_variant": error_variant if kind == "error" else "",
        "state": state,
        "multi_participant": bool(intent.get("multi_participant")),
        "target": _string(intent.get("target") or "feishu-webhook", 160),
        "actions": actions,
        "diagnostic": redact_sensitive(intent.get("diagnostic") or ""),
    }


def build_feishu_card(intent: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_notification_intent(intent)
    kind = normalized["type"]
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**类型**：{_CATEGORY_LABELS[kind]}\n**摘要**：{normalized['summary']}",
            },
        }
    ]
    if kind == "application_form":
        state_line = f"**状态**：{_STATE_LABELS[normalized['state']]}"
        if normalized["multi_participant"]:
            state_line += "\n**处理模式**：多人参与"
        else:
            state_line += "\n**处理模式**：单人最终决策"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": state_line}})
    if kind == "error":
        if normalized["error_variant"] == "admin_facing" and normalized["diagnostic"]:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**诊断摘要**：{normalized['diagnostic']}"},
            })
        elif normalized["error_variant"] == "user_facing":
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "请根据提示重试，或联系管理员查看系统诊断信息。"},
            })

    related = normalized["related"]
    if related:
        related_lines = []
        if related.get("type"):
            related_lines.append(f"**对象类型**：{related['type']}")
        if related.get("id"):
            related_lines.append(f"**对象 ID**：{related['id']}")
        if related.get("title"):
            related_lines.append(f"**对象标题**：{related['title']}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(related_lines)}})

    for label, value in normalized["details"]:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{label}**：{value}"},
        })

    action_buttons = []
    for action in normalized["actions"]:
        button = {
            "tag": "button",
            "text": {"tag": "plain_text", "content": action["text"]},
            "type": _button_style(action["category"]),
        }
        if action["category"] == "jump":
            button["url"] = action["url"]
        else:
            button["value"] = {
                **action["value"],
                "notification_id": normalized["id"],
                "action_category": action["category"],
                "callback_status": "not_implemented",
            }
        action_buttons.append(button)
    if action_buttons:
        elements.append({"tag": "action", "actions": action_buttons[:6]})

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": _TYPE_TEMPLATE[kind],
                "title": {"tag": "plain_text", "content": normalized["title"]},
            },
            "elements": elements,
        },
    }


def _record_path(status_dir: str | None = None) -> str:
    base = status_dir or os.environ.get("VO_STATUS_DIR") or "/data"
    return os.path.join(base, "feishu-notification-records.jsonl")


def _webhook_fingerprint(webhook_url: str) -> str:
    if not webhook_url:
        return ""
    return hashlib.sha256(webhook_url.encode("utf-8")).hexdigest()[:12]


def _secret_fingerprint(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def record_feishu_notification(intent: dict[str, Any], result: dict[str, Any], status_dir: str | None = None) -> dict[str, Any]:
    normalized = validate_notification_intent(intent)
    record = {
        "id": normalized["id"],
        "type": normalized["type"],
        "title": normalized["title"],
        "related": normalized["related"],
        "target": normalized["target"],
        "sentAt": _now_iso(),
        "ok": bool(result.get("ok")),
        "status": _string(result.get("status") or result.get("code") or "", 120),
        "error": redact_sensitive(result.get("error") or result.get("message") or ""),
        "webhookFingerprint": _string(result.get("webhookFingerprint") or "", 40),
        "appFingerprint": _string(result.get("appFingerprint") or "", 40),
        "channel": _string(result.get("channel") or "", 40),
    }
    path = _record_path(status_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _RECORD_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def _record_invalid_notification(intent: dict[str, Any], result: dict[str, Any], status_dir: str | None = None) -> dict[str, Any]:
    fallback_type = _string((intent or {}).get("type") or "notification", 80)
    if fallback_type not in NOTIFICATION_TYPES:
        fallback_type = "notification"
    record = {
        "id": _string((intent or {}).get("id") or str(uuid.uuid4()), 120),
        "type": fallback_type,
        "title": _string((intent or {}).get("title") or "Invalid notification", 160),
        "related": _normalize_related((intent or {}).get("related")),
        "target": _string((intent or {}).get("target") or "feishu-webhook", 160),
        "sentAt": _now_iso(),
        "ok": False,
        "status": "invalid_intent",
        "error": redact_sensitive(result.get("error") or ""),
        "webhookFingerprint": "",
    }
    path = _record_path(status_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _RECORD_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def send_feishu_notification(
    intent: dict[str, Any],
    *,
    webhook_url: str | None = None,
    app_config: dict[str, Any] | None = None,
    status_dir: str | None = None,
    dry_run: bool = False,
    urlopen: Callable[..., Any] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    try:
        payload = build_feishu_card(intent)
        normalized = validate_notification_intent(intent)
    except FeishuNotificationError as exc:
        result = {"ok": False, "status": "invalid_intent", "error": str(exc)}
        result["record"] = _record_invalid_notification(intent or {}, result, status_dir)
        return result

    enabled = str(os.environ.get("VO_FEISHU_NOTIFICATION_ENABLED", "1")).strip().lower()
    if enabled in {"0", "false", "no", "off", "disabled"}:
        result = {"ok": True, "status": "skipped_disabled", "webhookFingerprint": ""}
        result["record"] = record_feishu_notification(normalized, result, status_dir)
        return result

    opener = urlopen or urllib.request.urlopen
    webhook = webhook_url or os.environ.get("VO_FEISHU_NOTIFICATION_WEBHOOK") or ""
    fingerprint = _webhook_fingerprint(webhook)
    if dry_run:
        result = {"ok": True, "status": "dry_run", "payload": payload, "webhookFingerprint": fingerprint}
        result["record"] = record_feishu_notification(normalized, result, status_dir)
        return result

    app_cfg = app_config or {}
    if app_cfg.get("appId") and app_cfg.get("appSecret") and app_cfg.get("receiveId"):
        result = _send_feishu_app_message(
            payload,
            app_cfg,
            urlopen=opener,
            timeout=timeout,
        )
        result["record"] = record_feishu_notification(normalized, result, status_dir)
        return result

    if not webhook:
        result = {"ok": True, "status": "skipped_missing_webhook", "webhookFingerprint": ""}
        result["record"] = record_feishu_notification(normalized, result, status_dir)
        return result

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw[:500]}
        success = parsed.get("code") == 0 or parsed.get("StatusCode") == 0
        result = {
            "ok": bool(success),
            "status": "sent" if success else "feishu_error",
            "channel": "webhook",
            "code": parsed.get("code", parsed.get("StatusCode", "")),
            "message": redact_sensitive(parsed.get("msg") or parsed.get("StatusMessage") or raw),
            "webhookFingerprint": fingerprint,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result = {
            "ok": False,
            "status": "network_error",
            "channel": "webhook",
            "error": redact_sensitive(str(exc)),
            "webhookFingerprint": fingerprint,
        }
    result["record"] = record_feishu_notification(normalized, result, status_dir)
    return result


def _parse_json_response(response: Any) -> dict[str, Any]:
    raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"raw": raw[:500]}


def _feishu_request(url: str, body: dict[str, Any], *, headers: dict[str, str] | None = None, urlopen: Callable[..., Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return _parse_json_response(response)


def _get_tenant_access_token(app_cfg: dict[str, Any], *, urlopen: Callable[..., Any], timeout: int) -> dict[str, Any]:
    app_id = _string(app_cfg.get("appId"), 160)
    app_secret = _string(app_cfg.get("appSecret"), 300)
    cache_key = _secret_fingerprint(app_id + ":" + app_secret)
    cached = _TOKEN_CACHE.get(cache_key) or {}
    if cached.get("token") and cached.get("expiresAt", 0) > time.time() + 120:
        return {"ok": True, "token": cached["token"], "appFingerprint": _secret_fingerprint(app_id)}
    parsed = _feishu_request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
        urlopen=urlopen,
        timeout=timeout,
    )
    if parsed.get("code") != 0:
        return {
            "ok": False,
            "status": "feishu_auth_error",
            "channel": "app",
            "code": parsed.get("code", ""),
            "message": redact_sensitive(parsed.get("msg") or parsed.get("message") or parsed.get("raw") or ""),
            "appFingerprint": _secret_fingerprint(app_id),
        }
    token = _string(parsed.get("tenant_access_token"), 2000)
    expire = int(parsed.get("expire") or 7200)
    _TOKEN_CACHE[cache_key] = {"token": token, "expiresAt": time.time() + max(60, expire)}
    return {"ok": True, "token": token, "appFingerprint": _secret_fingerprint(app_id)}


def _send_feishu_app_message(payload: dict[str, Any], app_cfg: dict[str, Any], *, urlopen: Callable[..., Any], timeout: int) -> dict[str, Any]:
    app_id = _string(app_cfg.get("appId"), 160)
    receive_id = _string(app_cfg.get("receiveId"), 300)
    receive_id_type = _string(app_cfg.get("receiveIdType") or "chat_id", 40)
    if receive_id_type not in {"open_id", "user_id", "union_id", "email", "chat_id"}:
        return {
            "ok": False,
            "status": "invalid_app_config",
            "channel": "app",
            "error": f"unsupported receiveIdType: {receive_id_type}",
            "appFingerprint": _secret_fingerprint(app_id),
        }
    try:
        token_result = _get_tenant_access_token(app_cfg, urlopen=urlopen, timeout=timeout)
        if not token_result.get("ok"):
            return token_result
        parsed = _feishu_request(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
            {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(payload.get("card") or {}, ensure_ascii=False),
            },
            headers={"Authorization": f"Bearer {token_result['token']}"},
            urlopen=urlopen,
            timeout=timeout,
        )
        success = parsed.get("code") == 0
        return {
            "ok": bool(success),
            "status": "sent" if success else "feishu_error",
            "channel": "app",
            "code": parsed.get("code", ""),
            "message": redact_sensitive(parsed.get("msg") or parsed.get("message") or parsed.get("raw") or ""),
            "appFingerprint": token_result.get("appFingerprint") or _secret_fingerprint(app_id),
        }
    except urllib.error.HTTPError as exc:
        try:
            parsed = _parse_json_response(exc)
            message = parsed.get("msg") or parsed.get("message") or parsed.get("raw") or str(exc)
            code = parsed.get("code", exc.code)
        except Exception:
            message = str(exc)
            code = getattr(exc, "code", "")
        return {
            "ok": False,
            "status": "feishu_error",
            "channel": "app",
            "code": code,
            "message": redact_sensitive(message),
            "appFingerprint": _secret_fingerprint(app_id),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "status": "network_error",
            "channel": "app",
            "error": redact_sensitive(str(exc)),
            "appFingerprint": _secret_fingerprint(app_id),
        }
