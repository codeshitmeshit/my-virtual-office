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
    "title": "Release conclusion",
    "summary": "Release completed successfully.",
    "conclusions": ["Package published", "Smoke tests passed"],
    "organizationalAdvice": ["Reuse the release playbook across teams"],
}
ARTIFACTS = [{
    "path": "release/notes.md",
    "kind": "markdown",
    "inline": True,
    "content": "# Release result\nThe package is published.",
}]
CONCLUSION_REPORT = {
    "title": "张雪机车分析结论",
    "summary": "张雪机车正从话题品牌向性能品牌跃迁。",
    "conclusions": [
        "赛事成绩为品牌提供了性能背书。",
        "长期价值取决于量产质量和售后能力。",
    ],
    "organizationalAdvice": [
        "把赛事能力沉淀为可复用的产品验证与品牌资产。",
    ],
}


def test_generate_completion_report_outputs_only_final_content_conclusions():
    result = generate_completion_report(
        {"id": "project-1", "title": "张雪机车的分析"},
        OCCURRENCE,
        artifacts=ARTIFACTS,
        omissions=[],
        reporting_agent_id="agent",
        generate=lambda **_request: {
            "ok": True,
            "status": "completed",
            "reply": json.dumps(CONCLUSION_REPORT, ensure_ascii=False),
        },
    )

    assert result["report"] == CONCLUSION_REPORT
    assert result["markdown"] == (
        "# 张雪机车分析结论\n\n"
        "张雪机车正从话题品牌向性能品牌跃迁。\n\n"
        "## 核心结论\n"
        "- 赛事成绩为品牌提供了性能背书。\n"
        "- 长期价值取决于量产质量和售后能力。\n\n"
        "---\n\n"
        "- 把赛事能力沉淀为可复用的产品验证与品牌资产。\n"
    )
    for lifecycle_label in ("Execution", "Goal", "Exceptions", "Follow-ups", "Artifacts"):
        assert lifecycle_label not in result["markdown"]


def test_generate_completion_report_validates_reply_and_renders_content_markdown():
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
    assert result["markdown"] == (
        "# Release conclusion\n\n"
        "Release completed successfully.\n\n"
        "## 核心结论\n"
        "- Package published\n"
        "- Smoke tests passed\n\n"
        "---\n\n"
        "- Reuse the release playbook across teams\n"
    )


def test_generate_completion_report_rejects_missing_agent_without_calling_provider():
    with pytest.raises(CompletionReportGenerationError) as raised:
        generate_completion_report(
            PROJECT,
            OCCURRENCE,
            artifacts=ARTIFACTS,
            omissions=[],
            reporting_agent_id="",
            generate=lambda **_request: (_ for _ in ()).throw(AssertionError("provider called")),
        )

    assert raised.value.code == "reporting_agent_missing"
    assert raised.value.recoverable is False


def test_generate_completion_report_rejects_missing_final_artifact_content():
    with pytest.raises(CompletionReportGenerationError) as raised:
        generate_completion_report(
            PROJECT,
            OCCURRENCE,
            artifacts=[{
                "path": "release/final.pdf",
                "kind": "reference",
                "inline": False,
                "content": "",
            }],
            omissions=[],
            reporting_agent_id="agent",
            generate=lambda **_request: {"ok": True, "reply": json.dumps(REPORT)},
        )

    assert raised.value.code == "final_report_content_missing"
    assert raised.value.recoverable is False


@pytest.mark.parametrize("status", ["busy", "timeout"])
def test_generate_completion_report_classifies_transient_provider_failures(status):
    with pytest.raises(CompletionReportGenerationError) as raised:
        generate_completion_report(
            PROJECT,
            OCCURRENCE,
            artifacts=ARTIFACTS,
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
            artifacts=ARTIFACTS,
            omissions=[],
            reporting_agent_id="agent",
            generate=lambda **_request: {"ok": True, "status": "completed", "reply": reply},
        )

    assert raised.value.code in {"reporting_agent_empty_reply", "reporting_agent_invalid_output"}
    assert raised.value.recoverable is True


def test_generate_completion_report_bounds_agent_fields_and_list_sizes():
    oversized = {
        "title": "t" * 1000,
        "summary": "s" * 10000,
        "conclusions": [str(index) * 1000 for index in range(20)],
        "organizationalAdvice": [str(index) * 1000 for index in range(20)],
    }

    result = generate_completion_report(
        PROJECT,
        OCCURRENCE,
        artifacts=ARTIFACTS,
        omissions=[],
        reporting_agent_id="agent",
        generate=lambda **_request: {"ok": True, "status": "completed", "reply": json.dumps(oversized)},
    )["report"]

    assert len(result["title"]) == 300
    assert len(result["summary"]) == 5000
    assert len(result["conclusions"]) == 10
    assert all(len(item) <= 500 for item in result["conclusions"])
    assert len(result["organizationalAdvice"]) == 10
    assert all(len(item) <= 500 for item in result["organizationalAdvice"])
