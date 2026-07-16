#!/usr/bin/env python3
"""Offline transport selection/failure/rollback rehearsal without Feishu credentials."""
import json
import os
import pathlib
import subprocess
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


def processing_recovery_config(enabled):
    config_module = pathlib.Path(ROOT, "integrations", "feishu-channel-worker", "src", "config.mjs").as_uri()
    env = os.environ.copy()
    env["VO_FEISHU_CHAT_PROCESSING_RECOVERY_ENABLED"] = "true" if enabled else "false"
    result = subprocess.run(
        ["node", "--input-type=module", "-e", f"import {{ processingRecoveryConfig }} from '{config_module}'; console.log(JSON.stringify(processingRecoveryConfig(process.env)));"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    return json.loads(result.stdout.strip())


def main():
    previous_config = server.VO_CONFIG
    previous_override = os.environ.get("VO_FEISHU_CHAT_TRANSPORT")
    previous_group_override = os.environ.get("VO_FEISHU_GROUP_CHAT_ENABLED")
    os.environ.pop("VO_FEISHU_GROUP_CHAT_ENABLED", None)
    server.VO_CONFIG = {
        **previous_config,
        "feishu": {
            "chatApp": {
                "enabled": True,
                "appId": "cli_rehearsal",
                "appSecret": "redacted-rehearsal-secret",
                "representativeAgentId": "hermes-default",
                "transportImplementation": "channel-sdk-node",
                "groupChatEnabled": False,
            },
            "bindings": {},
        },
    }
    previous_dispatch = server._dispatch_representative_agent_message

    def group_event(message_id):
        return {
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_rehearsal"}, "sender_name": "Rehearsal Member",
                    "sender_type": "user", "sender_is_bot": False,
                },
                "message": {
                    "message_id": message_id, "chat_id": "oc_rehearsal", "chat_type": "group",
                    "message_type": "text", "text": f"rehearsal:{message_id}",
                    "mentions": [{"openId": "ou_vo", "name": "VO", "isBot": True}],
                },
            }
        }

    def fake_dispatch(agent_id, text, conversation_id, source_meta):
        return {"ok": True, "reply": "offline rehearsal reply", "conversationId": conversation_id}

    try:
        server._dispatch_representative_agent_message = fake_dispatch
        os.environ["VO_FEISHU_CHAT_TRANSPORT"] = "channel-sdk-node"
        switch_off = server._feishu_chat_config_response()
        private_record = server._record_feishu_channel_event({
            "event": "turn_completed",
            "sourceMessageId": "om_rehearsal_private",
            "conversationId": "feishu-dm:rehearsal",
            "chatType": "p2p",
            "reply": "persisted before transport switch",
        })

        server.VO_CONFIG["feishu"]["chatApp"]["groupChatEnabled"] = True
        switch_on = server._feishu_chat_config_response()
        injected_delivery_failure = server._handle_feishu_chat_message_event(
            group_event("om_rehearsal_group"),
            send_text=lambda *_: {"ok": False, "status": "timeout", "category": "send_timeout"},
        )
        audit_size_before_disable = os.path.getsize(server._feishu_channel_record_path())

        server.VO_CONFIG["feishu"]["chatApp"]["groupChatEnabled"] = False
        disabled = server._handle_feishu_chat_message_event(
            group_event("om_rehearsal_disabled"),
            send_text=lambda *_: {"ok": True, "status": "sent"},
        )
        persisted_after_restart = server._feishu_channel_idempotency_hit("om_rehearsal_group")
        audit_size_after_disable = os.path.getsize(server._feishu_channel_record_path())

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

        recovery_off = processing_recovery_config(False)
        recovery_on = processing_recovery_config(True)

        os.environ["VO_FEISHU_CHAT_TRANSPORT"] = "legacy-python"
        rollback = server._effective_feishu_chat_transport()
        rollback_status = server._feishu_chat_config_response()
        persisted_private = server._feishu_channel_idempotency_hit("om_rehearsal_private")
        checks = {
            "groupDefaultOff": switch_off.get("groupChatEffective") is False,
            "groupEnabledForTest": switch_on.get("groupChatEffective") is True,
            "deliveryFailureClassified": injected_delivery_failure.get("status") == "delivery_failed",
            "disableRejectsNewGroup": disabled.get("status") == "ignored_unsupported_chat_type",
            "restartReconcilesInFlight": bool(persisted_after_restart and persisted_after_restart.get("indexState") == "completed"),
            "nodeSelected": selected == "channel-sdk-node",
            "failureInjected": injected_failure.get("status") == "missing_channel_sdk",
            "startupIsolated": injected_failure.get("affectsVoStartup") is False,
            "recoveryOffRetainsSpoolMode": recovery_off.get("enabled") is False,
            "recoveryEnablementValidated": recovery_on.get("enabled") is True,
            "retryWakeBelowOneMinute": recovery_on.get("maxDelayMs", 60000) + recovery_on.get("jitterMs", 0) < 60000,
            "callbackAttemptBounded": recovery_on.get("callbackAttemptTimeoutMs", 60000) <= 55000,
            "legacyRestored": rollback == "legacy-python",
            "legacyGroupDisabled": rollback_status.get("groupChatEffective") is False,
            "privateHistoryPreserved": bool(persisted_private and persisted_private.get("sourceMessageId") == private_record.get("sourceMessageId")),
            "noHistoryMigration": audit_size_after_disable >= audit_size_before_disable,
        }
        result = {
            "ok": all(checks.values()),
            "checks": checks,
            "switchOff": switch_off.get("groupChatStatus"),
            "switchOn": switch_on.get("groupChatStatus"),
            "nodeSelection": selected,
            "injectedFailure": {k: v for k, v in injected_failure.items() if k not in {"lastError"}},
            "rollback": rollback,
            "historyPreserved": bool(persisted_private and persisted_after_restart),
            "statusDir": "<temporary>",
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    finally:
        server._dispatch_representative_agent_message = previous_dispatch
        server.VO_CONFIG = previous_config
        if previous_override is None:
            os.environ.pop("VO_FEISHU_CHAT_TRANSPORT", None)
        else:
            os.environ["VO_FEISHU_CHAT_TRANSPORT"] = previous_override
        if previous_group_override is None:
            os.environ.pop("VO_FEISHU_GROUP_CHAT_ENABLED", None)
        else:
            os.environ["VO_FEISHU_GROUP_CHAT_ENABLED"] = previous_group_override


if __name__ == "__main__":
    raise SystemExit(main())
