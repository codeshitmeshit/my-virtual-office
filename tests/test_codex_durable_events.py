#!/usr/bin/env python3
"""Durability and idempotency coverage for Codex chat key-state events."""

import json
import os
import sys
import tempfile

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-durable-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"

import server


AGENT = {
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "providerKind": "codex",
    "name": "Codex",
    "profile": "local",
}


def _events(status_dir):
    path = os.path.join(status_dir, "agent-platform-communications.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _configure(monkeypatch, status_dir, provider):
    monkeypatch.setattr(server, "STATUS_DIR", status_dir)
    monkeypatch.setattr(server, "get_roster", lambda: [AGENT])
    monkeypatch.setattr(server, "_codex_provider_from_config", lambda: provider)


class ResultProvider:
    def __init__(self, workspace, result, event=None):
        self.workspace = workspace
        self.result = result
        self.event = event
        self.calls = 0

    def send_message(self, *args, event_callback=None, **kwargs):
        self.calls += 1
        if event_callback and self.event:
            event_callback(dict(self.event))
        return dict(self.result)


def test_durable_operation_is_idempotent_across_file_backed_restart(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        monkeypatch.setattr(server, "STATUS_DIR", status_dir)
        monkeypatch.setattr(server, "get_roster", lambda: [AGENT])

        first = server._append_codex_durable_operation(
            "codex-local", "conv-restart", "terminal", "run-1", {"status": "completed"}
        )
        # The helper deliberately has no process-local dedupe cache. Calling it again
        # models a new process recovering idempotency from the durable journal.
        second = server._append_codex_durable_operation(
            "codex-local", "conv-restart", "terminal", "run-1", {"status": "completed"}
        )

        assert first["id"] == second["id"]
        assert len(_events(status_dir)) == 1


def test_partial_fsync_failure_remains_retry_idempotent(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        monkeypatch.setattr(server, "STATUS_DIR", status_dir)
        monkeypatch.setattr(server, "get_roster", lambda: [AGENT])
        monkeypatch.setattr(server.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("fsync failed")))

        with pytest.raises(OSError, match="fsync failed"):
            server._append_codex_durable_operation(
                "codex-local", "conv-partial", "terminal", "run-partial", {"status": "failed"}, ok=False
            )

        retried = server._append_codex_durable_operation(
            "codex-local", "conv-partial", "terminal", "run-partial", {"status": "failed"}, ok=False
        )
        assert retried["operation"] == "terminal"
        assert len(_events(status_dir)) == 1


def test_accepted_message_write_failure_blocks_provider_and_releases_lock(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = ResultProvider(workspace, {"ok": True, "status": "completed", "reply": "unused"})
        _configure(monkeypatch, status_dir, provider)
        original_append = server._append_comm_event

        def fail_durable(event, *, require_durable=False):
            if require_durable:
                raise OSError("disk unavailable")
            return original_append(event, require_durable=require_durable)

        monkeypatch.setattr(server, "_append_comm_event", fail_durable)
        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conv-accept-failure",
            "message": "must persist first",
            "fromType": "human",
        })

        assert result["status"] == "durable_write_failed"
        assert provider.calls == 0
        lock = server._codex_operation_lock("codex-local")
        assert lock.acquire(blocking=False)
        lock.release()


def test_replyless_failure_persists_one_terminal_outcome(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = ResultProvider(workspace, {
            "ok": False,
            "status": "execution_failed",
            "error": "provider stopped",
            "reply": "",
            "threadId": "thr-failed",
            "turnId": "turn-failed",
        })
        _configure(monkeypatch, status_dir, provider)

        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conv-replyless",
            "message": "fail safely",
            "fromType": "human",
            "_streamRunId": "run-replyless",
        })
        server._append_codex_durable_operation(
            "codex-local", "conv-replyless", "terminal", "run-replyless", {"status": "execution_failed"}, ok=False
        )

        terminal = [event for event in _events(status_dir) if event.get("operation") == "terminal"]
        assert result["status"] == "execution_failed"
        assert len(terminal) == 1
        assert terminal[0]["visibleInOffice"] is False
        assert terminal[0].get("text") == ""


def test_terminal_write_failure_overrides_success(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = ResultProvider(workspace, {
            "ok": True,
            "status": "completed",
            "reply": "durable reply",
            "threadId": "thr-success",
            "turnId": "turn-success",
        })
        _configure(monkeypatch, status_dir, provider)

        def fail_terminal(*args, **kwargs):
            raise OSError("terminal fsync failed")

        monkeypatch.setattr(server, "_append_codex_durable_operation", fail_terminal)
        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conv-terminal-failure",
            "message": "complete",
            "fromType": "human",
        })

        assert result["ok"] is False
        assert result["status"] == "durable_write_failed"
        assert provider.calls == 1


def test_pending_approval_is_durable_and_deduplicated(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = ResultProvider(
            workspace,
            {"ok": False, "status": "needs_human_intervention", "reply": "", "turnId": "turn-approval"},
            event={
                "id": "approval-event",
                "type": "interaction",
                "status": "pending",
                "approval_id": "approval-123",
                "turnId": "turn-approval",
                "threadId": "thr-approval",
            },
        )
        _configure(monkeypatch, status_dir, provider)

        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conv-approval",
            "message": "needs approval",
            "fromType": "human",
            "_streamRunId": "run-approval",
        })
        server._append_codex_durable_operation(
            "codex-local", "conv-approval", "approval_request", "approval-123", {"approvalId": "approval-123"}
        )

        requests = [event for event in _events(status_dir) if event.get("operation") == "approval_request"]
        assert result["status"] == "needs_human_intervention"
        assert len(requests) == 1
        assert requests[0]["metadata"]["approvalId"] == "approval-123"


def test_approval_resolution_write_failure_is_not_published(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        class ApprovalProvider:
            def __init__(self):
                self.workspace = workspace

            def respond_approval(self, profile, approval_id, choice, session_id=None):
                return {"ok": True, "approval": {"id": approval_id, "threadId": session_id or "thr-approval"}}

        provider = ApprovalProvider()
        _configure(monkeypatch, status_dir, provider)
        published = []
        monkeypatch.setattr(server.PROVIDER_EVENT_JOURNAL, "publish", lambda *args, **kwargs: published.append(args))
        monkeypatch.setattr(
            server,
            "_append_codex_approval_result_comm_event",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("approval fsync failed")),
        )

        result = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-approval-resolution",
            "approvalId": "approval-456",
            "threadId": "thr-approval",
            "choice": "approve",
        })

        assert result["status"] == "durable_write_failed"
        assert published == []
