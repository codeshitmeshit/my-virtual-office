#!/usr/bin/env python3
"""Offline transport selection/failure/rollback rehearsal without Feishu credentials."""
import json
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

status_dir = tempfile.mkdtemp(prefix="vo-feishu-rollout-rehearsal-")
os.environ.update({
    "VO_STATUS_DIR": status_dir,
    "VO_HERMES_ENABLED": "0",
    "VO_CODEX_ENABLED": "0",
})

import server  # noqa: E402


def main():
    previous_config = server.VO_CONFIG
    previous_override = os.environ.get("VO_FEISHU_CHAT_TRANSPORT")
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_rehearsal",
                "appSecret": "redacted-rehearsal-secret",
                "representativeAgentId": "hermes-default",
                "transportImplementation": "channel-sdk-node",
            },
            "bindings": {},
        },
    }
    try:
        os.environ["VO_FEISHU_CHAT_TRANSPORT"] = "legacy-python"
        legacy = server._effective_feishu_chat_transport()
        record = server._record_feishu_channel_event({
            "event": "turn_completed",
            "sourceMessageId": "om_rehearsal",
            "conversationId": "feishu-dm:rehearsal",
            "reply": "persisted before transport switch",
        })

        os.environ["VO_FEISHU_CHAT_TRANSPORT"] = "channel-sdk-node"
        selected = server._effective_feishu_chat_transport()
        worker = server.FeishuChatWorkerProcess(
            app_id="cli_rehearsal",
            app_secret="redacted-rehearsal-secret",
            callback_url="http://127.0.0.1/inbound",
            status_dir=status_dir,
            transport=selected,
        )
        worker._node_preflight = lambda: {
            "ok": False,
            "status": "missing_channel_sdk",
            "scope": "feishu_chat",
            "affectsVoStartup": False,
            "action": "npm ci --omit=dev",
        }
        injected_failure = worker.start()

        os.environ["VO_FEISHU_CHAT_TRANSPORT"] = "legacy-python"
        rollback = server._effective_feishu_chat_transport()
        persisted = server._feishu_channel_idempotency_hit("om_rehearsal")
        checks = {
            "legacySelected": legacy == "legacy-python",
            "nodeSelected": selected == "channel-sdk-node",
            "failureInjected": injected_failure.get("status") == "missing_channel_sdk",
            "startupIsolated": injected_failure.get("affectsVoStartup") is False,
            "legacyRestored": rollback == "legacy-python",
            "historyPreserved": bool(persisted and persisted.get("sourceMessageId") == record.get("sourceMessageId")),
        }
        result = {
            "ok": all(checks.values()),
            "checks": checks,
            "legacyStart": legacy,
            "nodeSelection": selected,
            "injectedFailure": {k: v for k, v in injected_failure.items() if k not in {"lastError"}},
            "rollback": rollback,
            "historyPreserved": bool(persisted),
            "statusDir": status_dir,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    finally:
        server.VO_CONFIG = previous_config
        if previous_override is None:
            os.environ.pop("VO_FEISHU_CHAT_TRANSPORT", None)
        else:
            os.environ["VO_FEISHU_CHAT_TRANSPORT"] = previous_override


if __name__ == "__main__":
    raise SystemExit(main())
