#!/usr/bin/env python3
"""MarkdownProjectStore coverage for stage-pipeline orchestration fields."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_materialization import (
    materialize_columns,
    materialize_project_base,
    materialize_task_base,
)
from services.project_orchestration import EXECUTION_MODEL_STAGE_PIPELINE_V1


def _project(tasks=None):
    return {
        "id": "project-1",
        "title": "Orchestrated project",
        "description": "Stage pipeline persistence",
        "columns": [{"id": "todo", "title": "Todo"}],
        "tasks": tasks or [],
        "activity": [],
    }


def _task(task_id, stage, *, skip=None, stage_run_id=None):
    return {
        "id": task_id,
        "title": f"Task {task_id}",
        "columnId": "todo",
        "executionStage": stage,
        "stageRunId": stage_run_id,
        "orchestrationSkip": skip or {
            "status": "none",
            "requestedBy": None,
            "requestedAt": None,
            "reason": None,
            "decidedBy": None,
            "decidedAt": None,
        },
    }


def _project_file(store):
    entry = next(iter(os.listdir(store.projects_dir)))
    return os.path.join(store.projects_dir, entry, "project.md")


def _task_file(store):
    entry = next(iter(os.listdir(store.projects_dir)))
    tasks_dir = os.path.join(store.projects_dir, entry, "tasks")
    return os.path.join(tasks_dir, next(name for name in os.listdir(tasks_dir) if name.endswith(".md")))


def test_stage_pipeline_project_and_task_fields_round_trip(tmp_path):
    orchestration = {
        "schemaVersion": 1,
        "revision": 7,
        "state": "running",
        "currentStage": 2,
        "currentRunId": "run-123",
        "pauseReason": None,
        "startedAt": "2026-07-27T08:00:00+00:00",
        "completedAt": None,
    }
    approved_skip = {
        "status": "approved",
        "requestedBy": {"type": "agent", "id": "builder"},
        "requestedAt": "2026-07-27T08:01:00+00:00",
        "reason": "external blocker accepted",
        "decidedBy": {"type": "user", "id": "owner"},
        "decidedAt": "2026-07-27T08:02:00+00:00",
    }
    project = _project(tasks=[
        _task("task-1", 1, stage_run_id="run-111"),
        _task("task-2", 2, skip=approved_skip, stage_run_id="run-123"),
    ])
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": orchestration,
    })
    store = MarkdownProjectStore(str(tmp_path))

    store.save_all({"projects": [project], "templates": []})
    loaded = MarkdownProjectStore(str(tmp_path)).load_all()["projects"][0]

    assert loaded["executionModel"] == EXECUTION_MODEL_STAGE_PIPELINE_V1
    assert loaded["orchestration"] == orchestration
    tasks = {task["id"]: task for task in loaded["tasks"]}
    assert tasks["task-1"]["executionStage"] == 1
    assert tasks["task-1"]["stageRunId"] == "run-111"
    assert tasks["task-1"]["orchestrationSkip"]["status"] == "none"
    assert tasks["task-2"]["executionStage"] == 2
    assert tasks["task-2"]["stageRunId"] == "run-123"
    assert tasks["task-2"]["orchestrationSkip"] == approved_skip

    project_frontmatter = open(_project_file(store), encoding="utf-8").read()
    task_frontmatter = open(_task_file(store), encoding="utf-8").read()
    assert f"executionModel: {EXECUTION_MODEL_STAGE_PIPELINE_V1}" in project_frontmatter
    assert "orchestration_json:" in project_frontmatter
    assert "executionStage:" in task_frontmatter
    assert "stageRunId:" in task_frontmatter
    assert "orchestrationSkip_json:" in task_frontmatter


def test_task_final_result_metadata_and_markdown_sidecar_round_trip(tmp_path):
    project = _project(tasks=[
        {
            **_task("task-1", 1, stage_run_id="run-1"),
            "executionState": "done",
            "completedAt": "done-at",
            "evidence": {
                "attemptId": "attempt-1",
                "executorSummary": "Verified the final output.",
                "changedFiles": ["docs/result.md"],
                "testResults": ["pytest passed"],
            },
            "finalResult": {
                "schemaVersion": 1,
                "status": "available",
                "summary": "Verified the final output.",
                "sourceAttemptId": "attempt-1",
                "executionStage": 1,
                "generatedAt": "done-at",
                "artifactRefs": [{"kind": "file", "path": "docs/result.md"}],
            },
        }
    ])
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {"schemaVersion": 1, "revision": 1, "state": "completed"},
    })
    store = MarkdownProjectStore(str(tmp_path))

    store.save_all({"projects": [project], "templates": []})
    loaded = MarkdownProjectStore(str(tmp_path)).load_all()["projects"][0]

    task = loaded["tasks"][0]
    assert task["finalResult"]["status"] == "available"
    assert task["finalResult"]["markdownPath"].endswith("/TASK_FINAL_RESULT.md")
    sidecar = tmp_path / task["finalResult"]["markdownPath"]
    assert sidecar.exists()
    sidecar_text = sidecar.read_text(encoding="utf-8")
    assert sidecar_text.startswith("# TASK_FINAL_RESULT")
    assert "Verified the final output." in sidecar_text
    assert "docs/result.md" in sidecar_text


def test_stage_handoff_markdown_path_is_backfilled_from_task_final_result(tmp_path):
    task = {
        **_task("task-1", 1, stage_run_id="run-1"),
        "executionState": "done",
        "completedAt": "done-at",
        "finalResult": {
            "schemaVersion": 1,
            "status": "available",
            "summary": "Stage output ready.",
            "sourceAttemptId": "attempt-1",
            "executionStage": 1,
            "generatedAt": "done-at",
            "artifactRefs": [],
        },
    }
    project = _project(tasks=[task])
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            "schemaVersion": 1,
            "revision": 2,
            "state": "completed",
            "stageHandoffs": {
                "1": {
                    "schemaVersion": 1,
                    "stage": 1,
                    "generatedAt": "done-at",
                    "tasks": [{
                        "taskId": "task-1",
                        "title": "Task task-1",
                        "stage": 1,
                        "status": "available",
                        "summary": "Stage output ready.",
                        "markdownPath": "",
                        "sourceAttemptId": "attempt-1",
                        "artifactRefs": [],
                    }],
                },
            },
        },
    })
    store = MarkdownProjectStore(str(tmp_path))

    store.save_all({"projects": [project], "templates": []})
    loaded = MarkdownProjectStore(str(tmp_path)).load_all()["projects"][0]

    handoff_path = loaded["orchestration"]["stageHandoffs"]["1"]["tasks"][0]["markdownPath"]
    task_path = loaded["tasks"][0]["finalResult"]["markdownPath"]
    assert handoff_path == task_path
    assert handoff_path.endswith("/TASK_FINAL_RESULT.md")


def test_malformed_orchestration_frontmatter_is_repaired_to_safe_empty_objects(tmp_path):
    project = _project(tasks=[_task("task-1", 1)])
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {"schemaVersion": 1, "revision": 1, "state": "draft"},
    })
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [project], "templates": []})

    project_path = _project_file(store)
    project_text = open(project_path, encoding="utf-8").read()
    project_text = project_text.replace(
        'orchestration_json: {"schemaVersion":1,"revision":1,"state":"draft"}',
        'orchestration_json: {"schemaVersion":',
    )
    open(project_path, "w", encoding="utf-8").write(project_text)

    task_path = _task_file(store)
    task_text = open(task_path, encoding="utf-8").read()
    task_text = task_text.replace("executionStage: 1", "executionStage: invalid")
    task_text = task_text.replace(
        'orchestrationSkip_json: {"status":"none","requestedBy":null,"requestedAt":null,"reason":null,"decidedBy":null,"decidedAt":null}',
        'orchestrationSkip_json: {"status":',
    )
    open(task_path, "w", encoding="utf-8").write(task_text)

    loaded = MarkdownProjectStore(str(tmp_path)).load_all()["projects"][0]
    task = loaded["tasks"][0]

    assert loaded["executionModel"] == EXECUTION_MODEL_STAGE_PIPELINE_V1
    assert loaded["orchestration"] == {}
    assert task["executionStage"] is None
    assert task["orchestrationSkip"] == {}


def test_canonical_materialized_projects_do_not_write_legacy_progression_authorities(tmp_path):
    columns, _ = materialize_columns(None, new_id=iter(["c1", "c2", "c3", "c4"]).__next__)
    task = materialize_task_base(
        {"title": "Stage task"},
        columns=columns,
        task_id="task-1",
        timestamp="2026-07-27T08:00:00+00:00",
        new_id=lambda: "unused-task",
        now=lambda: "unused-now",
    )
    project = materialize_project_base(
        {"title": "Stage project"},
        columns=columns,
        tasks=[task],
        workspace=None,
        project_id="project-1",
        timestamp="2026-07-27T08:00:00+00:00",
        new_id=lambda: "unused-project",
        now=lambda: "unused-now",
    )
    store = MarkdownProjectStore(str(tmp_path))

    store.save_all({"projects": [project], "templates": []})

    project_frontmatter = open(_project_file(store), encoding="utf-8").read()
    task_frontmatter = open(_task_file(store), encoding="utf-8").read()
    assert f"executionModel: {EXECUTION_MODEL_STAGE_PIPELINE_V1}" in project_frontmatter
    assert "orchestration_json:" in project_frontmatter
    assert "executionStage: 1" in task_frontmatter
    assert "orchestrationSkip_json:" in task_frontmatter
    for legacy in (
        "projectExecutionStartMode:",
        "projectExecutionFlowActive:",
        "projectExecutionFlowStopReason:",
        "executionPolicy_json:",
        "workflowActive:",
        "workflowPhase:",
        "activeTaskId:",
        "activeAgent:",
        "autoMode:",
    ):
        assert legacy not in project_frontmatter
    assert "executionOrder:" not in task_frontmatter


def test_marked_project_save_and_reload_strips_legacy_authorities_even_if_present(tmp_path):
    project = _project(tasks=[
        {
            **_task("task-1", 1, stage_run_id="run-1"),
            "executionOrder": 9,
            "executionState": "executing",
            "activeAttemptId": "attempt-1",
        }
    ])
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            "schemaVersion": 1,
            "revision": 3,
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
            "pauseReason": None,
        },
        "projectExecutionStartMode": "single",
        "projectExecutionFlowActive": True,
        "projectExecutionFlowStopReason": "legacy_stop",
        "executionPolicy": {"maxActiveTasks": 1},
        "workflowActive": True,
        "workflowPhase": "executing",
        "activeTaskId": "task-1",
        "activeAgent": "legacy-agent",
        "autoMode": True,
    })
    store = MarkdownProjectStore(str(tmp_path))

    store.save_all({"projects": [project], "templates": []})
    loaded = MarkdownProjectStore(str(tmp_path)).load_all()["projects"][0]

    for legacy in (
        "projectExecutionStartMode",
        "projectExecutionFlowActive",
        "projectExecutionFlowStopReason",
        "executionPolicy",
        "workflowActive",
        "workflowPhase",
        "activeTaskId",
        "activeAgent",
        "autoMode",
    ):
        assert legacy not in loaded
    assert loaded["executionModel"] == EXECUTION_MODEL_STAGE_PIPELINE_V1
    assert loaded["orchestration"]["state"] == "running"
    assert loaded["tasks"][0]["executionStage"] == 1
    assert "executionOrder" not in loaded["tasks"][0]

    project_frontmatter = open(_project_file(store), encoding="utf-8").read()
    task_frontmatter = open(_task_file(store), encoding="utf-8").read()
    for legacy in (
        "projectExecutionStartMode:",
        "projectExecutionFlowActive:",
        "projectExecutionFlowStopReason:",
        "executionPolicy_json:",
        "workflowActive:",
        "workflowPhase:",
        "activeTaskId:",
        "activeAgent:",
        "autoMode:",
    ):
        assert legacy not in project_frontmatter
    assert "executionOrder:" not in task_frontmatter


def test_marked_project_reload_ignores_legacy_frontmatter_pollution(tmp_path):
    project = _project(tasks=[_task("task-1", 1, stage_run_id="run-1")])
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            "schemaVersion": 1,
            "revision": 3,
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
            "pauseReason": None,
        },
    })
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [project], "templates": []})

    project_path = _project_file(store)
    project_text = open(project_path, encoding="utf-8").read()
    project_text = project_text.replace(
        "executionModel: stage_pipeline_v1\n",
        "executionModel: stage_pipeline_v1\n"
        "projectExecutionStartMode: single\n"
        "projectExecutionFlowActive: true\n"
        "projectExecutionFlowStopReason: legacy_stop\n"
        "executionPolicy_json: {\"maxActiveTasks\":1}\n"
        "workflowActive: true\n"
        "workflowPhase: executing\n"
        "activeTaskId: task-1\n"
        "activeAgent: legacy-agent\n"
        "autoMode: true\n",
    )
    open(project_path, "w", encoding="utf-8").write(project_text)

    task_path = _task_file(store)
    task_text = open(task_path, encoding="utf-8").read()
    task_text = task_text.replace("executionStage: 1\n", "executionStage: 1\nexecutionOrder: 7\n")
    open(task_path, "w", encoding="utf-8").write(task_text)

    loaded = MarkdownProjectStore(str(tmp_path)).load_all()["projects"][0]

    for legacy in (
        "projectExecutionStartMode",
        "projectExecutionFlowActive",
        "projectExecutionFlowStopReason",
        "executionPolicy",
        "workflowActive",
        "workflowPhase",
        "activeTaskId",
        "activeAgent",
        "autoMode",
    ):
        assert legacy not in loaded
    assert "executionOrder" not in loaded["tasks"][0]
    assert loaded["executionModel"] == EXECUTION_MODEL_STAGE_PIPELINE_V1
    assert loaded["tasks"][0]["executionStage"] == 1
