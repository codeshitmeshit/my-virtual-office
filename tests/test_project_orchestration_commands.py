#!/usr/bin/env python3
"""Repository-backed project orchestration command tests."""

from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_orchestration import (
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
)
from services.project_orchestration_commands import autosave_orchestration
from services.project_repository import ProjectRepository


class MemoryStore:
    def __init__(self, project):
        self.data = {"projects": [copy.deepcopy(project)], "templates": []}
        self.saved = 0
        self.fail_saves = False

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        if self.fail_saves:
            raise OSError("save failed")
        self.saved += 1
        self.data = copy.deepcopy(value)


def _task(task_id, stage=1, state="backlog", **overrides):
    task = {
        "id": task_id,
        "title": task_id,
        "executionStage": stage,
        "stageRunId": None,
        "orchestrationSkip": default_skip_state(),
        "executionState": state,
        "updatedAt": "initial",
    }
    task.update(overrides)
    return task


def _project(*, state="draft", revision=0, tasks=None, marked=True):
    project = {
        "id": "project-1",
        "title": "Project",
        "updatedAt": "initial",
        "orchestration": {
            **default_orchestration_state(),
            "state": state,
            "revision": revision,
        },
        "tasks": tasks if tasks is not None else [
            _task("a", 1),
            _task("b", 2),
            _task("c", 3),
        ],
    }
    if marked:
        project["executionModel"] = EXECUTION_MODEL_STAGE_PIPELINE_V1
    return project


def _repo(project):
    store = MemoryStore(project)
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def test_autosave_persists_full_assignment_and_increments_revision_atomically():
    store, repo = _repo(_project())

    outcome = autosave_orchestration(
        "project-1",
        {
            "revision": 0,
            "assignments": [
                {"taskId": "a", "executionStage": 2},
                {"taskId": "b", "executionStage": 1},
                {"taskId": "c", "executionStage": 1},
            ],
        },
        repository=repo,
        now=lambda: "saved",
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["orchestration"]["revision"] == 1
    assert outcome.result.payload["assignments"] == [
        {"taskId": "a", "executionStage": 2},
        {"taskId": "b", "executionStage": 1},
        {"taskId": "c", "executionStage": 1},
    ]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["revision"] == 1
    assert [(task["id"], task["executionStage"], task["updatedAt"]) for task in saved["tasks"]] == [
        ("a", 2, "saved"),
        ("b", 1, "saved"),
        ("c", 1, "saved"),
    ]
    assert saved["updatedAt"] == "saved"


def test_autosave_normalizes_sparse_positive_stages():
    store, repo = _repo(_project())

    outcome = autosave_orchestration(
        "project-1",
        {
            "revision": 0,
            "assignments": [
                {"taskId": "a", "executionStage": 10},
                {"taskId": "b", "executionStage": 20},
                {"taskId": "c", "executionStage": 20},
            ],
        },
        repository=repo,
        now=lambda: "saved",
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["assignments"] == [
        {"taskId": "a", "executionStage": 1},
        {"taskId": "b", "executionStage": 2},
        {"taskId": "c", "executionStage": 2},
    ]
    assert [task["executionStage"] for task in store.data["projects"][0]["tasks"]] == [1, 2, 2]


def test_autosave_rejects_stale_revision_with_authoritative_state():
    project = _project(revision=3)
    before = copy.deepcopy(project)
    store, repo = _repo(project)

    outcome = autosave_orchestration(
        "project-1",
        {"revision": 2, "assignments": [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 1}, {"taskId": "c", "executionStage": 2}]},
        repository=repo,
        now=lambda: "saved",
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "orchestration_revision_conflict"
    assert outcome.result.payload["currentRevision"] == 3
    assert outcome.result.payload["assignments"] == [
        {"taskId": "a", "executionStage": 1},
        {"taskId": "b", "executionStage": 2},
        {"taskId": "c", "executionStage": 3},
    ]
    assert store.data["projects"][0] == before


def test_autosave_rejects_incomplete_unknown_duplicate_and_invalid_assignments():
    project = _project()
    cases = [
        (
            [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 2}],
            400,
            "incomplete_orchestration_assignment",
        ),
        (
            [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 2}, {"taskId": "missing", "executionStage": 3}],
            400,
            "incomplete_orchestration_assignment",
        ),
        (
            [{"taskId": "a", "executionStage": 1}, {"taskId": "a", "executionStage": 2}, {"taskId": "c", "executionStage": 3}],
            400,
            "duplicate_orchestration_assignment",
        ),
        (
            [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 0}, {"taskId": "c", "executionStage": 2}],
            400,
            "invalid_orchestration_assignment",
        ),
    ]

    for assignments, status, code in cases:
        store, repo = _repo(project)
        outcome = autosave_orchestration(
            "project-1",
            {"revision": 0, "assignments": assignments},
            repository=repo,
            now=lambda: "saved",
        )
        assert outcome.result.status == status
        assert outcome.result.payload["code"] == code
        assert store.data["projects"][0] == project


def test_autosave_rejects_unmarked_or_non_editable_projects():
    unmarked_store, unmarked_repo = _repo(_project(marked=False))
    unmarked = autosave_orchestration(
        "project-1",
        {"revision": 0, "assignments": [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 2}, {"taskId": "c", "executionStage": 3}]},
        repository=unmarked_repo,
        now=lambda: "saved",
    )
    assert unmarked.result.status == 400
    assert unmarked.result.payload["code"] == "missing_execution_model"
    assert unmarked_store.saved == 0

    running_store, running_repo = _repo(_project(state="running"))
    running = autosave_orchestration(
        "project-1",
        {"revision": 0, "assignments": [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 1}, {"taskId": "c", "executionStage": 2}]},
        repository=running_repo,
        now=lambda: "saved",
    )
    assert running.result.status == 409
    assert running.result.payload["code"] == "orchestration_not_editable"
    assert running.result.payload["orchestrationState"] == "running"
    assert running_store.data["projects"][0]["updatedAt"] == "initial"


def test_autosave_allows_paused_edits_but_locks_completed_stage_history():
    project = _project(
        state="paused",
        tasks=[
            _task("done", 1, state="done"),
            _task("next", 2),
            _task("later", 3),
        ],
    )
    store, repo = _repo(project)

    rejected = autosave_orchestration(
        "project-1",
        {"revision": 0, "assignments": [{"taskId": "done", "executionStage": 2}, {"taskId": "next", "executionStage": 2}, {"taskId": "later", "executionStage": 3}]},
        repository=repo,
        now=lambda: "saved",
    )
    assert rejected.result.status == 409
    assert rejected.result.payload["code"] == "completed_stage_locked"
    assert store.data["projects"][0] == project

    accepted = autosave_orchestration(
        "project-1",
        {"revision": 0, "assignments": [{"taskId": "done", "executionStage": 1}, {"taskId": "next", "executionStage": 5}, {"taskId": "later", "executionStage": 5}]},
        repository=repo,
        now=lambda: "saved",
    )
    assert accepted.result.status == 200
    assert accepted.result.payload["assignments"] == [
        {"taskId": "done", "executionStage": 1},
        {"taskId": "next", "executionStage": 2},
        {"taskId": "later", "executionStage": 2},
    ]


def test_autosave_paused_unfinished_tasks_normalize_after_last_completed_stage():
    project = _project(
        state="paused",
        tasks=[
            _task("done-1", 1, state="done", completedAt="done-at"),
            _task("done-2", 2, state="completed"),
            _task("next", 3),
            _task("later", 4),
        ],
    )
    store, repo = _repo(project)

    outcome = autosave_orchestration(
        "project-1",
        {
            "revision": 0,
            "assignments": [
                {"taskId": "done-1", "executionStage": 1},
                {"taskId": "done-2", "executionStage": 2},
                {"taskId": "next", "executionStage": 1},
                {"taskId": "later", "executionStage": 10},
            ],
        },
        repository=repo,
        now=lambda: "saved",
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["assignments"] == [
        {"taskId": "done-1", "executionStage": 1},
        {"taskId": "done-2", "executionStage": 2},
        {"taskId": "next", "executionStage": 3},
        {"taskId": "later", "executionStage": 4},
    ]
    assert [task["executionStage"] for task in store.data["projects"][0]["tasks"]] == [1, 2, 3, 4]


def test_autosave_missing_project_and_save_failure_do_not_leave_partial_state():
    project = _project()
    store, repo = _repo(project)

    missing = autosave_orchestration(
        "missing",
        {"revision": 0, "assignments": []},
        repository=repo,
        now=lambda: "saved",
    )
    assert missing.result.status == 404

    store.fail_saves = True
    try:
        autosave_orchestration(
            "project-1",
            {"revision": 0, "assignments": [{"taskId": "a", "executionStage": 2}, {"taskId": "b", "executionStage": 1}, {"taskId": "c", "executionStage": 1}]},
            repository=repo,
            now=lambda: "saved",
        )
    except OSError as exc:
        assert str(exc) == "save failed"
    else:
        raise AssertionError("expected save failure")
    assert store.data["projects"][0] == project
