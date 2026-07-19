#!/usr/bin/env python3
"""OfficeHandler contracts for management and authenticated Agent HR routes."""

import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-hr-http-")

import server
from services.hr_config import HRConfig
from services.hr_information_completion import HRInformationCompletionReceipt
from services.hr_runtime import HRCommandRouter, build_hr_application_runtime


NOW = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
SECRET_1 = "agent-one-human-resources-http-grant-000001"
SECRET_2 = "agent-two-human-resources-http-grant-000002"


class Lifecycle:
    def __init__(self):
        self.paused = False

    def public_state(self, *, ensure=True):
        return {"role": "hr", "status": "paused" if self.paused else "ready"}

    def pause(self):
        self.paused = True
        return self.public_state(ensure=False)

    def resume(self):
        self.paused = False
        return self.public_state(ensure=False)


class Connection:
    def settimeout(self, timeout):
        self.timeout = timeout


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    lifecycle = Lifecycle()
    workspace = tmp_path / "workspaces" / "agent-3"
    workspace.mkdir(parents=True)
    result = build_hr_application_runtime(
        status_dir=tmp_path / "status",
        lifecycle=lifecycle,
        config=HRConfig.from_env(
            {
                "VO_HR_ENABLED": "1",
                "VO_HR_SCHEDULER_ENABLED": "0",
                "VO_HR_TIMEZONE": "UTC",
            }
        ),
        commands=HRCommandRouter(),
        roster_provider=lambda force: [
            {
                "id": "agent-3", "name": "Agent Three", "providerKind": "openclaw",
                "workspace": str(workspace),
            }
        ],
        workspace_base=tmp_path / "workspaces",
    )
    for ai_id, secret in (("agent-1", SECRET_1), ("agent-2", SECRET_2)):
        result.repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id.title(),
            agent_kind="project",
            provider_kind="openclaw",
            status="active",
            availability="available",
            source="test",
        )
        result.repository.save_introduction(
            ai_id=ai_id,
            state="published",
            raw_response=f"private {ai_id} response",
            introduction=f"Public {ai_id} introduction",
            source="hr-summary",
            actor_id="hr",
            expected_version=0,
        )
        result.repository.rotate_access_grant(
            ai_id=ai_id,
            key_id=f"key-{ai_id}",
            secret_digest=hashlib.sha256(secret.encode()).hexdigest(),
            issued_at=(NOW - timedelta(days=1)).isoformat(),
            expires_at=(NOW + timedelta(days=30)).isoformat(),
        )
    result.routes._authenticator._clock = lambda: NOW
    result.routes._agents._clock = lambda: NOW
    monkeypatch.setattr(server, "_hr_application_runtime", result)
    return result, lifecycle


def handler(
    path,
    body=None,
    *,
    headers=None,
    management=False,
    remote_host="127.0.0.1",
):
    payload = json.dumps(body).encode() if body is not None else b""
    instance = object.__new__(server.OfficeHandler)
    instance.path = path
    instance.headers = {"Content-Length": str(len(payload)), **(headers or {})}
    if management:
        instance.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
    instance.client_address = (remote_host, 12345)
    instance.rfile = io.BytesIO(payload)
    instance.wfile = io.BytesIO()
    instance.connection = Connection()
    instance.responses = []
    instance.response_headers = []
    instance.send_response = lambda status, *args, **kwargs: instance.responses.append(status)
    instance.send_header = lambda name, value: instance.response_headers.append((name, value))
    instance.end_headers = lambda: None
    return instance


def call(instance, method):
    getattr(instance, f"do_{method}")()
    raw = instance.wfile.getvalue()
    return instance.responses[-1], json.loads(raw) if raw else {}


def agent_headers(ai_id="agent-1", secret=SECRET_1):
    return {
        "X-VO-Agent-Action": "human-resources",
        "X-VO-Agent-Id": ai_id,
        "Authorization": f"Bearer {secret}",
    }


def test_management_gets_reuse_token_challenge_and_return_safe_contract(runtime):
    denied = handler("/api/human-resources/overview")
    status, payload = call(denied, "GET")
    assert status == 403
    assert payload["code"] == "management_token_required"

    overview = handler("/api/human-resources/overview", management=True)
    status, payload = call(overview, "GET")
    assert status == 200
    assert payload["ok"] is True
    assert payload["hr"]["status"] == "ready"
    assert "secret_digest" not in json.dumps(payload)


def test_management_routes_cover_detail_log_health_export_and_commands(runtime):
    _runtime, lifecycle = runtime
    routes = (
        "/api/human-resources/agents/agent-1",
        "/api/human-resources/access-log?limit=10",
        "/api/human-resources/health",
        "/api/human-resources/export?table=agents&limit=10",
    )
    for path in routes:
        status, payload = call(handler(path, management=True), "GET")
        assert status == 200, (path, payload)
        assert payload["ok"] is True

    status, _payload = call(
        handler("/api/human-resources/hr/pause", {}, management=True), "POST"
    )
    assert status == 200
    assert lifecycle.paused is True
    status, payload = call(
        handler("/api/human-resources/cycles/run", {}, management=True), "POST"
    )
    assert status == 503
    assert payload["command"]["accepted"] is False

    status, payload = call(
        handler("/api/human-resources/directory/sync", {"unexpected": True}, management=True), "POST"
    )
    assert status == 400
    assert payload["code"] == "hr_api_validation_failed"

    class Completion:
        def complete(self):
            return HRInformationCompletionReceipt(
                "information-http-1",
                "complete_information",
                True,
            )

    _runtime.routes._management._information_completion = Completion()
    status, payload = call(
        handler(
            "/api/human-resources/directory/complete-information",
            {},
            management=True,
        ),
        "POST",
    )
    assert status == 409
    assert payload["code"] == "hr_information_completion_hr_unavailable"
    lifecycle.paused = False
    status, payload = call(
        handler(
            "/api/human-resources/directory/complete-information",
            {},
            management=True,
        ),
        "POST",
    )
    assert status == 202
    assert payload["command"]["command"] == "complete_information"

    class DailySync:
        def run(self, ai_ids):
            assert ai_ids == ("agent-1",)
            from services.hr_manual_daily_sync import HRManualDailySyncReceipt
            return HRManualDailySyncReceipt("daily-http-1", "manual_daily_sync", True)

    _runtime.routes._management._manual_daily_sync = DailySync()
    status, payload = call(
        handler(
            "/api/human-resources/daily-sync",
            {"agentIds": ["agent-1"]},
            management=True,
        ),
        "POST",
    )
    assert status == 202
    assert payload["command"]["command"] == "manual_daily_sync"

    status, payload = call(
        handler("/api/human-resources/directory/sync", {}, management=True), "POST"
    )
    assert status == 200
    assert payload["sync"]["discovered"] == 1
    assert payload["sync"]["created"] == ["agent-3"]

    status, payload = call(
        handler(
            "/api/human-resources/directory/complete-information",
            {"unexpected": True},
            management=True,
        ),
        "POST",
    )
    assert status == 400
    assert payload["code"] == "hr_api_validation_failed"


def test_agent_directory_and_public_detail_require_bound_grant(runtime):
    repository, _lifecycle = runtime
    status, payload = call(
        handler("/api/agent-human-resources/directory", headers=agent_headers()),
        "GET",
    )
    assert status == 200
    assert len(payload["items"]) == 2
    assert repository.repository.list_access_log().items == ()

    status, payload = call(
        handler(
            "/api/agent-human-resources/agents/agent-2",
            headers=agent_headers(),
        ),
        "GET",
    )
    assert status == 200
    assert payload["agent"]["scope"] == "public"
    assert "private agent-2 response" not in json.dumps(payload)
    logs = repository.repository.list_access_log().items
    assert len(logs) == 1
    assert (logs[0].viewer_ai_id, logs[0].target_ai_id) == ("agent-1", "agent-2")


@pytest.mark.parametrize(
    ("headers", "remote_host", "code"),
    [
        ({}, "127.0.0.1", "hr_agent_action_required"),
        (
            {**agent_headers(), "Origin": "https://evil.example"},
            "127.0.0.1",
            "hr_agent_browser_origin_forbidden",
        ),
        (agent_headers(), "10.0.0.8", "hr_agent_loopback_required"),
        (
            agent_headers(ai_id="agent-1", secret=SECRET_2),
            "127.0.0.1",
            "hr_agent_grant_mismatch",
        ),
    ],
)
def test_agent_http_security_denies_missing_origin_remote_and_spoofed_calls(
    runtime, headers, remote_host, code
):
    status, payload = call(
        handler(
            "/api/agent-human-resources/directory",
            headers=headers,
            remote_host=remote_host,
        ),
        "GET",
    )
    assert status == 403
    assert payload == {"ok": False, "code": code}


def test_self_access_log_cannot_select_another_target(runtime):
    result, _lifecycle = runtime
    result.repository.record_successful_access(
        access_id="view-1",
        viewer_ai_id="agent-2",
        target_ai_id="agent-1",
        viewed_at=NOW.isoformat(),
        scope="public_work_summary",
        request_source="test",
        occurrence_key="view-1",
    )
    status, payload = call(
        handler(
            "/api/agent-human-resources/access-log/self?targetAiId=agent-2",
            headers=agent_headers(),
        ),
        "GET",
    )
    assert status == 200
    assert len(payload["items"]) == 1
    assert payload["items"][0]["targetAiId"] == "agent-1"


def test_hr_options_use_minimal_headers_and_never_enable_agent_cors(runtime):
    management = handler("/api/human-resources/overview")
    status, _payload = call(management, "OPTIONS")
    assert status == 204
    headers = dict(management.response_headers)
    assert headers["Access-Control-Allow-Headers"] == "Content-Type, X-VO-Management-Token"
    assert "Access-Control-Allow-Origin" not in headers
    assert "Authorization" not in headers["Access-Control-Allow-Headers"]

    agent = handler("/api/agent-human-resources/directory", headers={"Origin": "null"})
    status, payload = call(agent, "OPTIONS")
    assert status == 403
    assert payload["code"] == "hr_agent_browser_origin_forbidden"
    assert "Access-Control-Allow-Origin" not in dict(agent.response_headers)


def test_hr_http_errors_are_normalized_without_credentials(runtime):
    status, payload = call(
        handler(
            "/api/human-resources/export?table=access_grants&limit=not-a-number",
            management=True,
        ),
        "GET",
    )
    assert status == 400
    assert payload == {"ok": False, "code": "hr_http_validation_failed"}
    encoded = json.dumps(payload)
    assert SECRET_1 not in encoded
    assert server._MANAGEMENT_TOKEN not in encoded

    malformed = handler(
        "/api/human-resources/hr/pause",
        management=True,
    )
    malformed.headers["Content-Length"] = "1"
    malformed.rfile = io.BytesIO(b"{")
    status, payload = call(malformed, "POST")
    assert status == 400
    assert payload == {"ok": False, "code": "hr_api_validation_failed"}

    oversized = handler(
        "/api/human-resources/hr/pause",
        management=True,
    )
    oversized.headers["Content-Length"] = str(server.OfficeHandler._MANAGEMENT_BODY_LIMIT + 1)
    status, payload = call(oversized, "POST")
    assert status == 413
    assert payload == {"ok": False, "code": "hr_api_validation_failed"}
