import json
import os
import sys
import tempfile
import threading


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-codex-feishu-callbacks-import-"))

import server  # noqa: E402
from services.codex_feishu_approvals import CodexFeishuApprovalCoordinator, CodexFeishuApprovalRouteStore  # noqa: E402


def install_route(store, route_id="route-1", message_id="om_card_1", actor="ou_origin"):
    record, _ = store.register({
        "routeId": route_id,
        "approvalId": f"approval-{route_id}",
        "agentId": "codex-local",
        "conversationId": "feishu-dm:user:chat",
        "threadId": "thread-1",
        "turnId": "turn-1",
        "actorIds": {"openId": actor, "unionId": "on_origin"},
    })
    store.record_delivery(route_id, {
        "attemptId": f"attempt-{route_id}",
        "application": "notification",
        "status": "sent",
        "ok": True,
        "messageId": message_id,
    })
    return record


def card_body(route_id="route-1", action="codex_approval_once", actor="ou_origin", message_id="om_card_1"):
    return {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger", "event_id": "evt-1"},
        "event": {
            "open_message_id": message_id,
            "open_chat_id": "oc_card",
            "operator": {"open_id": actor, "union_id": "on_origin" if actor == "ou_origin" else "on_other"},
            "action": {"value": {"action": action, "route_id": route_id, "version": 1}},
        },
    }


def test_codex_card_action_resolves_once_and_conflicting_replay_is_stable(tmp_path):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"), token_factory=lambda: "claim-1")
    install_route(store)
    calls = []
    previous_store = server.CODEX_FEISHU_APPROVAL_ROUTES
    previous_respond = server._handle_codex_approval_respond
    previous_status_dir = server.STATUS_DIR
    server.CODEX_FEISHU_APPROVAL_ROUTES = store
    server.STATUS_DIR = str(tmp_path)
    server._handle_codex_approval_respond = lambda body: calls.append(body) or {"ok": True, "status": "approved", "runId": "turn-1"}
    try:
        first = server._handle_feishu_card_action(card_body())
        replay = server._handle_feishu_card_action(card_body(action="codex_approval_cancel"))
    finally:
        server.CODEX_FEISHU_APPROVAL_ROUTES = previous_store
        server._handle_codex_approval_respond = previous_respond
        server.STATUS_DIR = previous_status_dir

    assert first["ok"] is True
    assert first["outcome"]["businessStatus"] == "approved_once"
    assert replay["ok"] is True
    assert replay["outcome"]["businessStatus"] == "already_processed"
    assert replay["outcome"]["decision"] == "approve"
    assert len(calls) == 1
    assert calls[0]["approval_id"] == "approval-route-1"
    assert calls[0]["agentId"] == "codex-local"
    assert calls[0]["conversationId"] == "feishu-dm:user:chat"
    assert calls[0]["recordChatHistory"] is False
    assert store.get("route-1")["decision"] == "approve"


def test_codex_card_action_rejects_wrong_actor_message_stale_and_missing_linkage(tmp_path):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"))
    install_route(store)
    install_route(store, route_id="route-stale", message_id="om_stale")
    store.fail("route-stale", {"ok": False, "status": "expired"}, status="expired")
    calls = []
    previous_store = server.CODEX_FEISHU_APPROVAL_ROUTES
    previous_respond = server._handle_codex_approval_respond
    previous_status_dir = server.STATUS_DIR
    server.CODEX_FEISHU_APPROVAL_ROUTES = store
    server.STATUS_DIR = str(tmp_path)
    server._handle_codex_approval_respond = lambda body: calls.append(body) or {"ok": True}
    try:
        wrong_actor = server._handle_feishu_card_action(card_body(actor="ou_other"))
        wrong_message = server._handle_feishu_card_action(card_body(message_id="om_forged"))
        stale = server._handle_feishu_card_action(card_body(route_id="route-stale", message_id="om_stale"))
        missing = server._handle_feishu_card_action(card_body(route_id="route-missing"))
    finally:
        server.CODEX_FEISHU_APPROVAL_ROUTES = previous_store
        server._handle_codex_approval_respond = previous_respond
        server.STATUS_DIR = previous_status_dir

    assert wrong_actor["outcome"]["businessStatus"] == "callback_actor_invalid"
    assert wrong_message["outcome"]["businessStatus"] == "callback_linkage_invalid"
    assert stale["outcome"]["businessStatus"] == "approval_stale"
    assert missing["outcome"]["businessStatus"] == "callback_linkage_invalid"
    assert calls == []
    serialized = json.dumps([wrong_actor, wrong_message, stale, missing], ensure_ascii=False)
    assert "approval-route-1" not in serialized
    assert "thread-1" not in serialized


def test_codex_card_action_busy_and_ambiguous_primary_are_safe(tmp_path):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"), token_factory=lambda: "claim-busy")
    install_route(store, route_id="route-busy", message_id="om_busy")
    store.claim("route-busy", "approve", {"openId": "ou_origin"})
    store.register({
        "routeId": "route-ambiguous",
        "approvalId": "approval-ambiguous",
        "agentId": "codex-local",
        "conversationId": "feishu-dm:user:chat",
        "threadId": "thread-1",
        "turnId": "turn-1",
        "actorIds": {"openId": "ou_origin"},
    })
    store.record_delivery("route-ambiguous", {
        "attemptId": "attempt-ambiguous",
        "application": "notification",
        "status": "network_error",
        "ok": False,
        "ambiguous": True,
    })
    calls = []
    previous_store = server.CODEX_FEISHU_APPROVAL_ROUTES
    previous_respond = server._handle_codex_approval_respond
    previous_status_dir = server.STATUS_DIR
    server.CODEX_FEISHU_APPROVAL_ROUTES = store
    server.STATUS_DIR = str(tmp_path)
    server._handle_codex_approval_respond = lambda body: calls.append(body) or {"ok": True, "status": "approved"}
    try:
        busy = server._handle_feishu_card_action(card_body(route_id="route-busy", message_id="om_busy"))
        ambiguous = server._handle_feishu_card_action(card_body(route_id="route-ambiguous", message_id="om_unknown_primary"))
    finally:
        server.CODEX_FEISHU_APPROVAL_ROUTES = previous_store
        server._handle_codex_approval_respond = previous_respond
        server.STATUS_DIR = previous_status_dir

    assert busy["outcome"]["businessStatus"] == "callback_in_progress"
    assert ambiguous["outcome"]["businessStatus"] == "approved_once"
    assert len(calls) == 1


def test_feishu_card_decision_uses_isolated_history_policy_but_keeps_provider_event(tmp_path):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"), token_factory=lambda: "claim-isolated")
    install_route(store)
    provider_calls = []
    published = []
    presence = []

    class ApprovalProvider:
        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            provider_calls.append((profile, approval_id, choice, session_id))
            return {
                "ok": True,
                "status": "submitted",
                "approval": {
                    "id": approval_id,
                    "threadId": session_id,
                    "turnId": "turn-1",
                },
            }

    previous_store = server.CODEX_FEISHU_APPROVAL_ROUTES
    previous_provider = server._codex_provider_from_config
    previous_roster = server.get_roster
    previous_status_dir = server.STATUS_DIR
    previous_publish = server.PROVIDER_EVENT_JOURNAL.publish
    previous_presence = server.gateway_presence.set_provider_event
    server.CODEX_FEISHU_APPROVAL_ROUTES = store
    server.STATUS_DIR = str(tmp_path)
    server._codex_provider_from_config = lambda: ApprovalProvider()
    server.get_roster = lambda: [{
        "id": "codex-local", "statusKey": "codex-local", "providerKind": "codex",
        "profile": "local", "providerAgentId": "local", "name": "Codex",
    }]
    server.PROVIDER_EVENT_JOURNAL.publish = lambda *args, **kwargs: published.append((args, kwargs)) or {"id": 1}
    server.gateway_presence.set_provider_event = lambda *args, **kwargs: presence.append((args, kwargs))
    try:
        result = server._handle_feishu_card_action(card_body())
    finally:
        server.CODEX_FEISHU_APPROVAL_ROUTES = previous_store
        server._codex_provider_from_config = previous_provider
        server.get_roster = previous_roster
        server.STATUS_DIR = previous_status_dir
        server.PROVIDER_EVENT_JOURNAL.publish = previous_publish
        server.gateway_presence.set_provider_event = previous_presence

    assert result["ok"] is True
    assert provider_calls == [("local", "approval-route-1", "approve", "thread-1")]
    assert published and published[-1][0][3] == "approval.resolved"
    assert presence
    assert not (tmp_path / "agent-platform-communications.jsonl").exists()
    with open(tmp_path / "feishu-card-actions.jsonl", "r", encoding="utf-8") as stream:
        action_rows = [json.loads(line) for line in stream if line.strip()]
    assert action_rows[-1]["outcome"]["businessStatus"] == "approved_once"
    assert store.get("route-1")["outcome"]["status"] == "submitted"


def test_double_delivery_failure_closes_provider_once_and_marks_visible_failure(tmp_path):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"), token_factory=lambda: "failure-claim")
    sends = []

    def sender(intent, **kwargs):
        sends.append((intent, kwargs))
        return {"ok": False, "status": "network_error", "errorCategory": "TimeoutError"}

    coordinator = CodexFeishuApprovalCoordinator(store, send_notification=sender, status_dir=str(tmp_path))

    class ImmediateExecutor:
        def submit(self, delivery, on_failure):
            result = delivery()
            on_failure("undeliverable", result)
            return True

    class Provider:
        def __init__(self):
            self.calls = []

        def respond_approval(self, profile, approval_id, choice, session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted"}

    provider = Provider()
    failure_state = {"failed": False}
    previous_store = server.CODEX_FEISHU_APPROVAL_ROUTES
    previous_coordinator = server.CODEX_FEISHU_APPROVAL_COORDINATOR
    previous_executor = server.CODEX_FEISHU_APPROVAL_DELIVERY_EXECUTOR
    previous_notifications = server.VO_CONFIG.get("notifications")
    previous_chat = (server.VO_CONFIG.get("feishu") or {}).get("chatApp")
    server.CODEX_FEISHU_APPROVAL_ROUTES = store
    server.CODEX_FEISHU_APPROVAL_COORDINATOR = coordinator
    server.CODEX_FEISHU_APPROVAL_DELIVERY_EXECUTOR = ImmediateExecutor()
    server.VO_CONFIG["notifications"] = {
        "feishuEnabled": True, "feishuAppId": "notification-app", "feishuAppSecret": "notification-secret",
    }
    server.VO_CONFIG.setdefault("feishu", {})["chatApp"] = {
        "enabled": True, "appId": "chat-app", "appSecret": "chat-secret",
    }
    try:
        assert server._queue_codex_feishu_approval(
            {
                "id": "approval-live", "approval_id": "approval-live", "kind": "command",
                "profile": "local", "threadId": "thread-live", "turnId": "turn-live",
                "command": "printf safe",
            },
            {
                "sourceApp": "feishu", "sourceSurface": "feishu-dm", "sourceMessageId": "om_source",
                "feishuChatId": "oc_source", "sourceActor": {"openId": "ou_origin", "unionId": "on_origin"},
                "agentId": "codex-local", "conversationId": "feishu-dm:user:chat",
            },
            provider,
            failure_state,
        ) is True
    finally:
        server.CODEX_FEISHU_APPROVAL_ROUTES = previous_store
        server.CODEX_FEISHU_APPROVAL_COORDINATOR = previous_coordinator
        server.CODEX_FEISHU_APPROVAL_DELIVERY_EXECUTOR = previous_executor
        server.VO_CONFIG["notifications"] = previous_notifications
        server.VO_CONFIG.setdefault("feishu", {})["chatApp"] = previous_chat

    assert len(sends) == 2
    assert provider.calls == [("local", "approval-live", "cancel", "thread-live")]
    assert failure_state["failed"] is True
    assert failure_state["reason"] == "undeliverable"
    route_id = failure_state["routeId"]
    assert store.get(route_id)["status"] == "failed"
    assert store.get(route_id)["outcome"]["status"] == "approval_delivery_failed"


def test_saturated_delivery_queue_cancels_registered_approval_once(tmp_path, monkeypatch):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"), token_factory=lambda: "saturation-claim")
    coordinator = CodexFeishuApprovalCoordinator(
        store,
        send_notification=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not send")),
        status_dir=str(tmp_path),
    )

    class RejectingExecutor:
        def submit(self, _delivery, _on_failure):
            return False

    finished = threading.Event()
    calls = []

    class Provider:
        def respond_approval(self, profile, approval_id, choice, session_id=None):
            calls.append((profile, approval_id, choice, session_id))
            finished.set()
            return {"ok": True, "status": "submitted"}

    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_ROUTES", store)
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_COORDINATOR", coordinator)
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_DELIVERY_EXECUTOR", RejectingExecutor())
    failure_state = {"failed": False}
    server._queue_codex_feishu_approval(
        {
            "id": "approval-saturated", "approval_id": "approval-saturated", "kind": "permissions",
            "profile": "local", "threadId": "thread-saturated", "turnId": "turn-saturated",
        },
        {
            "sourceApp": "feishu", "sourceSurface": "feishu-dm", "sourceMessageId": "om_saturated",
            "feishuChatId": "oc_saturated", "sourceActor": {"openId": "ou_origin"},
            "agentId": "codex-local", "conversationId": "conv-saturated",
        },
        Provider(),
        failure_state,
    )
    assert finished.wait(1)
    assert calls == [("local", "approval-saturated", "cancel", "thread-saturated")]
    assert failure_state["reason"] == "queue_saturated"
    assert store.get(failure_state["routeId"])["status"] == "failed"


def test_duplicate_pending_event_delivers_existing_route_only_once(tmp_path, monkeypatch):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"))
    sends = []
    coordinator = CodexFeishuApprovalCoordinator(
        store,
        send_notification=lambda *_args, **_kwargs: sends.append(True) or {
            "ok": True, "status": "sent", "messageId": "om_once",
        },
        status_dir=str(tmp_path),
    )

    class ImmediateExecutor:
        def __init__(self):
            self.submissions = 0

        def submit(self, operation, _on_failure):
            self.submissions += 1
            operation()
            return True

    executor = ImmediateExecutor()
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_ROUTES", store)
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_COORDINATOR", coordinator)
    monkeypatch.setattr(server, "CODEX_FEISHU_APPROVAL_DELIVERY_EXECUTOR", executor)
    monkeypatch.setattr(server, "_codex_feishu_approval_delivery_configs", lambda: (
        {}, {"appId": "chat", "appSecret": "secret"},
    ))
    approval_payload = {
        "id": "approval-duplicate", "approval_id": "approval-duplicate", "kind": "command",
        "profile": "local", "threadId": "thread-duplicate", "turnId": "turn-duplicate",
        "command": "printf safe",
    }
    context = {
        "sourceApp": "feishu", "sourceSurface": "feishu-dm", "sourceMessageId": "om_duplicate",
        "feishuChatId": "oc_duplicate", "sourceActor": {"openId": "ou_origin"},
        "agentId": "codex-local", "conversationId": "conv-duplicate",
    }

    assert server._queue_codex_feishu_approval(approval_payload, context, object(), {}) is True
    assert server._queue_codex_feishu_approval(approval_payload, context, object(), {}) is True
    assert executor.submissions == 1
    assert sends == [True]
    assert coordinator.stats()["metrics"]["duplicate_delivery_suppressed"] == 1


def test_card_action_audit_is_route_linked_and_rotated(tmp_path, monkeypatch):
    monkeypatch.setenv("VO_FEISHU_AUDIT_MAX_BYTES", "512")
    monkeypatch.setenv("VO_FEISHU_AUDIT_BACKUPS", "2")
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    for index in range(20):
        server._record_feishu_card_action(
            {"schema": "2.0", "header": {"event_type": "card.action.trigger"}},
            card_body(route_id="route-audit")["event"],
            {"action": "codex_approval_once", "route_id": "route-audit", "padding": "x" * 120},
            outcome={"businessStatus": f"replay-{index}"},
        )
    path = tmp_path / "feishu-card-actions.jsonl"
    assert path.exists()
    assert (tmp_path / "feishu-card-actions.jsonl.1").exists()
    with open(path, "r", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    assert rows[-1]["routeId"] == "route-audit"
