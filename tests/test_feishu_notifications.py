import json
import os
import sys
import tempfile
import urllib.error


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from feishu_notifications import (  # noqa: E402
    FeishuNotificationError,
    build_feishu_card,
    send_feishu_notification,
    validate_notification_intent,
)


def base_intent(kind="notification"):
    return {
        "type": kind,
        "title": "VO 测试通知",
        "summary": "这是一条测试通知。",
        "related": {"type": "task", "id": "task-1", "title": "Demo task"},
        "details": {"项目": "Demo", "状态": "Ready"},
    }


def read_records(status_dir):
    path = os.path.join(status_dir, "feishu-notification-records.jsonl")
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_four_notification_types_render_interactive_cards():
    for kind in ("application_form", "notification", "warning", "error"):
        intent = base_intent(kind)
        if kind == "application_form":
            intent["state"] = "pending"
            intent["actions"] = [{"category": "confirm", "text": "同意", "value": {"request_id": "req-1"}}]
        if kind == "error":
            intent["error_variant"] = "user_facing"
            intent["audience"] = "both"
        card = build_feishu_card(intent)
        assert card["msg_type"] == "interactive"
        assert card["card"]["header"]["title"]["content"] == "VO 测试通知"
        assert card["card"]["header"]["template"] in {"blue", "green", "orange", "red"}


def test_application_form_actions_and_states_are_validated():
    intent = base_intent("application_form")
    intent.update({
        "state": "expired",
        "multi_participant": True,
        "actions": [
            {"category": "confirm", "text": "同意", "value": {"action": "approve"}},
            {"category": "cancel", "text": "拒绝", "value": {"action": "reject"}},
            {"category": "jump", "text": "查看详情", "url": "/detail"},
        ],
    })
    card = build_feishu_card(intent)
    action_block = card["card"]["elements"][-1]
    assert action_block["tag"] == "action"
    assert [button["text"]["content"] for button in action_block["actions"]] == ["同意", "拒绝", "查看详情"]
    assert action_block["actions"][0]["value"]["callback_status"] == "not_implemented"

    bad = dict(intent, state="unknown")
    try:
        validate_notification_intent(bad)
    except FeishuNotificationError as exc:
        assert "unsupported application form state" in str(exc)
    else:
        raise AssertionError("invalid application form state should fail")


def test_non_application_notifications_only_allow_jump_actions():
    intent = base_intent("warning")
    intent["actions"] = [{"category": "jump", "text": "查看", "url": "/projects"}]
    assert build_feishu_card(intent)["card"]["elements"][-1]["tag"] == "action"

    bad = base_intent("notification")
    bad["actions"] = [{"category": "confirm", "text": "确认", "value": {}}]
    try:
        validate_notification_intent(bad)
    except FeishuNotificationError as exc:
        assert "non-application notifications only support jump actions" in str(exc)
    else:
        raise AssertionError("decision action should fail for non-application notification")


def test_error_variants_do_not_leak_secrets_to_user_card():
    secret = "webhook=https://open.feishu.cn/open-apis/bot/v2/hook/secret-token password=abc123"
    user_card = build_feishu_card({
        **base_intent("error"),
        "error_variant": "user_facing",
        "diagnostic": secret,
    })
    rendered = json.dumps(user_card, ensure_ascii=False)
    assert "secret-token" not in rendered
    assert "abc123" not in rendered

    admin_card = build_feishu_card({
        **base_intent("error"),
        "error_variant": "admin_facing",
        "diagnostic": secret,
    })
    admin_rendered = json.dumps(admin_card, ensure_ascii=False)
    assert "[REDACTED]" in admin_rendered
    assert "secret-token" not in admin_rendered
    assert "abc123" not in admin_rendered


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body.encode("utf-8")

    def close(self):
        return None


def test_sender_uses_fake_http_and_records_success_without_leaking_webhook():
    with tempfile.TemporaryDirectory() as status_dir:
        calls = []

        def fake_urlopen(request, timeout=0):
            calls.append((request.full_url, timeout, request.data))
            return FakeResponse('{"StatusCode":0,"StatusMessage":"success","code":0,"msg":"success"}')

        webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/super-secret-token"
        result = send_feishu_notification(
            base_intent("notification"),
            webhook_url=webhook,
            status_dir=status_dir,
            urlopen=fake_urlopen,
        )
        assert result["ok"] is True
        assert result["status"] == "sent"
        assert calls and calls[0][0] == webhook
        records = read_records(status_dir)
        assert records[0]["ok"] is True
        assert records[0]["webhookFingerprint"]
        assert "super-secret-token" not in json.dumps(records, ensure_ascii=False)


def test_sender_uses_app_credentials_and_records_success_without_leaking_secret():
    with tempfile.TemporaryDirectory() as status_dir:
        calls = []

        def fake_urlopen(request, timeout=0):
            calls.append((request.full_url, dict(request.header_items()), request.data.decode("utf-8")))
            if "/auth/v3/tenant_access_token/internal" in request.full_url:
                return FakeResponse('{"code":0,"msg":"ok","tenant_access_token":"tenant-token-secret","expire":7200}')
            if "/im/v1/messages" in request.full_url:
                assert "receive_id_type=chat_id" in request.full_url
                assert any(k.lower() == "authorization" and v == "Bearer tenant-token-secret" for k, v in request.header_items())
                body = json.loads(request.data.decode("utf-8"))
                assert body["receive_id"] == "oc_demo"
                assert body["msg_type"] == "interactive"
                assert json.loads(body["content"])["header"]["title"]["content"] == "VO 测试通知"
                return FakeResponse('{"code":0,"msg":"success","data":{"message_id":"om_1"}}')
            raise AssertionError("unexpected URL: " + request.full_url)

        result = send_feishu_notification(
            base_intent("notification"),
            app_config={
                "appId": "cli_demo",
                "appSecret": "app-secret-should-not-leak",
                "receiveIdType": "chat_id",
                "receiveId": "oc_demo",
            },
            status_dir=status_dir,
            urlopen=fake_urlopen,
        )
        assert result["ok"] is True
        assert result["status"] == "sent"
        assert result["channel"] == "app"
        assert len(calls) == 2
        records = read_records(status_dir)
        serialized = json.dumps(records, ensure_ascii=False)
        assert records[0]["channel"] == "app"
        assert records[0]["appFingerprint"]
        assert "app-secret-should-not-leak" not in serialized
        assert "tenant-token-secret" not in serialized


def test_sender_surfaces_feishu_app_http_error_body():
    with tempfile.TemporaryDirectory() as status_dir:

        def fake_urlopen(request, timeout=0):
            if "/auth/v3/tenant_access_token/internal" in request.full_url:
                return FakeResponse('{"code":0,"msg":"ok","tenant_access_token":"tenant-token-secret","expire":7200}')
            if "/im/v1/messages" in request.full_url:
                raise urllib.error.HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    {},
                    FakeResponse('{"code":99991663,"msg":"invalid receive_id"}'),
                )
            raise AssertionError("unexpected URL: " + request.full_url)

        result = send_feishu_notification(
            base_intent("notification"),
            app_config={
                "appId": "cli_demo",
                "appSecret": "app-secret-should-not-leak",
                "receiveIdType": "chat_id",
                "receiveId": "bad_chat",
            },
            status_dir=status_dir,
            urlopen=fake_urlopen,
        )
        assert result["ok"] is False
        assert result["status"] == "feishu_error"
        assert result["code"] == 99991663
        assert "invalid receive_id" in result["message"]


def test_sender_records_non_success_network_failure_and_missing_webhook():
    with tempfile.TemporaryDirectory() as status_dir:

        def feishu_error(request, timeout=0):
            return FakeResponse('{"StatusCode":9499,"StatusMessage":"bad secret token"}')

        result = send_feishu_notification(
            base_intent("notification"),
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/token-1",
            status_dir=status_dir,
            urlopen=feishu_error,
        )
        assert result["ok"] is False
        assert result["status"] == "feishu_error"

        def network_error(request, timeout=0):
            raise urllib.error.URLError("connection refused token-2")

        result = send_feishu_notification(
            base_intent("warning"),
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/token-2",
            status_dir=status_dir,
            urlopen=network_error,
        )
        assert result["ok"] is False
        assert result["status"] == "network_error"

        result = send_feishu_notification(base_intent("notification"), webhook_url="", status_dir=status_dir)
        assert result["ok"] is True
        assert result["status"] == "skipped_missing_webhook"

        records = read_records(status_dir)
        assert [r["status"] for r in records] == ["feishu_error", "network_error", "skipped_missing_webhook"]
        serialized = json.dumps(records, ensure_ascii=False)
        assert "token-1" not in serialized
        assert "token-2" not in serialized


def test_invalid_intent_records_structured_error():
    with tempfile.TemporaryDirectory() as status_dir:
        result = send_feishu_notification({"type": "wat", "title": "", "summary": ""}, status_dir=status_dir)
        assert result["ok"] is False
        assert result["status"] == "invalid_intent"
        record = read_records(status_dir)[0]
        assert record["status"] == "invalid_intent"
        assert record["ok"] is False


def test_setup_config_masks_feishu_webhook_and_preserves_blank_secret():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-feishu-config-")
    import server

    existing = {"notifications": {
        "feishuWebhook": "https://open.feishu.cn/open-apis/bot/v2/hook/original-token",
        "feishuAppSecret": "original-app-secret",
        "feishuEnabled": True,
    }}
    merged = server._merge_setup_config(existing, {"notifications": {"feishuWebhook": "", "feishuAppSecret": "", "feishuEnabled": False}})
    assert merged["notifications"]["feishuWebhook"].endswith("original-token")
    assert merged["notifications"]["feishuAppSecret"] == "original-app-secret"
    assert merged["notifications"]["feishuEnabled"] is False

    masked = server._mask_feishu_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/original-token")
    assert "original-token" not in masked
    assert "••••" in masked


def test_feishu_config_save_returns_app_mask_and_clears_webhook():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-app-config-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    server._persist_setup_payload({
        "notifications": {
            "feishuWebhook": "https://open.feishu.cn/open-apis/bot/v2/hook/old-token",
            "feishuEnabled": True,
        }
    })
    result = server._save_feishu_notification_config({
        "feishuEnabled": True,
        "feishuAppId": "cli_demo_app",
        "feishuAppSecret": "secret-should-not-return",
        "feishuReceiveIdType": "chat_id",
        "feishuReceiveId": "oc_demo_chat",
        "clearWebhook": True,
    })
    assert result["ok"] is True
    assert result["feishuAppConfigured"] is True
    assert result["maskedFeishuAppId"]
    assert result["maskedFeishuReceiveId"]
    serialized = json.dumps(result, ensure_ascii=False)
    assert "secret-should-not-return" not in serialized
    with open(os.path.join(status_dir, "vo-config.json"), "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["notifications"]["feishuWebhook"] == ""


def test_manual_test_intents_cover_all_notification_types():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    import server

    intents = server._feishu_notification_test_intents()
    assert set(intents) == {"application_form", "notification", "warning", "error"}
    assert {intent["type"] for intent in intents.values()} == {"application_form", "notification", "warning", "error"}


def test_feishu_card_action_challenge_and_recording():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-card-action-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    server.STATUS_DIR = status_dir
    assert server._handle_feishu_card_action({"challenge": "abc123"}) == {"challenge": "abc123"}
    try:
        result = server._handle_feishu_card_action({
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_demo"},
                "open_message_id": "om_demo",
                "action": {
                    "value": {
                        "action": "acceptance_approve",
                        "notification_id": "manual-test",
                        "action_category": "confirm",
                    }
                },
            },
        })
        assert result["ok"] is True
        with open(os.path.join(status_dir, "feishu-card-actions.jsonl"), "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    finally:
        server.STATUS_DIR = previous_status_dir
    assert rows[0]["action"] == "acceptance_approve"
    assert rows[0]["notificationId"] == "manual-test"
    assert rows[0]["user"]["openId"] == "ou_demo"


def test_feishu_card_action_verification_token_rejects_mismatch():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-feishu-card-token-")
    import server

    previous = server.VO_CONFIG.setdefault("notifications", {}).get("feishuVerificationToken")
    try:
        server.VO_CONFIG.setdefault("notifications", {})["feishuVerificationToken"] = "expected-token"
        result = server._handle_feishu_card_action({
            "header": {"token": "wrong-token", "event_type": "card.action.trigger"},
            "event": {"action": {"value": {"action": "acceptance_approve"}}},
        })
        assert result["_status"] == 401
    finally:
        server.VO_CONFIG.setdefault("notifications", {})["feishuVerificationToken"] = previous or ""


if __name__ == "__main__":
    test_four_notification_types_render_interactive_cards()
    test_application_form_actions_and_states_are_validated()
    test_non_application_notifications_only_allow_jump_actions()
    test_error_variants_do_not_leak_secrets_to_user_card()
    test_sender_uses_fake_http_and_records_success_without_leaking_webhook()
    test_sender_uses_app_credentials_and_records_success_without_leaking_secret()
    test_sender_surfaces_feishu_app_http_error_body()
    test_sender_records_non_success_network_failure_and_missing_webhook()
    test_invalid_intent_records_structured_error()
    test_setup_config_masks_feishu_webhook_and_preserves_blank_secret()
    test_feishu_config_save_returns_app_mask_and_clears_webhook()
    test_manual_test_intents_cover_all_notification_types()
    test_feishu_card_action_challenge_and_recording()
    test_feishu_card_action_verification_token_rejects_mismatch()
    print("test_feishu_notifications.py passed")
