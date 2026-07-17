import json
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-codex-feishu-callbacks-import-"))

import server  # noqa: E402
from services.codex_feishu_approvals import CodexFeishuApprovalRouteStore  # noqa: E402


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
