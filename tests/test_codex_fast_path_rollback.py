#!/usr/bin/env python3
"""Executable rollback rehearsal for the Codex chat fast path."""

import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-rollback-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"

import server
from services.codex_fast_path import CodexEventFastPath, CodexFastPathSettings


AGENT = {
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "providerKind": "codex",
    "name": "Codex",
    "profile": "local",
}


class RollbackProvider:
    workspace = ""

    def __init__(self, workspace):
        self.workspace = workspace

    def send_message(self, _message, *, event_callback=None, thread_id="", **_kwargs):
        native_thread = thread_id or "thr-rollback"
        event_callback({
            "id": "approval-rollback-event",
            "type": "interaction",
            "status": "pending",
            "approval_id": "approval-rollback",
            "interactionId": "approval-rollback",
            "threadId": native_thread,
            "turnId": "turn-rollback",
            "sequence": 1,
            "ts": 1,
        })
        event_callback({
            "id": "turn-rollback-event",
            "type": "turn",
            "status": "completed",
            "threadId": native_thread,
            "turnId": "turn-rollback",
            "sequence": 2,
            "output": {"reply": "durable rollback reply"},
            "ts": 2,
        })
        return {
            "ok": True,
            "status": "completed",
            "reply": "durable rollback reply",
            "threadId": native_thread,
            "turnId": "turn-rollback",
            "modifiedFiles": [],
        }

    def respond_approval(self, _profile, approval_id, choice, session_id=None):
        return {
            "ok": True,
            "status": "submitted",
            "approval": {
                "id": approval_id,
                "approval_id": approval_id,
                "threadId": session_id or "thr-rollback",
                "turnId": "turn-rollback",
                "status": "approved" if choice == "approve" else "cancelled",
            },
        }


def _snapshot_files(root):
    snapshot = {}
    for current, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(current, name)
            with open(path, "rb") as stream:
                snapshot[os.path.relpath(path, root)] = stream.read()
    return snapshot


def test_enabled_write_can_be_read_flag_off_without_data_repair(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = RollbackProvider(workspace)
        monkeypatch.setattr(server, "STATUS_DIR", status_dir)
        monkeypatch.setattr(server, "get_roster", lambda: [AGENT])
        monkeypatch.setattr(server, "_codex_provider_from_config", lambda: provider)
        monkeypatch.setattr(
            server,
            "_CODEX_EVENT_FAST_PATH",
            CodexEventFastPath(CodexFastPathSettings(requested_enabled=True, enabled=True)),
        )

        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conv-rollback",
            "message": "persist this before rollback",
            "fromType": "human",
            "idempotencyKey": "rollback-request-1",
            "_streamRunId": "run-rollback",
        })
        approval = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-rollback",
            "approvalId": "approval-rollback",
            "threadId": "thr-rollback",
            "choice": "approve",
        })

        assert result["ok"] is True
        assert result["reply"] == "durable rollback reply"
        assert approval["ok"] is True
        before_rollback = _snapshot_files(status_dir)

        # Model the controlled restart with the code still deployed but the
        # startup-only flag disabled. The new process has an empty live view.
        monkeypatch.setattr(
            server,
            "_CODEX_EVENT_FAST_PATH",
            CodexEventFastPath(CodexFastPathSettings(requested_enabled=False, enabled=False)),
        )

        history = server._load_comm_history(
            limit=100,
            conversation_id="conv-rollback",
            agent_id="codex-local",
        )
        activity = server._handle_codex_activity({
            "agentId": ["codex-local"],
            "conversationId": ["conv-rollback"],
        })
        thread_id = server._get_codex_thread_id("codex-local", "conv-rollback")

        texts = [str(event.get("text") or "") for event in history]
        operations = [str(event.get("operation") or "") for event in history]
        assert "persist this before rollback" in texts
        assert "durable rollback reply" in texts
        assert "approval_request" in operations
        assert "approval_resolution" in operations
        assert "terminal" in operations
        assert thread_id == "thr-rollback"
        assert [event["type"] for event in activity["events"]] == ["interaction", "turn"]
        assert activity["events"][-1]["output"]["reply"] == "durable rollback reply"

        # Read-only rollback recovery must not need migration, reverse writes,
        # or any data-repair mutation.
        assert _snapshot_files(status_dir) == before_rollback
