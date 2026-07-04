"""Notifications service functions split from server.py.

The functions intentionally hydrate their globals from the importing server module
so this mechanical split can preserve the existing module-level helpers and
configuration while removing domain business bodies from server.py.
"""

import sys

__all__ = ['_send_feishu_workflow_notification', '_vo_public_url', '_feishu_notification_marker', '_mark_feishu_notification', '_feishu_notification_config_response', '_save_feishu_notification_config', '_feishu_notification_test_intents', '_send_feishu_notification_test_cards', '_feishu_card_action_log_path', '_feishu_card_action_user', '_feishu_card_action_value', '_feishu_card_action_form_values', '_feishu_card_action_form_text', '_feishu_card_action_success', '_feishu_card_action_error', '_feishu_meeting_action_actor', '_handle_feishu_card_action']


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _hydrate():
    srv = _server_module()
    if srv is None:
        return
    exported = set(__all__)
    for key, value in vars(srv).items():
        if key in {"_server_module", "_hydrate"}:
            continue
        if key in exported:
            globals()[key] = value
            continue
        globals()[key] = value


def _wrap_exports():
    for name in list(__all__):
        fn = globals().get(name)
        if not callable(fn) or getattr(fn, "_service_wrapper", False):
            continue

        def wrapper(*args, __fn=fn, **kwargs):
            _hydrate()
            return __fn(*args, **kwargs)

        wrapper.__name__ = getattr(fn, "__name__", name)
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        wrapper.__module__ = __name__
        wrapper._service_wrapper = True
        globals()[name] = wrapper


_wrap_exports()
_hydrate()


def _send_feishu_workflow_notification(intent):
    return send_feishu_notification(
        intent,
        webhook_url=VO_CONFIG.get("notifications", {}).get("feishuWebhook") or None,
        app_config=_feishu_app_send_config(VO_CONFIG.get("notifications", {})),
        status_dir=STATUS_DIR,
    )

def _vo_public_url(path=""):
    base = str(os.environ.get("VO_PUBLIC_URL") or os.environ.get("VO_LIVE_URL") or "").strip()
    if not base:
        base = f"http://localhost:{PORT}"
    if not re.match(r"^[a-z][a-z0-9+.-]*://", base, re.I):
        base = f"http://{base}"
    base = base.rstrip("/")
    path = str(path or "").strip()
    if not path:
        return base + "/"
    if re.match(r"^[a-z][a-z0-9+.-]*://", path, re.I) or path.startswith("lark://"):
        return path
    return base + (path if path.startswith("/") else "/" + path)

def _feishu_notification_marker(container, key):
    if not isinstance(container, dict) or not key:
        return {}
    markers = container.setdefault("feishuNotifications", {})
    if not isinstance(markers, dict):
        markers = {}
        container["feishuNotifications"] = markers
    marker = markers.get(key)
    if not isinstance(marker, dict):
        return {}
    return marker if marker.get("ok") is True else {}

def _mark_feishu_notification(container, key, result):
    if not isinstance(container, dict) or not key:
        return
    markers = container.setdefault("feishuNotifications", {})
    if not isinstance(markers, dict):
        markers = {}
        container["feishuNotifications"] = markers
    markers[key] = {
        "sentAt": _exec_meeting_now(),
        "ok": bool((result or {}).get("ok")),
        "status": str((result or {}).get("status") or (result or {}).get("code") or ""),
        "recordId": str((((result or {}).get("record") or {}).get("id")) or ""),
    }

def _feishu_notification_config_response():
    cfg = VO_CONFIG.get("notifications", {}) or {}
    receiver = _get_feishu_long_connection_receiver()
    return {
        "ok": True,
        "feishuEnabled": cfg.get("feishuEnabled", True),
        "feishuConfigured": _feishu_app_configured(cfg),
        "feishuAppConfigured": _feishu_app_configured(cfg),
        "maskedFeishuAppId": _mask_secret_value(cfg.get("feishuAppId"), 5, 4),
        "feishuReceiveIdType": cfg.get("feishuReceiveIdType") or "chat_id",
        "maskedFeishuReceiveId": _mask_secret_value(cfg.get("feishuReceiveId"), 5, 4),
        "feishuCallbackMode": "long_connection",
        "feishuLongConnection": receiver.status() if receiver else {"enabled": False, "running": False, "status": "not_started"},
    }

def _save_feishu_notification_config(body):
    webhook = str((body or {}).get("feishuWebhook") or "").strip()
    enabled = bool((body or {}).get("feishuEnabled", True))
    app_id = str((body or {}).get("feishuAppId") or "").strip()
    app_secret = str((body or {}).get("feishuAppSecret") or "").strip()
    receive_id_type = str((body or {}).get("feishuReceiveIdType") or "chat_id").strip() or "chat_id"
    receive_id = str((body or {}).get("feishuReceiveId") or "").strip()
    if webhook and not re.match(r"^https://open\.(feishu|larksuite)\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_-]+$", webhook):
        return {"ok": False, "error": "Invalid Feishu webhook URL", "code": "invalid_webhook", "_status": 400}
    if receive_id_type not in {"open_id", "user_id", "union_id", "email", "chat_id"}:
        return {"ok": False, "error": "Invalid Feishu receive ID type", "code": "invalid_receive_id_type", "_status": 400}
    notifications = {"feishuEnabled": enabled, "feishuReceiveIdType": receive_id_type}
    if webhook or (body or {}).get("clearWebhook"):
        notifications["feishuWebhook"] = webhook
    if app_id or (body or {}).get("clearApp"):
        notifications["feishuAppId"] = app_id
    if app_secret or (body or {}).get("clearApp"):
        notifications["feishuAppSecret"] = app_secret
    if receive_id or (body or {}).get("clearApp"):
        notifications["feishuReceiveId"] = receive_id
    payload = {"notifications": notifications}
    if (body or {}).get("clearWebhook"):
        payload.setdefault("_clearSecrets", []).append("notifications.feishuWebhook")
    result = _persist_setup_payload(payload)
    if not result.get("ok"):
        return result
    _start_feishu_long_connection()
    return _feishu_notification_config_response()

def _feishu_notification_test_intents():
    now = int(time.time())
    common = {
        "target": "feishu-manual-acceptance",
        "related": {"type": "acceptance", "id": "feishu-notification-module", "title": "Feishu notification module"},
    }
    return {
        "notification": {
            **common,
            "id": f"manual-test:notification:{now}",
            "type": "notification",
            "title": "VO 飞书通知验收",
            "summary": "这是一条来自 Virtual Office 的普通通知验收卡片。",
            "details": {"模块": "Feishu notification module", "类型": "notification"},
        },
        "application_form": {
            **common,
            "id": f"manual-test:application-form:{now}",
            "type": "application_form",
            "title": "VO 飞书申请表单验收",
            "summary": "这是一条申请表单验收卡片，按钮仅用于展示通用动作语义。",
            "state": "pending",
            "details": {"模块": "Feishu notification module", "处理模式": "单人最终决策"},
            "actions": [
                {"category": "confirm", "text": "同意", "value": {"action": "acceptance_approve"}},
                {"category": "cancel", "text": "拒绝", "value": {"action": "acceptance_reject"}},
            ],
        },
        "warning": {
            **common,
            "id": f"manual-test:warning:{now}",
            "type": "warning",
            "title": "VO 飞书警告验收",
            "summary": "这是一条来自 Virtual Office 的警告验收卡片，用于提示需要关注但未阻断的情况。",
            "details": {"模块": "Feishu notification module", "类型": "warning", "建议": "请关注后续处理状态"},
        },
        "error": {
            **common,
            "id": f"manual-test:error:{now}",
            "type": "error",
            "title": "VO 飞书错误验收",
            "summary": "这是一条来自 Virtual Office 的错误验收卡片，用于提示需要处理的失败状态。",
            "details": {"模块": "Feishu notification module", "类型": "error", "影响": "示例错误，不影响当前系统"},
            "error_variant": "user_facing",
        },
    }

def _send_feishu_notification_test_cards(kind=None):
    cfg = VO_CONFIG.get("notifications", {}) or {}
    webhook = cfg.get("feishuWebhook") or ""
    if not webhook and not _feishu_app_configured(cfg):
        return {"ok": False, "error": "Feishu notification app or webhook is not configured", "code": "missing_feishu_config", "_status": 400}
    intents = _feishu_notification_test_intents()
    selected = [kind] if kind in intents else ["application_form", "notification", "warning", "error"]
    results = []
    for selected_kind in selected:
        results.append(send_feishu_notification(
            intents[selected_kind],
            webhook_url=webhook,
            app_config=_feishu_app_send_config(cfg),
            status_dir=STATUS_DIR,
            timeout=20,
        ))
    ok = bool(results and all(r.get("ok") for r in results))
    response = {"ok": ok, "results": results}
    if not ok:
        failed = next((r for r in results if not r.get("ok")), {})
        detail = failed.get("message") or failed.get("error") or failed.get("status") or "Feishu test failed"
        if failed.get("code") not in ("", None):
            detail = f"{detail} (code: {failed.get('code')})"
        response["error"] = detail
    return response

def _feishu_card_action_log_path():
    return os.path.join(STATUS_DIR, "feishu-card-actions.jsonl")

def _feishu_card_action_user(event):
    user = event.get("operator") or event.get("user") or {}
    if not isinstance(user, dict):
        return {}
    return {
        "openId": str(user.get("open_id") or user.get("openId") or "").strip(),
        "userId": str(user.get("user_id") or user.get("userId") or "").strip(),
        "unionId": str(user.get("union_id") or user.get("unionId") or "").strip(),
    }

def _feishu_card_action_value(event):
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    value = action.get("value") if isinstance(action.get("value"), dict) else {}
    if not value:
        for behavior in action.get("behaviors") or []:
            if isinstance(behavior, dict) and behavior.get("type") == "callback" and isinstance(behavior.get("value"), dict):
                value = behavior["value"]
                break
    return value

def _feishu_card_action_form_values(event):
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    candidates = [
        action.get("form_value"),
        action.get("formValue"),
        action.get("form_values"),
        action.get("formValues"),
        action.get("form_value_map"),
        action.get("formValueMap"),
        event.get("form_value"),
        event.get("formValue"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}

def _feishu_card_action_form_text(event, *names):
    values = _feishu_card_action_form_values(event)
    for name in names:
        if name in values:
            value = values.get(name)
            if isinstance(value, dict):
                value = value.get("value") or value.get("text") or value.get("content")
            if isinstance(value, list):
                value = "\n".join(str(item) for item in value if item is not None)
            text = str(value or "").strip()
            if text:
                return text
    return ""

def _feishu_card_action_success(content):
    return {"type": "success", "content": content}

def _feishu_card_action_error(content):
    return {"type": "error", "content": content}

def _feishu_meeting_action_actor(event, fallback="feishu"):
    user = _feishu_card_action_user(event)
    return user.get("userId") or user.get("openId") or user.get("unionId") or fallback

def _handle_feishu_card_action(body):
    if not isinstance(body, dict):
        return {"ok": False, "error": "Invalid Feishu callback body", "_status": 400}
    challenge = body.get("challenge")
    if isinstance(challenge, str) and challenge:
        return {"challenge": challenge}

    event = body.get("event") if isinstance(body.get("event"), dict) else body
    value = _feishu_card_action_value(event)
    action = str(value.get("action") or "").strip()
    meeting_outcome = _dispatch_feishu_meeting_request_action(action, str(value.get("request_id") or "").strip(), event)
    project_outcome = {"handled": False} if meeting_outcome.get("handled") else _dispatch_feishu_project_execution_action(action, value, event)
    outcome = meeting_outcome if meeting_outcome.get("handled") else (project_outcome if project_outcome.get("handled") else None)
    record = _record_feishu_card_action(body, event, value, outcome=outcome)
    if meeting_outcome.get("handled"):
        return {
            "ok": bool(meeting_outcome.get("ok")),
            "toast": meeting_outcome.get("toast") or _feishu_card_action_success("操作已收到"),
            "recordId": record["id"],
            "outcome": {k: v for k, v in meeting_outcome.items() if k not in {"toast"}},
        }
    if project_outcome.get("handled"):
        return {
            "ok": bool(project_outcome.get("ok")),
            "toast": project_outcome.get("toast") or _feishu_card_action_success("操作已收到"),
            "recordId": record["id"],
            "outcome": {k: v for k, v in project_outcome.items() if k not in {"toast"}},
        }
    return {
        "ok": True,
        "toast": {"type": "success", "content": "操作已收到"},
        "recordId": record["id"],
    }

_wrap_exports()
_hydrate()
