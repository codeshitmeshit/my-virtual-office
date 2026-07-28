#!/usr/bin/env python3
"""Focused coverage for task final-result artifacts and prompt handoffs."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.project_task_final_result import (  # noqa: E402
    FINAL_RESULT_FILENAME,
    ensure_task_final_result,
    prior_stage_result_prompt_block,
    record_stage_handoff,
    render_task_final_result_markdown,
    task_final_result_prompt_instructions,
)


def test_task_final_result_index_and_markdown_are_generated_from_evidence():
    project = {"id": "project-1", "title": "Launch"}
    task = {
        "id": "task-1",
        "title": "Build report",
        "executionStage": 2,
        "evidence": {
            "attemptId": "attempt-1",
            "executorSummary": "Built the report and verified the output.",
            "changedFiles": ["reports/final.md"],
            "testResults": ["pytest passed"],
            "checklist": [{"id": "deliverable", "text": "Report exists", "done": True}],
        },
    }

    final_result = ensure_task_final_result(project, task, now="now")
    markdown = render_task_final_result_markdown(project, task)

    assert final_result["status"] == "available"
    assert final_result["summary"] == "Built the report and verified the output."
    assert final_result["sourceAttemptId"] == "attempt-1"
    assert final_result["artifactRefs"] == [{"kind": "file", "path": "reports/final.md"}]
    assert markdown.startswith("# TASK_FINAL_RESULT")
    assert "## Final Conclusion" in markdown
    assert "pytest passed" in markdown
    assert FINAL_RESULT_FILENAME in task_final_result_prompt_instructions()


def test_prior_stage_prompt_uses_compact_indexes_not_full_result_bodies():
    project = {
        "id": "project-1",
        "title": "Launch",
        "orchestration": {},
        "tasks": [
            {
                "id": "stage-1-task",
                "title": "Collect facts",
                "executionStage": 1,
                "finalResult": {
                    "status": "available",
                    "summary": "Collected the facts.",
                    "markdownPath": "projects-md/project/tasks/collect/TASK_FINAL_RESULT.md",
                    "sourceAttemptId": "attempt-1",
                    "artifactRefs": [{"kind": "file", "path": "facts.md"}],
                },
            },
            {"id": "stage-2-task", "title": "Use facts", "executionStage": 2},
        ],
    }
    record_stage_handoff(project, 1, generated_at="now")

    block = prior_stage_result_prompt_block(project, project["tasks"][1])

    assert "PRIOR STAGE RESULT INDEX" in block
    assert "Collect facts" in block
    assert "projects-md/project/tasks/collect/TASK_FINAL_RESULT.md" in block
    assert "Collected the facts." in block
