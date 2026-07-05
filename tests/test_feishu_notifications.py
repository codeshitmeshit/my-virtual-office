import io
import json
import os
import sys
import tempfile
import types
import urllib.error


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from feishu_notifications import (  # noqa: E402
    FeishuNotificationError,
    build_feishu_card,
    send_feishu_markdown_message,
    send_feishu_notification,
    send_feishu_text_message,
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


def call_office_handler(server, method, path, body=None, headers=None):
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    handler = server.OfficeHandler.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(payload)), **(headers or {})}
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler._status = None
    handler._headers = []

    def send_response(self, status, message=None):
        self._status = status

    def send_header(self, key, value):
        self._headers.append((key, value))

    def end_headers(self):
        return None

    handler.send_response = types.MethodType(send_response, handler)
    handler.send_header = types.MethodType(send_header, handler)
    handler.end_headers = types.MethodType(end_headers, handler)
    if method == "POST":
        server.OfficeHandler.do_POST(handler)
    else:
        server.OfficeHandler.do_GET(handler)
    return handler._status, json.loads(handler.wfile.getvalue().decode("utf-8"))


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
        "inputs": [{
            "name": "feedback",
            "label": "返工原因",
            "placeholder": "说明需要调整的内容",
            "multiline": True,
        }],
        "actions": [
            {"category": "confirm", "text": "同意", "value": {"action": "approve"}},
            {"category": "cancel", "text": "拒绝", "value": {"action": "reject"}},
            {"category": "jump", "text": "查看详情", "url": "/detail"},
        ],
    })
    card = build_feishu_card(intent)
    assert card["card"]["schema"] == "2.0"
    elements = card["card"]["body"]["elements"]
    form = next(element for element in elements if element["tag"] == "form")
    input_block = next(element for element in form["elements"] if element["tag"] == "input")
    assert input_block["name"] == "feedback"
    assert input_block["input_type"] == "multiline_text"
    button_row = next(element for element in form["elements"] if element["tag"] == "column_set")
    buttons = [column["elements"][0] for column in button_row["columns"]]
    assert [button["text"]["content"] for button in buttons] == ["同意", "拒绝", "查看详情"]
    assert buttons[0]["form_action_type"] == "submit"
    assert buttons[0]["action_type"] == "form_submit"
    assert buttons[0]["behaviors"][0]["value"]["callback_status"] == "not_implemented"
    assert buttons[1]["form_action_type"] == "submit"
    assert buttons[1]["action_type"] == "form_submit"
    assert buttons[1]["behaviors"][0]["value"]["callback_status"] == "not_implemented"
    assert buttons[2]["behaviors"][0]["default_url"] == "/detail"

    bad = dict(intent, state="unknown")
    try:
        validate_notification_intent(bad)
    except FeishuNotificationError as exc:
        assert "unsupported application form state" in str(exc)
    else:
        raise AssertionError("invalid application form state should fail")


def test_approved_application_form_uses_green_card_header():
    intent = base_intent("application_form")
    intent.update({
        "state": "approved",
        "title": "会议申请已同意: Demo meeting",
        "actions": [{"category": "jump", "text": "查看会议", "url": "/#meeting=m-1"}],
    })

    card = build_feishu_card(intent)

    assert card["card"]["header"]["template"] == "green"


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


def test_text_sender_uses_chat_app_credentials_without_leaking_secret():
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append((request.full_url, dict(request.header_items()), request.data.decode("utf-8")))
        if "/auth/v3/tenant_access_token/internal" in request.full_url:
            body = json.loads(request.data.decode("utf-8"))
            assert body["app_id"] == "cli_chat"
            assert body["app_secret"] == "chat-secret-should-not-leak"
            return FakeResponse('{"code":0,"msg":"ok","tenant_access_token":"tenant-token-secret","expire":7200}')
        if "/im/v1/messages" in request.full_url:
            assert "receive_id_type=chat_id" in request.full_url
            assert any(k.lower() == "authorization" and v == "Bearer tenant-token-secret" for k, v in request.header_items())
            body = json.loads(request.data.decode("utf-8"))
            assert body["receive_id"] == "oc_chat"
            assert body["msg_type"] == "text"
            sent_text = json.loads(body["content"])["text"]
            assert sent_text == "CEO (by Hermes): hello"
            return FakeResponse('{"code":0,"msg":"success","data":{"message_id":"om_text_1"}}')
        raise AssertionError("unexpected URL: " + request.full_url)

    result = send_feishu_text_message(
        "CEO (by Hermes):\nhello",
        app_config={
            "appId": "cli_chat",
            "appSecret": "chat-secret-should-not-leak",
        },
        receive_id="oc_chat",
        receive_id_type="chat_id",
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["status"] == "sent"
    assert result["channel"] == "app_text"
    assert result["messageId"] == "om_text_1"
    serialized = json.dumps(result, ensure_ascii=False)
    assert "chat-secret-should-not-leak" not in serialized
    assert "tenant-token-secret" not in serialized
    assert len(calls) == 2


def test_markdown_sender_preserves_markdown_without_prefix():
    markdown = "当前 VO 里有 2 个 agent:\n\n| id | 名称 |\n|---|---|\n| `codex-local` | Codex |"

    def fake_urlopen(request, timeout=0):
        if "/auth/v3/tenant_access_token/internal" in request.full_url:
            return FakeResponse('{"code":0,"msg":"ok","tenant_access_token":"tenant-token-secret","expire":7200}')
        if "/im/v1/messages" in request.full_url:
            body = json.loads(request.data.decode("utf-8"))
            assert body["receive_id"] == "oc_chat"
            assert body["msg_type"] == "interactive"
            card = json.loads(body["content"])
            content = card["body"]["elements"][0]["content"]
            assert content == markdown
            assert not content.startswith("CEO (by")
            assert "\n|---|---|" in content
            return FakeResponse('{"code":0,"msg":"success","data":{"message_id":"om_markdown_1"}}')
        raise AssertionError("unexpected URL: " + request.full_url)

    result = send_feishu_markdown_message(
        markdown,
        app_config={
            "appId": "cli_chat",
            "appSecret": "chat-secret-should-not-leak",
        },
        receive_id="oc_chat",
        receive_id_type="chat_id",
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["status"] == "sent"
    assert result["channel"] == "app_markdown"
    assert result["messageId"] == "om_markdown_1"


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

    class FakeReceiver:
        def __init__(self, app_id="", app_secret="", action_handler=None):
            self.app_id = app_id
            self.app_secret = app_secret
            self.action_handler = action_handler

        def start(self):
            return {"enabled": True, "running": True, "status": "running"}

        def status(self):
            return {"enabled": True, "running": True, "status": "running"}

    previous_receiver_cls = server.FeishuLongConnectionReceiver
    previous_receiver = server._FEISHU_LONG_CONNECTION_RECEIVER
    server.FeishuLongConnectionReceiver = FakeReceiver
    server._FEISHU_LONG_CONNECTION_RECEIVER = None
    server._persist_setup_payload({
        "notifications": {
            "feishuWebhook": "https://open.feishu.cn/open-apis/bot/v2/hook/old-token",
            "feishuEnabled": True,
        }
    })
    try:
        result = server._save_feishu_notification_config({
            "feishuEnabled": True,
            "feishuAppId": "cli_demo_app",
            "feishuAppSecret": "secret-should-not-return",
            "feishuReceiveIdType": "chat_id",
            "feishuReceiveId": "oc_demo_chat",
            "clearWebhook": True,
        })
    finally:
        server.FeishuLongConnectionReceiver = previous_receiver_cls
        server._FEISHU_LONG_CONNECTION_RECEIVER = previous_receiver
    assert result["ok"] is True
    assert result["feishuAppConfigured"] is True
    assert result["maskedFeishuAppId"]
    assert result["maskedFeishuReceiveId"]
    assert result["feishuCallbackMode"] == "long_connection"
    assert result["feishuLongConnection"]["status"] == "running"
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


def test_feishu_long_connection_event_conversion():
    from feishu_long_connection import FeishuLongConnectionReceiver

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    data = Obj(
        header=Obj(event_id="evt_demo"),
        event=Obj(
            operator=Obj(open_id="ou_demo", user_id="u_demo", union_id="on_demo"),
            context=Obj(open_message_id="om_demo", open_chat_id="oc_demo"),
            action=Obj(value={"action": "acceptance_approve"}, tag="button", option="", name="approve"),
        ),
    )
    body = FeishuLongConnectionReceiver._event_to_body(data)
    assert body["header"]["event_type"] == "card.action.trigger"
    assert body["event"]["operator"]["open_id"] == "ou_demo"
    assert body["event"]["open_message_id"] == "om_demo"
    assert body["event"]["action"]["value"]["action"] == "acceptance_approve"


def test_feishu_long_connection_message_event_conversion():
    from feishu_long_connection import FeishuLongConnectionReceiver

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    data = Obj(
        header=Obj(event_id="evt_msg"),
        event=Obj(
            sender=Obj(sender_id=Obj(open_id="ou_sender", user_id="u_sender", union_id="on_sender")),
            message=Obj(
                message_id="om_demo",
                chat_id="oc_demo",
                chat_type="p2p",
                message_type="text",
                content=json.dumps({"text": "hello from feishu"}),
            ),
        ),
    )
    body = FeishuLongConnectionReceiver._message_event_to_body(data)
    assert body["header"]["event_type"] == "im.message.receive_v1"
    assert body["event"]["sender"]["sender_id"]["open_id"] == "ou_sender"
    assert body["event"]["message"]["message_id"] == "om_demo"
    assert body["event"]["message"]["chat_id"] == "oc_demo"
    assert body["event"]["message"]["text"] == "hello from feishu"


def test_feishu_long_connection_message_handler_is_invoked():
    from feishu_long_connection import FeishuLongConnectionReceiver

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    calls = []
    receiver = FeishuLongConnectionReceiver(
        app_id="cli_demo",
        app_secret="secret",
        message_handler=lambda body: calls.append(body),
        name="test-feishu-chat-receiver",
    )
    data = Obj(
        header=Obj(event_id="evt_msg_handler"),
        event=Obj(
            sender=Obj(sender_id=Obj(open_id="ou_sender")),
            message=Obj(
                message_id="om_handler",
                chat_id="oc_handler",
                chat_type="p2p",
                message_type="text",
                content=json.dumps({"text": "handler hello"}),
            ),
        ),
    )

    receiver._handle_message_event(data)

    assert len(calls) == 1
    assert calls[0]["header"]["event_type"] == "im.message.receive_v1"
    assert calls[0]["event"]["sender"]["sender_id"]["open_id"] == "ou_sender"
    assert calls[0]["event"]["message"]["message_id"] == "om_handler"
    assert calls[0]["event"]["message"]["text"] == "handler hello"
    status = receiver.status()
    assert status["running"] is True
    assert status["status"] == "running"
    assert status["lastEventAt"] > 0


def test_feishu_chat_config_is_separate_from_notification_app():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-chat-config-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    class FakeChatWorker:
        def __init__(self, app_id="", app_secret="", callback_url="", status_dir=""):
            self.app_id = app_id
            self.app_secret = app_secret
            self.callback_url = callback_url
            self.status_dir = status_dir

        def start(self):
            return {"enabled": True, "running": True, "status": "running", "mode": "subprocess"}

        def status(self):
            return {"enabled": True, "running": True, "status": "running", "mode": "subprocess"}

    previous_worker_cls = server.FeishuChatWorkerProcess
    previous_chat_receiver = server._FEISHU_CHAT_LONG_CONNECTION_RECEIVER
    server.FeishuChatWorkerProcess = FakeChatWorker
    server._FEISHU_CHAT_LONG_CONNECTION_RECEIVER = None
    server._persist_setup_payload({
        "notifications": {
            "feishuEnabled": True,
            "feishuAppId": "cli_notification",
            "feishuAppSecret": "notification-secret",
            "feishuReceiveId": "oc_notification",
        }
    })
    try:
        result = server._save_feishu_chat_config({
            "enabled": True,
            "appId": "cli_chat",
            "appSecret": "chat-secret",
        })
    finally:
        server.FeishuChatWorkerProcess = previous_worker_cls
        server._FEISHU_CHAT_LONG_CONNECTION_RECEIVER = previous_chat_receiver

    assert result["ok"] is True
    assert result["configured"] is True
    assert result["longConnection"]["status"] == "running"
    assert result["longConnection"]["mode"] == "subprocess"
    serialized = json.dumps(result, ensure_ascii=False)
    assert "chat-secret" not in serialized
    with open(os.path.join(status_dir, "vo-config.json"), "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["notifications"]["feishuAppId"] == "cli_notification"
    assert saved["notifications"]["feishuAppSecret"] == "notification-secret"
    assert saved["feishu"]["chatApp"]["appId"] == "cli_chat"
    assert saved["feishu"]["chatApp"]["appSecret"] == "chat-secret"


def test_disabling_feishu_chat_config_stops_existing_long_connection():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-chat-disable-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    class FakeRunningReceiver:
        app_id = "cli_chat"
        app_secret = "chat-secret"

        def __init__(self):
            self.stopped = False

        def status(self):
            return {"enabled": True, "running": True, "status": "running"}

        def stop(self):
            self.stopped = True
            return {"enabled": False, "running": False, "status": "stopped"}

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_receiver = server._FEISHU_CHAT_LONG_CONNECTION_RECEIVER
    receiver = FakeRunningReceiver()
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {},
        },
    }
    server._FEISHU_CHAT_LONG_CONNECTION_RECEIVER = receiver
    try:
        result = server._save_feishu_chat_config({"enabled": False})
    finally:
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config
        server._FEISHU_CHAT_LONG_CONNECTION_RECEIVER = previous_receiver

    assert result["ok"] is True
    assert result["enabled"] is False
    assert result["longConnection"]["running"] is False
    assert result["longConnection"]["status"] == "disabled"
    assert receiver.stopped is True


def test_feishu_chat_config_rejects_unknown_representative_agent():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-chat-invalid-agent-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    result = server._save_feishu_chat_config({
        "enabled": True,
        "appId": "cli_chat",
        "appSecret": "chat-secret",
        "representativeAgentId": "definitely-missing-agent",
    })

    assert result["ok"] is False
    assert result["code"] == "agent_not_found"
    assert result["_status"] == 404


def test_feishu_channel_adapter_records_and_dedupes():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({
            "agent_id": agent_id,
            "message": message,
            "conversation_id": conversation_id,
            "source_meta": source_meta,
        })
        return {"ok": True, "reply": "CEO reply", "conversationId": conversation_id}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    body = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_bound"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": {"text": "hello"},
                "text": "hello",
            },
        }
    }
    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event(body, send_text=fake_send)
        duplicate = server._handle_feishu_chat_message_event(body, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert result["reply"] == "CEO reply"
    assert duplicate["idempotent"] is True
    assert len(calls) == 1
    assert calls[0]["agent_id"] == "hermes-default"
    assert calls[0]["source_meta"]["sourceMessageId"] == "om_1"
    assert sends == [{"chat_id": "oc_1", "text": "CEO reply"}]
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert {row["event"] for row in rows} >= {"user_message", "turn_completed"}
    completed = [row for row in rows if row["event"] == "turn_completed"][0]
    assert completed["sourceMessageId"] == "om_1"
    assert completed["representativeAgentId"] == "hermes-default"
    assert completed["reply"] == "CEO reply"
    assert completed["feishuReply"] == "CEO reply"
    with open(os.path.join(status_dir, "agent-platform-communications.jsonl"), "r", encoding="utf-8") as f:
        comm_rows = [json.loads(line) for line in f if line.strip()]
    visible_rows = [row for row in comm_rows if row.get("visibleInOffice", True)]
    assert [row["direction"] for row in visible_rows] == ["request", "reply"]
    assert visible_rows[0]["metadata"]["sourceApp"] == "feishu"
    assert visible_rows[0]["metadata"]["sourceMessageId"] == "om_1"
    assert visible_rows[1]["text"] == "CEO reply"
    delivery_rows = [row for row in comm_rows if row.get("operation") == "feishu_delivery"]
    assert delivery_rows[0]["metadata"]["feishuSendResult"]["status"] == "sent"


def test_feishu_channel_adds_and_deletes_message_reaction_receipt():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-receipt-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    previous_send = server._feishu_chat_app_text_send
    previous_receipt = server._feishu_chat_app_receipt_send
    previous_recall = server._feishu_chat_app_message_recall
    previous_reaction_add = server._feishu_chat_app_reaction_add
    previous_reaction_delete = server._feishu_chat_app_reaction_delete
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "codex-local",
            },
            "bindings": {"open_id:ou_receipt": "user-1"},
        },
    }
    operations = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        operations.append({"op": "dispatch", "agent_id": agent_id, "message": message})
        return {"ok": True, "reply": "正式回复", "conversationId": conversation_id}

    def fake_send(chat_id, text):
        operations.append({"op": "send", "chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "messageId": "om_final"}

    def fake_receipt(chat_id, text):
        operations.append({"op": "receipt", "chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "messageId": "om_receipt"}

    def fake_recall(message_id):
        operations.append({"op": "recall", "message_id": message_id})
        return {"ok": True, "status": "recalled", "messageId": message_id}

    def fake_reaction_add(message_id, emoji_type):
        operations.append({"op": "reaction_add", "message_id": message_id, "emoji_type": emoji_type})
        return {"ok": True, "status": "added", "reactionId": "reaction_1", "emojiType": emoji_type}

    def fake_reaction_delete(message_id, reaction_id):
        operations.append({"op": "reaction_delete", "message_id": message_id, "reaction_id": reaction_id})
        return {"ok": True, "status": "deleted", "reactionId": reaction_id}

    body = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_receipt"}},
            "message": {
                "message_id": "om_receipt_source",
                "chat_id": "oc_receipt",
                "chat_type": "p2p",
                "message_type": "text",
                "content": {"text": "hello"},
            },
        }
    }
    try:
        server._dispatch_representative_agent_message = fake_dispatch
        server._feishu_chat_app_text_send = fake_send
        server._feishu_chat_app_receipt_send = fake_receipt
        server._feishu_chat_app_message_recall = fake_recall
        server._feishu_chat_app_reaction_add = fake_reaction_add
        server._feishu_chat_app_reaction_delete = fake_reaction_delete
        result = server._handle_feishu_chat_message_event(body)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server._feishu_chat_app_text_send = previous_send
        server._feishu_chat_app_receipt_send = previous_receipt
        server._feishu_chat_app_message_recall = previous_recall
        server._feishu_chat_app_reaction_add = previous_reaction_add
        server._feishu_chat_app_reaction_delete = previous_reaction_delete
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert [item["op"] for item in operations] == ["reaction_add", "dispatch", "send", "reaction_delete"]
    assert operations[0]["message_id"] == "om_receipt_source"
    assert operations[0]["emoji_type"] == "LGTM"
    assert operations[2]["text"] == "正式回复"
    assert operations[3]["message_id"] == "om_receipt_source"
    assert operations[3]["reaction_id"] == "reaction_1"
    completed = result["record"]
    assert completed["reactionResult"]["reactionId"] == "reaction_1"
    assert completed["reactionDeleteResult"]["status"] == "deleted"
    assert completed["receiptResult"] == {}


def test_feishu_channel_falls_back_to_temporary_receipt_when_reaction_fails():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-receipt-fallback-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    previous_send = server._feishu_chat_app_text_send
    previous_receipt = server._feishu_chat_app_receipt_send
    previous_recall = server._feishu_chat_app_message_recall
    previous_reaction_add = server._feishu_chat_app_reaction_add
    previous_reaction_delete = server._feishu_chat_app_reaction_delete
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "codex-local",
            },
            "bindings": {"open_id:ou_receipt_fallback": "user-1"},
        },
    }
    operations = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        operations.append({"op": "dispatch"})
        return {"ok": True, "reply": "正式回复", "conversationId": conversation_id}

    def fake_send(chat_id, text):
        operations.append({"op": "send", "text": text})
        return {"ok": True, "status": "sent", "messageId": "om_final"}

    def fake_receipt(chat_id, text):
        operations.append({"op": "receipt", "chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "messageId": "om_receipt"}

    def fake_recall(message_id):
        operations.append({"op": "recall", "message_id": message_id})
        return {"ok": True, "status": "recalled", "messageId": message_id}

    def fake_reaction_add(message_id, emoji_type):
        operations.append({"op": "reaction_add", "message_id": message_id, "emoji_type": emoji_type})
        return {"ok": False, "status": "feishu_error", "code": 999}

    def fake_reaction_delete(message_id, reaction_id):
        operations.append({"op": "reaction_delete", "message_id": message_id, "reaction_id": reaction_id})
        return {"ok": True, "status": "deleted", "reactionId": reaction_id}

    body = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_receipt_fallback"}},
            "message": {
                "message_id": "om_receipt_fallback_source",
                "chat_id": "oc_receipt_fallback",
                "chat_type": "p2p",
                "message_type": "text",
                "content": {"text": "hello"},
            },
        }
    }
    try:
        server._dispatch_representative_agent_message = fake_dispatch
        server._feishu_chat_app_text_send = fake_send
        server._feishu_chat_app_receipt_send = fake_receipt
        server._feishu_chat_app_message_recall = fake_recall
        server._feishu_chat_app_reaction_add = fake_reaction_add
        server._feishu_chat_app_reaction_delete = fake_reaction_delete
        result = server._handle_feishu_chat_message_event(body)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server._feishu_chat_app_text_send = previous_send
        server._feishu_chat_app_receipt_send = previous_receipt
        server._feishu_chat_app_message_recall = previous_recall
        server._feishu_chat_app_reaction_add = previous_reaction_add
        server._feishu_chat_app_reaction_delete = previous_reaction_delete
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert [item["op"] for item in operations] == ["reaction_add", "receipt", "dispatch", "send", "recall"]
    assert operations[1]["text"]
    assert operations[4]["message_id"] == "om_receipt"
    completed = result["record"]
    assert completed["reactionResult"]["ok"] is False
    assert completed["receiptResult"]["messageId"] == "om_receipt"
    assert completed["receiptRecallResult"]["status"] == "recalled"


def test_feishu_channel_missing_representative_agent_does_not_dispatch():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-missing-rep-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "reply": "should not happen"}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_missing_rep",
                    "chat_id": "oc_missing_rep",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": "hello",
                },
            }
        }, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is False
    assert result["status"] == "missing_representative_agent"
    assert calls == []
    assert sends and "CEO Agent" in sends[0]["text"]
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert rows[0]["event"] == "rejected"
    assert rows[0]["reason"] == "missing_representative_agent"
    assert rows[0]["voUserId"] == "user-1"


def test_feishu_channel_representative_agent_change_affects_future_messages():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-agent-switch-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "agent-a",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({"agentId": agent_id, "message": message, "conversationId": conversation_id})
        return {"ok": True, "reply": f"reply from {agent_id}", "conversationId": conversation_id}

    def fake_send(chat_id, text):
        sends.append({"chatId": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    def body(message_id, text):
        return {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": message_id,
                    "chat_id": "oc_1",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": text,
                },
            }
        }

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        first = server._handle_feishu_chat_message_event(body("om_agent_a", "hello A"), send_text=fake_send)
        server.VO_CONFIG = {
            **server.VO_CONFIG,
            "feishu": {
                **(server.VO_CONFIG.get("feishu") or {}),
                "chatApp": {
                    **((server.VO_CONFIG.get("feishu") or {}).get("chatApp") or {}),
                    "representativeAgentId": "agent-b",
                },
            },
        }
        second = server._handle_feishu_chat_message_event(body("om_agent_b", "hello B"), send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert first["ok"] is True
    assert second["ok"] is True
    assert [call["agentId"] for call in calls] == ["agent-a", "agent-b"]
    assert [send["text"] for send in sends] == [
        "reply from agent-a",
        "reply from agent-b",
    ]
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    completed = [row for row in rows if row.get("event") == "turn_completed"]
    assert [row["representativeAgentId"] for row in completed] == ["agent-a", "agent-b"]
    assert [row["sourceMessageId"] for row in completed] == ["om_agent_a", "om_agent_b"]


def test_feishu_channel_consecutive_messages_keep_order_and_conversation():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-order-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({
            "agentId": agent_id,
            "message": message,
            "conversationId": conversation_id,
            "sourceMessageId": source_meta.get("sourceMessageId"),
        })
        return {"ok": True, "reply": f"reply to {message}", "conversationId": conversation_id}

    def fake_send(chat_id, text):
        sends.append({"chatId": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    def body(message_id, text):
        return {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": message_id,
                    "chat_id": "oc_order",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": text,
                },
            }
        }

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        first = server._handle_feishu_chat_message_event(body("om_order_1", "first"), send_text=fake_send)
        second = server._handle_feishu_chat_message_event(body("om_order_2", "second"), send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert first["ok"] is True
    assert second["ok"] is True
    assert [call["sourceMessageId"] for call in calls] == ["om_order_1", "om_order_2"]
    assert [call["message"] for call in calls] == ["first", "second"]
    assert calls[0]["conversationId"] == calls[1]["conversationId"]
    assert len(sends) == 2
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert [row["event"] for row in rows] == ["user_message", "turn_completed", "user_message", "turn_completed"]
    assert [row["sourceMessageId"] for row in rows] == ["om_order_1", "om_order_1", "om_order_2", "om_order_2"]
    assert rows[0]["conversationId"] == rows[1]["conversationId"] == rows[2]["conversationId"] == rows[3]["conversationId"]


def test_feishu_channel_unavailable_representative_agent_records_failure():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-missing-agent-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "missing-agent",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    sends = []

    def fake_send(chat_id, text):
        sends.append({"chatId": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_missing_agent",
                    "chat_id": "oc_missing_agent",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": "hello missing agent",
                },
            }
        }, send_text=fake_send)
    finally:
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is False
    assert result["status"] == "agent_failed"
    assert sends and not sends[0]["text"].startswith("CEO (by")
    assert "Representative agent 'missing-agent' not found" in sends[0]["text"]
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert [row["event"] for row in rows] == ["user_message", "turn_completed"]
    completed = rows[-1]
    assert completed["representativeAgentId"] == "missing-agent"
    assert completed["agentResult"]["ok"] is False
    assert completed["agentResult"]["_status"] == 404
    assert completed["sendResult"]["ok"] is True


def test_feishu_channel_recording_is_mandatory_even_if_disabled_in_config():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-mandatory-recording-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
                "recordMessages": False,
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    sends = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        return {"ok": True, "reply": "mandatory record reply", "conversationId": conversation_id}

    def fake_send(chat_id, text):
        sends.append({"chatId": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_recording_forced",
                    "chat_id": "oc_recording_forced",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": "record this",
                },
            }
        }, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert sends
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert [row["event"] for row in rows] == ["user_message", "turn_completed"]
    assert rows[-1]["sourceMessageId"] == "om_recording_forced"
    assert rows[-1]["reply"] == "mandatory record reply"


def test_feishu_channel_metadata_is_written_to_hermes_history():
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-history-metadata-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_get_agent = server._get_hermes_agent
    previous_api_chat = server._handle_hermes_api_chat
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "hermes": {
            **(previous_config.get("hermes") or {}),
            "apiEnabled": True,
            "timeoutSec": 10,
        },
    }

    def fake_get_agent(agent_key):
        return {
            "id": agent_key,
            "name": "Hermes",
            "profile": "feishu-history-profile",
            "providerKind": "hermes",
            "statusKey": agent_key,
        }

    def fake_api_chat(agent, profile, delivery_message, original_message, conversation_id=None, timeout=None, on_event=None):
        return {"ok": True, "reply": "history reply", "sessionId": "sess-history", "exitCode": 0}

    try:
        server._get_hermes_agent = fake_get_agent
        server._handle_hermes_api_chat = fake_api_chat
        result = server._handle_hermes_chat({
            "agentId": "hermes-default",
            "message": "hello from feishu",
            "conversationId": "feishu-dm:history",
            "fromType": "human",
            "fromDisplayName": "Feishu User",
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceLabel": "Feishu DM",
            "channel": "feishu",
            "sourceMessageId": "om_history",
            "feishuChatId": "oc_history",
            "representativeAgentId": "hermes-default",
        })
        history = server._load_hermes_history("feishu-history-profile", "feishu-dm:history")
    finally:
        server._get_hermes_agent = previous_get_agent
        server._handle_hermes_api_chat = previous_api_chat
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    user_message = next(item for item in history if item.get("role") == "user")
    assert result["ok"] is True
    assert user_message["sourceApp"] == "feishu"
    assert user_message["sourceSurface"] == "feishu-dm"
    assert user_message["sourceMessageId"] == "om_history"
    assert user_message["feishuChatId"] == "oc_history"
    assert user_message["representativeAgentId"] == "hermes-default"
    assert user_message["channel"] == "feishu"


def test_feishu_chat_inbound_test_route_dispatches_and_records():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-inbound-route-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    previous_send = server._feishu_chat_app_text_send
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_route": "user-route"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({
            "agentId": agent_id,
            "message": message,
            "conversationId": conversation_id,
            "sourceMeta": source_meta,
        })
        return {"ok": True, "reply": "route reply", "conversationId": conversation_id}

    def fake_send(chat_id, text, urlopen=None):
        sends.append({"chatId": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    body = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_route"}},
            "message": {
                "message_id": "om_route",
                "chat_id": "oc_route",
                "chat_type": "p2p",
                "message_type": "text",
                "text": "hello route",
            },
        }
    }
    try:
        server._dispatch_representative_agent_message = fake_dispatch
        server._feishu_chat_app_text_send = fake_send
        status, result = call_office_handler(server, "POST", "/api/feishu-chat/inbound-test", body)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server._feishu_chat_app_text_send = previous_send
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert status == 200
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["reply"] == "route reply"
    assert calls and calls[0]["agentId"] == "hermes-default"
    assert calls[0]["sourceMeta"]["sourceMessageId"] == "om_route"
    assert sends == [{"chatId": "oc_route", "text": "route reply"}]
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert [row["event"] for row in rows] == ["user_message", "turn_completed"]
    assert rows[-1]["sourceMessageId"] == "om_route"
    assert rows[-1]["voUserId"] == "user-route"
    assert rows[-1]["representativeAgentId"] == "hermes-default"


def test_feishu_chat_worker_route_requires_token_and_dispatches():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-worker-route-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    previous_send = server._feishu_chat_app_text_send
    previous_token = server._FEISHU_CHAT_WORKER_TOKEN
    server.STATUS_DIR = status_dir
    server._FEISHU_CHAT_WORKER_TOKEN = "worker-token"
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_worker": "user-worker"},
        },
    }
    calls = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({"agentId": agent_id, "message": message, "sourceMeta": source_meta})
        return {"ok": True, "reply": "worker reply", "conversationId": conversation_id}

    def fake_send(chat_id, text, urlopen=None):
        return {"ok": True, "status": "sent", "channel": "fake"}

    body = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_worker"}},
            "message": {
                "message_id": "om_worker",
                "chat_id": "oc_worker",
                "chat_type": "p2p",
                "message_type": "text",
                "text": "hello worker",
            },
        }
    }
    try:
        server._dispatch_representative_agent_message = fake_dispatch
        server._feishu_chat_app_text_send = fake_send
        denied_status, denied = call_office_handler(server, "POST", "/api/feishu-chat/inbound-worker", body)
        ok_status, ok = call_office_handler(
            server,
            "POST",
            "/api/feishu-chat/inbound-worker",
            body,
            headers={"X-VO-Feishu-Chat-Worker-Token": "worker-token"},
        )
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server._feishu_chat_app_text_send = previous_send
        server._FEISHU_CHAT_WORKER_TOKEN = previous_token
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert denied_status == 403
    assert denied["ok"] is False
    assert ok_status == 200
    assert ok["ok"] is True
    assert len(calls) == 1
    assert calls[0]["agentId"] == "hermes-default"
    assert calls[0]["message"] == "hello worker"
    assert calls[0]["sourceMeta"]["sourceMessageId"] == "om_worker"


def test_feishu_chat_self_test_route_dispatches_without_real_feishu_send():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-self-test-route-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    previous_start = server._start_feishu_chat_long_connection
    previous_find_agent = server._find_agent_record
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {},
        },
    }
    calls = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({
            "agentId": agent_id,
            "message": message,
            "conversationId": conversation_id,
            "sourceMeta": source_meta,
        })
        return {"ok": True, "reply": "self-test reply", "conversationId": conversation_id}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        server._start_feishu_chat_long_connection = lambda: {"enabled": True, "running": True, "status": "running"}
        server._find_agent_record = lambda agent_id: {"id": agent_id, "name": "Hermes", "providerKind": "hermes"} if agent_id == "hermes-default" else None
        status, result = call_office_handler(server, "POST", "/api/feishu-chat/self-test", {"text": "ping"})
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server._start_feishu_chat_long_connection = previous_start
        server._find_agent_record = previous_find_agent
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert status == 200
    assert result["ok"] is True
    assert result["selfTest"] is True
    assert result["status"] == "completed"
    assert calls and calls[0]["agentId"] == "hermes-default"
    assert calls[0]["message"] == "ping"
    assert result["sent"][0]["channel"] == "fake"
    assert result["sent"][0]["status"] == "self_test_skipped_real_feishu_send"
    assert "self-test reply" in result["sent"][0]["text"]


def test_feishu_chat_bindings_config_is_persisted_and_lookupable():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-bindings-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_config = server.VO_CONFIG
    try:
        server.VO_CONFIG = {
            **previous_config,
            "feishu": {
                **(previous_config.get("feishu") or {}),
                "bindings": {},
            },
        }
        result = server._save_feishu_chat_bindings_config({
            "bindings": {
                "open_id:ou_bound": "user-1",
                "union_id:on_bound": {"voUserId": "user-2"},
                "empty": "",
            }
        })
        server.VO_CONFIG = {
            **server.VO_CONFIG,
            "feishu": {
                **(server.VO_CONFIG.get("feishu") or {}),
                "bindings": result["bindings"],
            },
        }
        found_open = server._find_feishu_bound_user({"openId": "ou_bound"}, "")
        found_union = server._find_feishu_bound_user({"unionId": "on_bound"}, "")
    finally:
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert result["count"] == 2
    assert result["bindings"]["open_id:ou_bound"] == "user-1"
    assert result["bindings"]["union_id:on_bound"] == "user-2"
    assert found_open == "user-1"
    assert found_union == "user-2"


def test_feishu_chat_bindings_http_routes_persist_and_read():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-bindings-http-")
    previous_status_dir_env = os.environ.get("VO_STATUS_DIR")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_config = server.VO_CONFIG
    previous_status_dir = server.STATUS_DIR
    try:
        server.STATUS_DIR = status_dir
        server.VO_CONFIG = {
            **previous_config,
            "feishu": {
                **(previous_config.get("feishu") or {}),
                "bindings": {},
            },
        }
        post_status, posted = call_office_handler(server, "POST", "/api/feishu-chat/bindings", {"bindings": {"open_id:ou_http": "user-http"}})
        get_status, fetched = call_office_handler(server, "GET", "/api/feishu-chat/bindings")
    finally:
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config
        if previous_status_dir_env is None:
            os.environ.pop("VO_STATUS_DIR", None)
        else:
            os.environ["VO_STATUS_DIR"] = previous_status_dir_env

    assert post_status == 200
    assert posted["ok"] is True
    assert posted["bindings"] == {"open_id:ou_http": "user-http"}
    assert get_status == 200
    assert fetched["ok"] is True
    assert fetched["bindings"] == {"open_id:ou_http": "user-http"}
    with open(os.path.join(status_dir, "vo-config.json"), "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["feishu"]["bindings"] == {"open_id:ou_http": "user-http"}


def test_feishu_chat_records_route_reads_recent_channel_records():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-records-http-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    server.STATUS_DIR = status_dir
    try:
        server._record_feishu_channel_event({"event": "user_message", "sourceMessageId": "om_old"})
        server._record_feishu_channel_event({"event": "user_message", "sourceMessageId": "om_keep_1"})
        server._record_feishu_channel_event({"event": "turn_completed", "sourceMessageId": "om_keep_2"})
        status, result = call_office_handler(server, "GET", "/api/feishu-chat/records?limit=2")
    finally:
        server.STATUS_DIR = previous_status_dir

    assert status == 200
    assert result["ok"] is True
    assert result["count"] == 2
    assert [row["sourceMessageId"] for row in result["records"]] == ["om_keep_1", "om_keep_2"]
    assert [row["event"] for row in result["records"]] == ["user_message", "turn_completed"]


def test_feishu_channel_missing_chat_credentials_rejects_before_dispatch():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-missing-creds-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "reply": "should not happen"}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_missing_creds",
                    "chat_id": "oc_missing_creds",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": "hello",
                },
            }
        }, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is False
    assert result["status"] == "missing_chat_app_credentials"
    assert calls == []
    assert sends == []
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert rows[0]["reason"] == "missing_chat_app_credentials"


def test_feishu_channel_empty_text_is_ignored_before_dispatch():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-empty-text-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "reply": "should not happen"}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_empty_text",
                    "chat_id": "oc_empty_text",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": "   ",
                },
            }
        }, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert result["status"] == "ignored_empty_text"
    assert calls == []
    assert sends == []
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert rows[0]["reason"] == "empty_text"


def test_feishu_channel_unsupported_chat_or_message_type_is_ignored():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-unsupported-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "reply": "should not happen"}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        group_result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_group",
                    "chat_id": "oc_group",
                    "chat_type": "group",
                    "message_type": "text",
                    "text": "hello group",
                },
            }
        }, send_text=fake_send)
        file_result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_file",
                    "chat_id": "oc_1",
                    "chat_type": "p2p",
                    "message_type": "file",
                    "text": "",
                },
            }
        }, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert group_result["ok"] is True
    assert group_result["status"] == "ignored_unsupported_chat_type"
    assert file_result["ok"] is True
    assert file_result["status"] == "ignored_unsupported_message_type"
    assert calls == []
    assert sends == []
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert [row["reason"] for row in rows] == ["unsupported_chat_type", "unsupported_message_type"]


def test_feishu_channel_image_message_downloads_records_and_dispatches():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-image-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {"open_id:ou_bound": "user-1"},
        },
    }
    calls = []
    sends = []
    downloads = []

    def fake_dispatch(agent_id, message, conversation_id, source_meta):
        calls.append({
            "agent_id": agent_id,
            "message": message,
            "conversation_id": conversation_id,
            "source_meta": source_meta,
        })
        return {"ok": True, "reply": "收到图片了"}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    def fake_download(message_id, image_key):
        downloads.append({"message_id": message_id, "image_key": image_key})
        path = os.path.join(status_dir, "feishu-chat-attachments", "image.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return {
            "ok": True,
            "status": "downloaded",
            "resourceType": "image",
            "messageId": message_id,
            "fileKey": image_key,
            "name": "image.png",
            "path": path,
            "url": "/chat-media?path=" + path,
            "mimeType": "image/png",
            "contentType": "image/png",
            "size": 4,
        }

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bound"}},
                "message": {
                    "message_id": "om_image",
                    "chat_id": "oc_1",
                    "chat_type": "p2p",
                    "message_type": "image",
                    "content": {"image_key": "img_123"},
                },
            }
        }, send_text=fake_send, download_image=fake_download)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert downloads == [{"message_id": "om_image", "image_key": "img_123"}]
    assert len(calls) == 1
    assert calls[0]["agent_id"] == "hermes-default"
    assert "图片附件已同步到 VO" in calls[0]["message"]
    assert calls[0]["source_meta"]["attachments"][0]["fileKey"] == "img_123"
    assert sends == [{"chat_id": "oc_1", "text": "收到图片了"}]
    with open(os.path.join(status_dir, "feishu-channel-records.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    user_row = next(row for row in rows if row["event"] == "user_message")
    done_row = next(row for row in rows if row["event"] == "turn_completed")
    assert user_row["messageType"] == "image"
    assert user_row["attachments"][0]["mimeType"] == "image/png"
    assert done_row["attachments"][0]["fileKey"] == "img_123"
    with open(os.path.join(status_dir, "agent-platform-communications.jsonl"), "r", encoding="utf-8") as f:
        comm_rows = [json.loads(line) for line in f if line.strip()]
    request = next(row for row in comm_rows if row["direction"] == "request")
    assert request["attachments"][0]["name"] == "image.png"
    assert request["metadata"]["attachments"][0]["fileKey"] == "img_123"


def test_feishu_channel_unbound_user_dispatches_with_feishu_source_identity():
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    status_dir = tempfile.mkdtemp(prefix="vo-feishu-channel-unbound-")
    os.environ["VO_STATUS_DIR"] = status_dir
    import server

    previous_status_dir = server.STATUS_DIR
    previous_config = server.VO_CONFIG
    previous_dispatch = server._dispatch_representative_agent_message
    server.STATUS_DIR = status_dir
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_chat",
                "appSecret": "chat-secret",
                "representativeAgentId": "hermes-default",
            },
            "bindings": {},
        },
    }
    calls = []
    sends = []

    def fake_dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "reply": "hello from agent"}

    def fake_send(chat_id, text):
        sends.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "status": "sent", "channel": "fake"}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        result = server._handle_feishu_chat_message_event({
            "event": {
                "sender": {"sender_id": {"open_id": "ou_unbound"}},
                "message": {
                    "message_id": "om_unbound",
                    "chat_id": "oc_unbound",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "text": "hello",
                },
            }
        }, send_text=fake_send)
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.STATUS_DIR = previous_status_dir
        server.VO_CONFIG = previous_config

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert len(calls) == 1
    assert calls[0][0][1] == "hello"
    assert result["record"]["voUserId"] == "feishu:open_id:ou_unbound"
    assert result["record"]["conversationId"].startswith("feishu-dm:")
    assert sends and sends[0]["chat_id"] == "oc_unbound"
    assert "hello from agent" in sends[0]["text"]


def test_feishu_long_connection_response_uses_plain_toast_dict():
    from lark_oapi.core.json import JSON
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse

    response = P2CardActionTriggerResponse({"toast": {"type": "success", "content": "操作已收到"}})
    serialized = JSON.marshal(response)
    assert '"toast"' in serialized
    assert "操作已收到" in serialized


if __name__ == "__main__":
    test_four_notification_types_render_interactive_cards()
    test_application_form_actions_and_states_are_validated()
    test_non_application_notifications_only_allow_jump_actions()
    test_error_variants_do_not_leak_secrets_to_user_card()
    test_sender_uses_fake_http_and_records_success_without_leaking_webhook()
    test_sender_uses_app_credentials_and_records_success_without_leaking_secret()
    test_text_sender_uses_chat_app_credentials_without_leaking_secret()
    test_markdown_sender_preserves_markdown_without_prefix()
    test_sender_surfaces_feishu_app_http_error_body()
    test_sender_records_non_success_network_failure_and_missing_webhook()
    test_invalid_intent_records_structured_error()
    test_setup_config_masks_feishu_webhook_and_preserves_blank_secret()
    test_feishu_config_save_returns_app_mask_and_clears_webhook()
    test_manual_test_intents_cover_all_notification_types()
    test_feishu_card_action_challenge_and_recording()
    test_feishu_long_connection_event_conversion()
    test_feishu_long_connection_message_event_conversion()
    test_feishu_long_connection_message_handler_is_invoked()
    test_feishu_chat_config_is_separate_from_notification_app()
    test_feishu_chat_config_rejects_unknown_representative_agent()
    test_feishu_channel_adapter_records_and_dedupes()
    test_feishu_channel_adds_and_deletes_message_reaction_receipt()
    test_feishu_channel_falls_back_to_temporary_receipt_when_reaction_fails()
    test_feishu_channel_missing_representative_agent_does_not_dispatch()
    test_feishu_channel_representative_agent_change_affects_future_messages()
    test_feishu_channel_consecutive_messages_keep_order_and_conversation()
    test_feishu_channel_unavailable_representative_agent_records_failure()
    test_feishu_channel_recording_is_mandatory_even_if_disabled_in_config()
    test_feishu_channel_metadata_is_written_to_hermes_history()
    test_feishu_chat_inbound_test_route_dispatches_and_records()
    test_feishu_chat_self_test_route_dispatches_without_real_feishu_send()
    test_feishu_chat_bindings_config_is_persisted_and_lookupable()
    test_feishu_chat_bindings_http_routes_persist_and_read()
    test_feishu_chat_records_route_reads_recent_channel_records()
    test_feishu_channel_missing_chat_credentials_rejects_before_dispatch()
    test_feishu_channel_empty_text_is_ignored_before_dispatch()
    test_feishu_channel_unsupported_chat_or_message_type_is_ignored()
    test_feishu_channel_unbound_user_dispatches_with_feishu_source_identity()
    test_feishu_long_connection_response_uses_plain_toast_dict()
    print("test_feishu_notifications.py passed")
