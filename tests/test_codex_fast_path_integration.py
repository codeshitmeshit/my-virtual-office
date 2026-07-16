#!/usr/bin/env python3
"""Codex transient activity uses the bounded fast path without ledger rewrites."""

import os
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-fast-path-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"

import server
from services.codex_fast_path import CodexEventFastPath, CodexFastPathSettings, CodexFastPathTelemetry


AGENT = {
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "providerKind": "codex",
    "name": "Codex",
    "profile": "local",
}


def _enabled_service():
    return CodexEventFastPath(CodexFastPathSettings(requested_enabled=True, enabled=True), max_scopes=16)


class EventProvider:
    def __init__(self, workspace, events):
        self.workspace = workspace
        self.events = events

    def send_message(self, *args, event_callback=None, thread_id="", **kwargs):
        for event in self.events:
            event_callback({
                "threadId": thread_id or "thr-fast-path",
                "turnId": "turn-fast-path",
                **event,
            })
        return {
            "ok": True,
            "status": "completed",
            "reply": "done",
            "threadId": thread_id or "thr-fast-path",
            "turnId": "turn-fast-path",
            "modifiedFiles": [],
        }


def _configure(monkeypatch, status_dir, provider):
    monkeypatch.setattr(server, "STATUS_DIR", status_dir)
    monkeypatch.setattr(server, "get_roster", lambda: [AGENT])
    monkeypatch.setattr(server, "_codex_provider_from_config", lambda: provider)
    monkeypatch.setattr(server, "_CODEX_EVENT_FAST_PATH", _enabled_service())


def test_enabled_path_keeps_transient_activity_live_and_persists_only_key_events(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = EventProvider(workspace, [
            {"id": "tool-live", "sequence": 1, "type": "activity", "status": "running", "name": "commandExecution", "ts": 1},
            {"id": "approval-live", "sequence": 2, "type": "interaction", "status": "pending", "interactionId": "approval-live", "ts": 2},
            {"id": "turn-live", "sequence": 3, "type": "turn", "status": "completed", "output": {"reply": "done"}, "ts": 3},
        ])
        _configure(monkeypatch, status_dir, provider)
        persisted_types = []
        original_save = server._save_codex_activity

        def capture_save(events):
            persisted_types.append(events[-1].get("type"))
            original_save(events)

        monkeypatch.setattr(server, "_save_codex_activity", capture_save)
        live_during_callback = []

        def inspect_live(record):
            if record.get("id") == "tool-live":
                response = server._handle_codex_activity({
                    "agentId": ["codex-local"],
                    "conversationId": ["conv-fast-path"],
                })
                live_during_callback.extend(response["events"])

        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conv-fast-path",
            "message": "exercise fast path",
            "fromType": "human",
            "_streamRunId": "run-fast-path",
            "_onActivity": inspect_live,
        })

        assert result["ok"] is True
        assert any(event.get("id") == "tool-live" for event in live_during_callback)
        assert persisted_types == ["interaction", "turn"]
        persisted = server._load_codex_activity()
        assert [event["type"] for event in persisted] == ["interaction", "turn"]
        assert [event["sequence"] for event in persisted] == [2, 3]

        # A new process has no transient live view, but durable compatibility
        # records remain available and correctly ordered.
        monkeypatch.setattr(server, "_CODEX_EVENT_FAST_PATH", _enabled_service())
        recovered = server._handle_codex_activity({
            "agentId": ["codex-local"],
            "conversationId": ["conv-fast-path"],
        })
        assert [event["type"] for event in recovered["events"]] == ["interaction", "turn"]


def test_background_run_fast_path_never_upserts_or_removes_codex_progress_ledger(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = EventProvider(workspace, [
            {"id": "reasoning-fast", "sequence": 1, "type": "reasoning", "status": "running", "text": "working", "ts": 1},
            {"id": "turn-fast", "sequence": 2, "type": "turn", "status": "completed", "output": {"reply": "done"}, "ts": 2},
        ])
        _configure(monkeypatch, status_dir, provider)
        monkeypatch.setattr(
            server,
            "_append_codex_progress_comm_event",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fast path rewrote progress ledger")),
        )
        monkeypatch.setattr(
            server,
            "_remove_comm_progress_events",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fast path rewrote progress ledger")),
        )

        started = server._handle_codex_run_start({
            "agentId": "codex-local",
            "conversationId": "conv-fast-background",
            "message": "hello",
        })
        deadline = time.time() + 3
        snapshot = None
        while time.time() < deadline:
            snapshot = server.PROVIDER_RUN_REPOSITORY.get(started["runId"])
            if snapshot and snapshot.get("done"):
                break
            time.sleep(0.01)

        assert snapshot and snapshot["done"] is True
        assert snapshot["result"]["ok"] is True
        history = server._load_comm_history(limit=50, conversation_id="conv-fast-background", agent_id="codex-local")
        assert not [event for event in history if (event.get("metadata") or {}).get("ephemeral") == "codex-progress"]


def test_chat_path_records_backend_stages_without_content(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = EventProvider(workspace, [
            {"id": "reasoning-timing", "sequence": 1, "type": "reasoning", "status": "running", "text": "sensitive response text", "ts": 1},
            {"id": "turn-timing", "sequence": 2, "type": "turn", "status": "completed", "output": {"reply": "done"}, "ts": 2},
        ])
        _configure(monkeypatch, status_dir, provider)
        telemetry = CodexFastPathTelemetry()
        monkeypatch.setattr(server, "_CODEX_FAST_PATH_TELEMETRY", telemetry)
        telemetry.start("run-timing", "conversation-timing")

        result = server._handle_codex_chat({
            "agentId": "codex-local",
            "conversationId": "conversation-timing",
            "message": "sensitive prompt text",
            "fromType": "human",
            "_streamRunId": "run-timing",
        })

        assert result["ok"] is True
        diagnostics = telemetry.diagnostics()
        stages = diagnostics["recentRuns"][-1]["stageMs"]
        assert {
            "request_accepted",
            "provider_request_sent",
            "first_native_event",
            "first_displayable_fragment",
            "provider_terminal",
            "durable_terminal_committed",
        }.issubset(stages)
        assert "sensitive prompt text" not in str(diagnostics)
        assert "sensitive response text" not in str(diagnostics)
