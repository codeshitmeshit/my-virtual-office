#!/usr/bin/env python3
"""Structured Agent generation contracts for project completion reports."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_generation import (
    CompletionReportGenerationError,
    generate_completion_report,
)


PROJECT = {"id": "project-1", "title": "Launch", "description": "Ship the release"}
OCCURRENCE = {
    "occurrenceId": "stage-run:run-2",
    "version": 2,
    "runId": "run-2",
    "completedAt": "2026-08-03T02:00:00+08:00",
}
REPORT = {
    "goal": "Ship the release",
    "conclusion": "Release completed successfully.",
    "keyResults": ["Package published", "Smoke tests passed"],
    "nonFatalExceptions": ["Metrics dashboard was delayed"],
    "followUps": ["Review adoption next week"],
    "importantArtifacts": [
        {"label": "Release notes", "path": "release/notes.md", "note": "Owner-facing summary"},
    ],
}


def test_generate_completion_report_validates_reply_and_renders_versioned_markdown():
    calls = []

    def provider(**request):
        calls.append(request)
        return {"ok": True, "status": "completed", "reply": json.dumps(REPORT)}

    result = generate_completion_report(
        PROJECT,
        OCCURRENCE,
        artifacts=[{"path": "release/notes.md", "content": "Done", "inline": True}],
        omissions=[],
        reporting_agent_id="feishu-main-agent",
        generate=provider,
    )

    assert result["report"] == REPORT
    assert result["reportingAgentId"] == "feishu-main-agent"
    assert calls[0]["agent_id"] == "feishu-main-agent"
    assert calls[0]["conversation_id"] == "project-completion-report:project-1:stage-run:run-2"
    assert calls[0]["timeout_seconds"] == 600
    assert calls[0]["prompt"].startswith("<project_completion_report_prompt>")
    assert "# Project Completion Report — Launch" in result["markdown"]
    assert "- Version: v2" in result["markdown"]
    assert "- Run: run-2" in result["markdown"]
    assert "## Non-fatal Exceptions" in result["markdown"]
    assert "release/notes.md" in result["markdown"]


def test_generate_completion_report_rejects_missing_agent_without_calling_provider():
    with pytest.raises(CompletionReportGenerationError) as raised:
        generate_completion_report(
            PROJECT,
            OCCURRENCE,
            artifacts=[],
            omissions=[],
            reporting_agent_id="",
            generate=lambda **_request: (_ for _ in ()).throw(AssertionError("provider called")),
        )

    assert raised.value.code == "reporting_agent_missing"
    assert raised.value.recoverable is False


@pytest.mark.parametrize("status", ["busy", "timeout"])
def test_generate_completion_report_classifies_transient_provider_failures(status):
    with pytest.raises(CompletionReportGenerationError) as raised:
        generate_completion_report(
            PROJECT,
            OCCURRENCE,
            artifacts=[],
            omissions=[],
            reporting_agent_id="agent",
            generate=lambda **_request: {"ok": False, "status": status, "error": status},
        )

    assert raised.value.code == f"reporting_agent_{status}"
    assert raised.value.recoverable is True


@pytest.mark.parametrize("reply", ["", "not json", json.dumps({**REPORT, "hiddenReasoning": "secret"})])
def test_generate_completion_report_rejects_empty_invalid_or_extra_agent_output(reply):
    with pytest.raises(CompletionReportGenerationError) as raised:
        generate_completion_report(
            PROJECT,
            OCCURRENCE,
            artifacts=[],
            omissions=[],
            reporting_agent_id="agent",
            generate=lambda **_request: {"ok": True, "status": "completed", "reply": reply},
        )

    assert raised.value.code in {"reporting_agent_empty_reply", "reporting_agent_invalid_output"}
    assert raised.value.recoverable is True


def test_generate_completion_report_bounds_agent_fields_and_list_sizes():
    oversized = {
        "goal": "g" * 5000,
        "conclusion": "c" * 5000,
        "keyResults": [str(index) * 1000 for index in range(20)],
        "nonFatalExceptions": [],
        "followUps": [],
        "importantArtifacts": [
            {"label": "l" * 1000, "path": "p" * 1000, "note": "n" * 2000}
            for _ in range(20)
        ],
    }

    result = generate_completion_report(
        PROJECT,
        OCCURRENCE,
        artifacts=[],
        omissions=[],
        reporting_agent_id="agent",
        generate=lambda **_request: {"ok": True, "status": "completed", "reply": json.dumps(oversized)},
    )["report"]

    assert len(result["goal"]) == 2000
    assert len(result["conclusion"]) == 4000
    assert len(result["keyResults"]) == 10
    assert all(len(item) <= 500 for item in result["keyResults"])
    assert len(result["importantArtifacts"]) == 10
    assert len(result["importantArtifacts"][0]["path"]) == 500
