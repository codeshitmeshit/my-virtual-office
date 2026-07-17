import os
import sys
import tempfile

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-codex-feishu-integration-import-"))

import server  # noqa: E402
from services.codex_feishu_approvals import CodexFeishuApprovalCoordinator, CodexFeishuApprovalRouteStore  # noqa: E402


def origin():
    return {
        "sourceApp": "feishu",
        "sourceSurface": "feishu-dm",
        "sourceMessageId": "om_source",
        "feishuChatId": "oc_source",
        "sourceActor": {"openId": "ou_origin", "unionId": "on_origin", "name": "Origin User"},
        "agentId": "codex-local",
        "conversationId": "feishu-dm:user:chat",
    }


def approval(case):
    return {
        "id": f"approval-{case}",
        "approval_id": f"approval-{case}",
        "kind": "command",
        "command": "printf safe",
        "profile": "local",
        "threadId": f"thread-{case}",
        "turnId": f"turn-{case}",
    }


@pytest.mark.parametrize(
    ("case", "notification_config", "send_results", "expected_application", "expected_calls"),
    (
        ("primary", {"appId": "notification", "appSecret": "secret"}, [{"ok": True, "status": "sent", "messageId": "om_primary"}], "notification", 1),
        ("chat-only", {}, [{"ok": True, "status": "sent", "messageId": "om_chat"}], "chat", 1),
        ("fallback", {"appId": "notification", "appSecret": "secret"}, [{"ok": False, "status": "network_error"}, {"ok": True, "status": "sent", "messageId": "om_fallback"}], "chat", 2),
    ),
)
def test_live_routing_matrix_uses_common_sender(tmp_path, case, notification_config, send_results, expected_application, expected_calls):
    calls = []

    def sender(intent, **kwargs):
        calls.append((intent, kwargs))
        return send_results[len(calls) - 1]

    coordinator = CodexFeishuApprovalCoordinator(
        CodexFeishuApprovalRouteStore(str(tmp_path / f"{case}.json")),
        send_notification=sender,
        status_dir=str(tmp_path),
    )
    record, _ = coordinator.register(approval(case), origin())
    result = coordinator.deliver(
        record["routeId"],
        notification_config=notification_config,
        chat_config={"appId": "chat", "appSecret": "secret"},
    )
    assert result["ok"] is True
    assert result["application"] == expected_application
    assert len(calls) == expected_calls
    assert all(call[0]["id"] == record["routeId"] for call in calls)


def test_primary_card_resolution_updates_card_once_without_vo_history(tmp_path, monkeypatch):
    sends = []
    updates = []
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"), token_factory=lambda: "integration-claim")

    def sender(intent, **kwargs):
        sends.append((intent, kwargs))
        return {"ok": True, "status": "sent", "messageId": "om_integration"}

    def updater(message_id, intent, **kwargs):
        updates.append((message_id, intent, kwargs))
        return {"ok": True, "status": "updated", "messageId": message_id}

    coordinator = CodexFeishuApprovalCoordinator(
        store,
        send_notification=sender,
        update_notification=updater,
        status_dir=str(tmp_path),
    )
    record, _ = coordinator.register(approval("integration"), origin())
    assert coordinator.deliver(
        record["routeId"],
        notification_config={"appId": "notification", "appSecret": "secret"},
        chat_config={"appId": "chat", "appSecret": "secret"},
    )["ok"] is True

    class ImmediateExecutor:
        def submit(self, operation, on_failure):
            result = operation()
            if not result.get("ok"):
                on_failure("operation_failed", result)
            return True

    provider_calls = []
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_ROUTES", store)
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_COORDINATOR", coordinator)
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_DELIVERY_EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(
        server,
        "_handle_codex_approval_respond",
        lambda body: provider_calls.append(body) or {"ok": True, "status": "submitted", "runId": "turn-integration"},
    )

    callback = {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger", "event_id": "evt-integration"},
        "event": {
            "open_message_id": "om_integration",
            "open_chat_id": "oc_source",
            "operator": {"open_id": "ou_origin", "union_id": "on_origin"},
            "action": {"value": {"action": "codex_approval_once", "route_id": record["routeId"], "version": 1}},
        },
    }
    first = server._handle_feishu_card_action(callback)
    replay = server._handle_feishu_card_action(callback)

    assert first["outcome"]["businessStatus"] == "approved_once"
    assert replay["outcome"]["businessStatus"] == "already_processed"
    assert len(provider_calls) == 1
    assert updates and updates[-1][0] == "om_integration"
    assert updates[-1][1]["state"] == "approved"
    assert updates[-1][1]["actions"] == []
    assert not (tmp_path / "agent-platform-communications.jsonl").exists()
