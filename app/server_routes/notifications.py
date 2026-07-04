from .http import JsonBodyError, read_json, send_json


def _notifications_service():
    from server_services import notifications
    notifications._hydrate()
    return notifications


def handle_get(handler, parsed_url):
    if parsed_url.path != "/api/feishu-notification/config":
        return False
    notifications_service = _notifications_service()
    return send_json(handler, notifications_service._feishu_notification_config_response())


def handle_post(handler, parsed_url):
    notifications_service = _notifications_service()
    if parsed_url.path == "/api/feishu-notification/config":
        try:
            body = read_json(handler)
            result = notifications_service._save_feishu_notification_config(body)
        except JsonBodyError as e:
            result = {"ok": False, "error": str(e), "_status": 400}
        return send_json(handler, result)
    if parsed_url.path == "/api/feishu-notification/test":
        try:
            body = read_json(handler)
            result = notifications_service._send_feishu_notification_test_cards(str((body or {}).get("kind") or ""))
        except JsonBodyError as e:
            result = {"ok": False, "error": str(e), "_status": 400}
        return send_json(handler, result)
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
