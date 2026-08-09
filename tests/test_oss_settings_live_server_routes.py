import io
import json
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path

import pytest


os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-oss-settings-routes-"))

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402
from server_routes import oss_settings  # noqa: E402
from services.oss_runtime import OssRuntime  # noqa: E402
from services.oss_settings import OssSettingsStore, OssSettingsView  # noqa: E402
from services.oss_storage import OssStorageError  # noqa: E402


SECRET = "route-secret-sentinel"


def _handler(path, body=None, *, management_token=None, raw_body=None):
    handler = object.__new__(server.OfficeHandler)
    raw = (
        raw_body
        if raw_body is not None
        else json.dumps(body).encode("utf-8") if body is not None else b""
    )
    handler.path = path
    handler.headers = {"Content-Length": str(len(raw))}
    if management_token:
        handler.headers["X-VO-Management-Token"] = management_token
    handler.rfile = io.BytesIO(raw)
    handler.wfile = io.BytesIO()
    handler.status = None
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: setattr(handler, "status", status)
    handler.send_header = lambda key, value: handler.response_headers.append((key, value))
    handler.end_headers = lambda: None
    return handler


def _payload(handler):
    return json.loads(handler.wfile.getvalue().decode("utf-8") or "{}")


class FakeRuntime:
    def __init__(self):
        self.reads = 0
        self.activations = []
        self.failure = None

    def settings_view(self):
        self.reads += 1
        return OssSettingsView(
            endpoint="https://oss-cn-hangzhou.aliyuncs.com",
            bucket="vo-materials",
            access_key_id="LTAI-safe",
            configured=True,
            secret_configured=True,
        )

    def test_and_activate(self, body):
        self.activations.append(body)
        if self.failure:
            raise self.failure
        return self.settings_view()


def _use_runtime(monkeypatch, runtime):
    monkeypatch.setattr(oss_settings, "_runtime_provider", lambda: runtime)


def test_get_requires_management_token_before_reading_runtime(monkeypatch):
    runtime = FakeRuntime()
    _use_runtime(monkeypatch, runtime)
    denied = _handler("/api/settings/oss")

    server.OfficeHandler.do_GET(denied)

    assert denied.status == 403
    assert _payload(denied)["code"] == "management_token_required"
    assert runtime.reads == 0


def test_post_requires_management_token_before_parsing_body_or_calling_runtime(monkeypatch):
    runtime = FakeRuntime()
    _use_runtime(monkeypatch, runtime)
    denied = _handler(
        "/api/settings/oss/test-and-activate",
        raw_body=b'{"accessKeySecret":"' + SECRET.encode() + b'"',
    )

    server.OfficeHandler.do_POST(denied)

    assert denied.status == 403
    assert _payload(denied)["code"] == "management_token_required"
    assert runtime.activations == []
    assert denied.rfile.tell() == 0


def test_authorized_get_returns_only_safe_settings_projection(monkeypatch):
    runtime = FakeRuntime()
    _use_runtime(monkeypatch, runtime)
    handler = _handler("/api/settings/oss", management_token=server._MANAGEMENT_TOKEN)

    server.OfficeHandler.do_GET(handler)

    payload = _payload(handler)
    assert handler.status == 200
    assert payload["ok"] is True
    assert payload["settings"]["secretConfigured"] is True
    assert "accessKeySecret" not in json.dumps(payload)
    assert "region" not in payload["settings"]


def test_authorized_get_without_configuration_returns_empty_success_without_provider(monkeypatch, tmp_path):
    provider_calls = []

    def unexpected_provider(config):
        provider_calls.append(config)
        raise AssertionError("empty settings GET must not construct a provider")

    runtime = OssRuntime(OssSettingsStore(tmp_path), unexpected_provider)
    _use_runtime(monkeypatch, runtime)
    handler = _handler("/api/settings/oss", management_token=server._MANAGEMENT_TOKEN)

    server.OfficeHandler.do_GET(handler)

    payload = _payload(handler)
    assert handler.status == 200
    assert payload == {
        "ok": True,
        "settings": {
            "endpoint": "",
            "bucket": "",
            "accessKeyId": "",
            "configured": False,
            "secretConfigured": False,
        },
    }
    assert provider_calls == []


def test_unresolved_endpoint_returns_specific_safe_code_before_provider(monkeypatch, tmp_path):
    provider_calls = []
    runtime = OssRuntime(
        OssSettingsStore(tmp_path),
        lambda config: provider_calls.append(config),
    )
    _use_runtime(monkeypatch, runtime)
    body = {
        "endpoint": "https://oss-accelerate.aliyuncs.com",
        "bucket": "vo-materials",
        "accessKeyId": "LTAI-safe",
        "accessKeySecret": SECRET,
    }
    handler = _handler(
        "/api/settings/oss/test-and-activate",
        body,
        management_token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(handler)

    payload = _payload(handler)
    assert handler.status == 400
    assert payload["code"] == "oss_region_unresolved"
    assert provider_calls == []


@pytest.mark.parametrize(
    ("body_override", "expected_code", "expected_error"),
    [
        (
            {"endpoint": "ftp://oss-cn-hangzhou.aliyuncs.com"},
            "oss_endpoint_invalid",
            "OSS Endpoint must be a valid HTTP(S) address",
        ),
        (
            {"bucket": "INVALID_BUCKET"},
            "oss_bucket_invalid",
            "OSS Bucket name is invalid",
        ),
        (
            {"accessKeyId": ""},
            "oss_access_key_id_invalid",
            "OSS AccessKey ID is missing or invalid",
        ),
        (
            {"accessKeySecret": ""},
            "oss_access_key_secret_invalid",
            "OSS AccessKey Secret is missing or invalid",
        ),
    ],
)
def test_invalid_setting_returns_specific_safe_error(
    monkeypatch, tmp_path, body_override, expected_code, expected_error
):
    provider_calls = []
    runtime = OssRuntime(
        OssSettingsStore(tmp_path),
        lambda config: provider_calls.append(config),
    )
    _use_runtime(monkeypatch, runtime)
    body = {
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "bucket": "vo-materials",
        "accessKeyId": "LTAI-safe",
        "accessKeySecret": SECRET,
    }
    body.update(body_override)
    handler = _handler(
        "/api/settings/oss/test-and-activate",
        body,
        management_token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(handler)

    payload = _payload(handler)
    assert handler.status == 400
    assert payload["code"] == expected_code
    assert payload["error"] == expected_error
    assert SECRET not in json.dumps(payload)
    assert provider_calls == []


def test_authorized_test_and_activate_passes_bounded_json_and_returns_safe_view(monkeypatch):
    runtime = FakeRuntime()
    _use_runtime(monkeypatch, runtime)
    body = {
        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "bucket": "vo-materials",
        "accessKeyId": "LTAI-safe",
        "accessKeySecret": SECRET,
    }
    handler = _handler(
        "/api/settings/oss/test-and-activate",
        body,
        management_token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(handler)

    payload = _payload(handler)
    assert handler.status == 200
    assert runtime.activations == [body]
    assert SECRET not in json.dumps(payload)
    assert payload["settings"]["bucket"] == "vo-materials"


def test_provider_failure_maps_to_safe_status_and_message(monkeypatch, caplog):
    runtime = FakeRuntime()
    runtime.failure = OssStorageError(
        "unsafe " + SECRET,
        code="oss_authentication_failed",
        request_id="request-safe",
    )
    _use_runtime(monkeypatch, runtime)
    handler = _handler(
        "/api/settings/oss/test-and-activate",
        {"accessKeySecret": SECRET},
        management_token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(handler)

    payload = _payload(handler)
    assert handler.status == 400
    assert payload["code"] == "oss_authentication_failed"
    assert payload["requestId"] == "request-safe"
    assert SECRET not in json.dumps(payload)
    assert SECRET not in caplog.text


def test_unrecognized_provider_code_is_not_reflected(monkeypatch):
    runtime = FakeRuntime()
    runtime.failure = OssStorageError(
        "unsafe",
        code="credential-" + SECRET,
    )
    _use_runtime(monkeypatch, runtime)
    handler = _handler(
        "/api/settings/oss/test-and-activate",
        {"accessKeySecret": SECRET},
        management_token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(handler)

    payload = _payload(handler)
    assert handler.status == 502
    assert payload["code"] == "oss_provider_operation_failed"
    assert SECRET not in json.dumps(payload)


def test_unknown_oss_like_path_is_not_swallowed_by_route(monkeypatch):
    runtime = FakeRuntime()
    _use_runtime(monkeypatch, runtime)
    handler = _handler(
        "/api/settings/oss/unknown", management_token=server._MANAGEMENT_TOKEN
    )

    assert oss_settings.handle_get(handler, urllib.parse.urlparse(handler.path)) is False
    assert runtime.reads == 0
