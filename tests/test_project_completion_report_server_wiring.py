#!/usr/bin/env python3
"""Executable contracts for the thin server wiring around completion reports."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-completion-report-server-")

import server  # noqa: E402


class _Worker:
    def __init__(self):
        self.wakes = 0

    def wake(self):
        self.wakes += 1


def test_completion_callbacks_share_the_durable_worker_wakeup(monkeypatch):
    worker = _Worker()
    monkeypatch.setattr(server, "_PROJECT_COMPLETION_REPORT_WORKER", worker)

    direct = server._wake_project_completion_report_worker({"id": "p1"}, "normal")
    compatibility = server._send_project_execution_project_complete_notification(
        {"id": "p1"}, "recovery"
    )

    assert direct["status"] == "queued"
    assert compatibility["status"] == "queued"
    assert worker.wakes == 2


def test_reporting_agent_adapter_uses_provider_directly_not_feishu_chat_transport(monkeypatch):
    captured = []
    monkeypatch.setattr(server, "_is_codex_agent", lambda _agent_id: True)
    monkeypatch.setattr(server, "_is_claude_code_agent", lambda _agent_id: False)
    monkeypatch.setattr(server, "_is_hermes_agent", lambda _agent_id: False)
    monkeypatch.setattr(
        server,
        "_handle_codex_chat",
        lambda body: captured.append(body) or {"ok": True, "reply": "{}"},
    )
    monkeypatch.setattr(
        server,
        "_dispatch_representative_agent_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("chat transport called")),
    )

    result = server._project_completion_report_generate_agent(
        agent_id="codex-main",
        prompt="<task>report</task>",
        conversation_id="project-completion-report:p1:o1",
        timeout_seconds=30,
    )

    assert result == {"ok": True, "reply": "{}"}
    assert captured[0]["fromType"] == "system"
    assert captured[0]["conversationId"] == "project-completion-report:p1:o1"


def test_project_report_handler_exposes_only_sanitized_completion_report_versions(monkeypatch):
    monkeypatch.setattr(server, "_load_projects", lambda: {"projects": [{
        "id": "p1",
        "title": "Demo",
        "columns": [],
        "tasks": [],
        "orchestration": {"completionReports": [{
            "occurrenceId": "o1",
            "version": 1,
            "state": "failed",
            "visibleStatus": "failed",
            "claim": {"token": "private"},
            "generatedReport": {"goal": "private"},
            "lastError": {"code": "failed", "message": "delivery failed"},
        }]},
    }]})

    result = server._handle_project_report("p1")

    item = result["report"]["completionReports"][0]
    assert item["status"] == "failed"
    assert item["canResend"] is True
    assert "claim" not in item
    assert "generatedReport" not in item
