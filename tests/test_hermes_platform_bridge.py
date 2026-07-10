#!/usr/bin/env python3
"""Focused Hermes Messaging Gateway platform bridge tests."""
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import types


APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
SERVER_PATH = os.path.join(APP_DIR, "server.py")


def load_server():
    sys.path.insert(0, APP_DIR)
    if "websockets" not in sys.modules:
        websockets = types.ModuleType("websockets")
        websockets_asyncio = types.ModuleType("websockets.asyncio")
        websockets_client = types.ModuleType("websockets.asyncio.client")

        async def _missing_connect(*args, **kwargs):
            raise RuntimeError("websockets stub is not available in this isolated test")

        websockets_client.connect = _missing_connect
        websockets_asyncio.client = websockets_client
        websockets.asyncio = websockets_asyncio
        sys.modules["websockets"] = websockets
        sys.modules["websockets.asyncio"] = websockets_asyncio
        sys.modules["websockets.asyncio.client"] = websockets_client
    spec = importlib.util.spec_from_file_location("vo_server_hermes_platform_under_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  {mark} {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        raise AssertionError(name)


class Headers(dict):
    def get(self, key, default=None):
        for existing, value in self.items():
            if existing.lower() == key.lower():
                return value
        return default


def main():
    old_env = os.environ.copy()
    try:
        with tempfile.TemporaryDirectory() as root:
            status_dir = os.path.join(root, "status")
            oc_home = os.path.join(root, "openclaw")
            os.makedirs(oc_home, exist_ok=True)
            with open(os.path.join(oc_home, "openclaw.json"), "w", encoding="utf-8") as f:
                json.dump({"agents": {"list": [{"id": "main"}]}}, f)

            os.environ.update({
                "VO_STATUS_DIR": status_dir,
                "VO_OPENCLAW_PATH": oc_home,
                "VO_HERMES_ENABLED": "false",
                "VO_CODEX_ENABLED": "false",
                "VO_CLAUDE_CODE_ENABLED": "false",
                "VO_HERMES_PLATFORM_ENABLED": "true",
                "VO_HERMES_PLATFORM_TOKEN": "test-token",
                "VO_HERMES_PLATFORM_AGENT_ID": "hermes-gateway",
            })
            server = load_server()
            server.gateway_presence.set_manual_override = lambda *args, **kwargs: None
            server._discovered_roster = server._discover_roster()
            server.AGENT_SESSION_IDS = server._build_agent_session_ids()

            check("Gateway platform agent is synthesized", any(a.get("statusKey") == "hermes-gateway" for a in server.get_roster()))
            check("Auth accepts bearer token", server._hermes_platform_auth_error(Headers({"Authorization": "Bearer test-token"})) is None)
            check("Auth rejects missing token", server._hermes_platform_auth_error(Headers({})).get("_status") == 401)
            check("Auth rejects wrong token", server._hermes_platform_auth_error(Headers({"Authorization": "Bearer wrong"})).get("_status") == 403)

            enqueued = server._handle_hermes_platform_enqueue({
                "message": "Hello Hermes gateway",
                "fromType": "human",
                "fromUserId": "user-1",
                "fromDisplayName": "Office User",
                "toAgentId": "hermes-gateway",
                "conversationId": "user-1__hermes-gateway",
            })
            check("Enqueue succeeds", enqueued.get("ok"), str(enqueued))
            msg_id = enqueued.get("messageId")
            poll = server._handle_hermes_platform_poll({"adapterId": ["adapter-test"], "limit": ["1"]})
            check("Poll succeeds", poll.get("ok"), str(poll))
            check("Poll returns queued message", poll.get("messages") and poll["messages"][0]["id"] == msg_id, str(poll))
            lease_id = poll["messages"][0]["leaseId"]
            ack = server._handle_hermes_platform_ack({"messageId": msg_id, "leaseId": lease_id, "ok": True})
            check("Ack marks delivered", ack.get("ok") and ack.get("status") == "delivered", str(ack))
            reply = server._handle_hermes_platform_reply({
                "adapterId": "adapter-test",
                "chatId": "user-1__hermes-gateway",
                "message": "Hello from Hermes",
            })
            check("Reply succeeds", reply.get("ok"), str(reply))
            history = server._load_comm_history(conversation_id="user-1__hermes-gateway")
            check("Communication log has request and reply", len(history) == 2, str(history))
            check("Reply text is logged", history[-1].get("text") == "Hello from Hermes", str(history[-1]))
            queue_mode = os.stat(server._hermes_platform_queue_path()).st_mode & 0o777
            check("Gateway queue is private", queue_mode == 0o600, oct(queue_mode))
            comm_mode = os.stat(server._comm_log_path()).st_mode & 0o777
            check("Gateway communication log is private", comm_mode == 0o600, oct(comm_mode))

            old_max_messages = server._HERMES_PLATFORM_MAX_MESSAGES
            try:
                server._HERMES_PLATFORM_MAX_MESSAGES = 1
                full_state = server._load_hermes_platform_state()
                full_state["messages"] = [{"id": "pending-one", "status": "queued", "text": "pending"}]
                server._save_hermes_platform_state(full_state)
                comm_count_before = len(server._load_comm_history(limit=1000))
                rejected = server._handle_hermes_platform_enqueue({"message": "must not be dropped"})
                check("Gateway queue applies backpressure", rejected.get("_status") == 503, str(rejected))
                preserved = server._load_hermes_platform_state().get("messages") or []
                check("Gateway queue preserves pending messages", [item.get("id") for item in preserved] == ["pending-one"], str(preserved))
                check("Rejected enqueue does not create a communication event", len(server._load_comm_history(limit=1000)) == comm_count_before)

                failed_state = server._hermes_platform_state_default()
                failed_state["messages"] = [{"id": "failed-one", "status": "failed", "text": "failed"}]
                server._save_hermes_platform_state(failed_state)
                accepted = server._handle_hermes_platform_enqueue({"message": "after failed terminal"})
                check("Failed terminal messages release queue capacity", accepted.get("ok") is True, str(accepted))

                delivered_state = server._hermes_platform_state_default()
                delivered_state["messages"] = [{
                    "id": "stale-delivered",
                    "status": "delivered",
                    "text": "delivered without reply",
                    "deliveredAt": server._now_ms() - 3_700_000,
                }]
                server._save_hermes_platform_state(delivered_state)
                accepted_after_stale = server._handle_hermes_platform_enqueue({"message": "after stale delivered"})
                check("Stale delivered messages release queue capacity", accepted_after_stale.get("ok") is True, str(accepted_after_stale))
                server.VO_CONFIG["hermes"]["platformDeliveredRetentionSec"] = "not-a-number"
                check("Invalid delivered retention falls back safely", isinstance(server._hermes_platform_message_active({"status": "delivered", "deliveredAt": server._now_ms()}), bool))
                server.VO_CONFIG["hermes"].pop("platformDeliveredRetentionSec", None)
            finally:
                server._HERMES_PLATFORM_MAX_MESSAGES = old_max_messages
                server._save_hermes_platform_state(server._hermes_platform_state_default())

            agent = server._get_hermes_agent("hermes-gateway")

            def responder():
                deadline = time.time() + 5
                target = None
                while time.time() < deadline:
                    state = server._load_hermes_platform_state()
                    for item in reversed(state.get("messages") or []):
                        if item.get("text") == "Blocking bridge hello":
                            target = item
                            break
                    if target:
                        break
                    time.sleep(0.1)
                if target:
                    server._handle_hermes_platform_reply({
                        "adapterId": "adapter-test",
                        "messageId": target["id"],
                        "message": "Blocking bridge reply",
                    })

            thread = threading.Thread(target=responder, daemon=True)
            thread.start()
            chat = server._handle_hermes_platform_chat({
                "message": "Blocking bridge hello",
                "fromType": "human",
                "fromDisplayName": "User",
                "conversationId": "gateway-conversation-a",
                "timeoutSec": 5,
            }, agent)
            thread.join(timeout=2)
            check("Blocking chat returns plugin reply", chat.get("ok") and chat.get("reply") == "Blocking bridge reply", str(chat))
            gateway_history = server._load_hermes_history("gateway", "gateway-conversation-a")
            check("Gateway Hermes history records assistant reply", gateway_history[-1].get("text") == "Blocking bridge reply", str(gateway_history))
            check("Gateway Hermes history stays conversation-scoped", not server._load_hermes_history("gateway"), str(server._load_hermes_history("gateway")))
            check("Gateway conversation stores its platform session", server._get_hermes_session_id("gateway", "gateway-conversation-a") == "gateway-conversation-a")
            sessions, status = server.handle_chat_sessions_list("hermes-gateway")
            check("Gateway session browser uses platform conversations", status == 200 and any(item.get("id") == "gateway-conversation-a" for item in sessions.get("sessions") or []), str(sessions))
            switched, switch_status = server.handle_chat_session_switch("hermes-gateway", "gateway-conversation-a")
            check("Gateway session switch loads platform history", switch_status == 200 and switched.get("conversationId") == "gateway-conversation-a" and switched.get("messages", [])[-1].get("text") == "Blocking bridge reply", str(switched))

    finally:
        os.environ.clear()
        os.environ.update(old_env)

    print("\n  Hermes platform bridge: all checks passed")


if __name__ == "__main__":
    main()
