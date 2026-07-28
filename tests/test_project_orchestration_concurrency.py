#!/usr/bin/env python3
"""Deterministic concurrency regressions for marked project orchestration."""

from __future__ import annotations

import copy
import os
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-orchestration-concurrency-test-"))

from services.project_orchestration import (  # noqa: E402
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
)
from services.project_orchestration_commands import autosave_orchestration  # noqa: E402
from services.project_orchestration_pause import PauseCancellationPorts, PausePorts, complete_phase_two_pause, request_phase_one_pause  # noqa: E402
from services.project_orchestration_recovery import RecoveryPorts, recover_marked_projects  # noqa: E402
from services.project_orchestration_skip import SkipPorts, decide_task_skip  # noqa: E402
from services.project_repository import ProjectRepository  # noqa: E402
from services.project_stage_dispatch import (  # noqa: E402
    BoundedProjectExecutionDispatcher,
    reconcile_stage,
    start_marked_project,
)


class MemoryStore:
    def __init__(self, project):
        self.data = {"projects": [copy.deepcopy(project)], "templates": []}
        self.save_calls = 0

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.save_calls += 1
        self.data = copy.deepcopy(value)


class PreflightPorts:
    def __init__(self):
        self.run_ids = ["run-1", "run-duplicate", "run-2", "run-3"]

    def validate_workspace(self, _path):
        return {"ok": True, "path": "/work/project", "kind": "local"}

    def git_snapshot(self, _path):
        return {"ok": True, "dirty": False, "files": [], "fingerprint": "", "truncated": False}

    def resolve_roles(self, _project, _task, _allow_skip_reviewer):
        return {"ok": True, "executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}}

    def authorize(self, _project, _actor):
        return {"ok": True}

    def now(self):
        return "now"

    def new_run_id(self):
        return self.run_ids.pop(0)


class AttemptPorts:
    def __init__(self):
        self.attempt_ids = [f"attempt-{index}" for index in range(1, 12)]
        self.transitions = []

    def now(self):
        return "now"

    def new_attempt_id(self):
        return self.attempt_ids.pop(0)

    def requires_acceptance(self, task):
        return bool(task.get("requiresUserAcceptance"))

    def seed_checklist(self, task, _actor):
        task.setdefault("checklist", [{"id": "main", "text": "Do work", "done": False}])
        return True

    def has_pending_meeting_actions(self, _task):
        return False

    def transition(self, project, task, next_state, actor, reason, attempt_id):
        self.transitions.append((project.get("id"), task.get("id"), next_state, actor, reason, attempt_id))
        task["executionState"] = next_state


class SkipDecisionPorts:
    def __init__(self):
        self.run_ids = ["run-skip-next"]

    def now(self):
        return "now"

    def management_authorize(self, _project, _actor):
        return {"ok": True}

    def new_run_id(self):
        return self.run_ids.pop(0)


class RecoveryHarnessPorts:
    def __init__(self, repository, *, live_attempts=None):
        self.repository = repository
        self.live_attempts = set(live_attempts or ())
        self.next_attempt = 1
        self.prepared = []
        self.submitted = []
        self.reconciled = []

    def now(self):
        return "recovered-at"

    def is_live_attempt(self, attempt_id):
        return attempt_id in self.live_attempts

    def prepare_reserved_task(self, project_id, task_id, run_id):
        attempt_id = f"recovered-attempt-{self.next_attempt}"
        self.next_attempt += 1

        def mutate(project):
            task = next(item for item in project["tasks"] if item["id"] == task_id)
            task.setdefault("attempts", []).append({"id": attempt_id, "status": "executing", "stageRunId": run_id})
            task["activeAttemptId"] = attempt_id
            task["executionState"] = "executing"
            project["orchestration"]["state"] = "running"

        self.repository.update(project_id, mutate)
        self.prepared.append((project_id, task_id, run_id, attempt_id))
        return {"ok": True, "attemptId": attempt_id, "runId": run_id}

    def submit_reserved_task(self, project_id, task_id, run_id, attempt_id):
        self.live_attempts.add(attempt_id)
        self.submitted.append((project_id, task_id, run_id, attempt_id))
        return {"ok": True, "accepted": True}

    def reconcile_stage_run(self, project_id, run_id):
        self.reconciled.append((project_id, run_id))
        return {"ok": True, "status": "stage_waiting", "runId": run_id}

    def complete_pausing_project(self, _project_id):
        return {"ok": True, "status": "paused"}

    def transition(self, _project, task, next_state, _actor, _reason, _attempt_id):
        task["executionState"] = next_state

    def ports(self):
        return RecoveryPorts(
            now=self.now,
            is_live_attempt=self.is_live_attempt,
            prepare_reserved_task=self.prepare_reserved_task,
            submit_reserved_task=self.submit_reserved_task,
            reconcile_stage_run=self.reconcile_stage_run,
            complete_pausing_project=self.complete_pausing_project,
            transition=self.transition,
        )


def task(task_id, stage, **overrides):
    value = {
        "id": task_id,
        "title": task_id,
        "executionStage": stage,
        "stageRunId": None,
        "orchestrationSkip": default_skip_state(),
        "executionState": "pending",
        "attempts": [],
        "activeAttemptId": None,
        "executorAgentId": "executor",
        "reviewerAgentId": "reviewer",
    }
    value.update(overrides)
    return value


def project(*, state="draft", current_stage=None, current_run_id=None, revision=0, tasks=None):
    return {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": state,
            "currentStage": current_stage,
            "currentRunId": current_run_id,
            "revision": revision,
        },
        "projectExecutionEnabled": True,
        "workspacePath": "/work/project",
        "tasks": tasks if tasks is not None else [task("a", 1), task("b", 1), task("c", 2)],
    }


def repo_for(project_data):
    store = MemoryStore(project_data)
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def test_duplicate_project_start_serializes_to_one_stage_reservation():
    store, repository = repo_for(project())
    preflight = PreflightPorts()
    attempts = AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(lambda _item: None, worker_count=1, queue_capacity=8, autostart=False)
    results = []
    lock = threading.Lock()

    def worker():
        outcome = start_marked_project(
            "project-1",
            {"actor": {"type": "management", "id": "manager"}},
            repository=repository,
            preflight_ports=preflight,
            attempt_ports=attempts,
            dispatcher=dispatcher,
            create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
        )
        with lock:
            results.append((outcome.result.status, outcome.result.payload.get("status"), outcome.result.payload.get("code")))

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for item in threads:
        item.start()
    for item in threads:
        item.join()

    assert sorted(results) == [(200, "stage_started", None), (409, None, "orchestration_not_startable")]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert [item["stageRunId"] for item in saved["tasks"][:2]] == ["run-1", "run-1"]
    assert dispatcher.diagnostics()["accepted"] == 2


def test_duplicate_terminal_and_parallel_completion_callbacks_advance_once():
    project_data = project(
        state="running",
        current_stage=1,
        current_run_id="run-1",
        tasks=[
            task("a", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
            task("b", 1, stageRunId="run-1", executionState="completed"),
            task("c", 2),
        ],
    )
    store, repository = repo_for(project_data)
    run_ids = iter(["run-2", "run-duplicate"])
    results = []
    lock = threading.Lock()

    def worker():
        outcome = reconcile_stage(
            "project-1",
            "run-1",
            repository=repository,
            now=lambda: "now",
            new_run_id=lambda: next(run_ids),
        )
        with lock:
            results.append(outcome.result.payload["status"])

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for item in threads:
        item.start()
    for item in threads:
        item.join()
    duplicate = reconcile_stage("project-1", "run-1", repository=repository, now=lambda: "later", new_run_id=lambda: "run-late")

    assert sorted(results) == ["stage_advanced", "stale_run_ignored"]
    assert duplicate.result.payload["status"] == "stale_run_ignored"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentRunId"] == "run-2"
    assert saved["tasks"][2]["stageRunId"] == "run-2"


def test_completion_versus_pause_never_starts_later_stage_after_pause_wins():
    project_data = project(
        state="running",
        current_stage=1,
        current_run_id="run-1",
        tasks=[
            task("a", 1, stageRunId="run-1", executionState="done", completedAt="done-at", activeAttemptId="attempt-a"),
            task("b", 1, stageRunId="run-1", executionState="completed", activeAttemptId="attempt-b"),
            task("c", 2),
        ],
    )
    store, repository = repo_for(project_data)
    pause = request_phase_one_pause(
        "project-1",
        {"confirmed": True, "reason": "rebalance", "actor": {"type": "management", "id": "manager"}},
        repository=repository,
        ports=PausePorts(now=lambda: "paused-at", authorize=lambda _project, _actor: {"ok": True}),
    )
    completion = reconcile_stage("project-1", "run-1", repository=repository, now=lambda: "now", new_run_id=lambda: "run-2")
    converged = complete_phase_two_pause(
        "project-1",
        repository=repository,
        ports=PauseCancellationPorts(
            now=lambda: "converged-at",
            cancel_attempt=lambda _payload: {"ok": True, "status": "cancelled"},
            transition=lambda _project, task, next_state, _actor, _reason, _attempt_id: task.update({"executionState": next_state}),
        ),
    )

    assert pause.result.payload["status"] == "pausing"
    assert completion.result.payload["status"] == "stage_pausing"
    assert converged.result.payload["status"] == "paused"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "paused"
    assert saved["orchestration"]["currentRunId"] is None
    assert saved["tasks"][2]["stageRunId"] is None


def test_skip_approval_versus_completion_reconciles_current_stage_once():
    project_data = project(
        state="running",
        current_stage=1,
        current_run_id="run-1",
        tasks=[
            task(
                "a",
                1,
                stageRunId="run-1",
                orchestrationSkip={
                    **default_skip_state(),
                    "status": "requested",
                    "requestedBy": {"type": "agent", "id": "executor"},
                    "requestedAt": "earlier",
                },
            ),
            task("b", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
            task("c", 2),
        ],
    )
    store, repository = repo_for(project_data)
    skip_result = decide_task_skip(
        "project-1",
        "a",
        {"decision": "approve", "actor": {"type": "management", "id": "manager"}},
        repository=repository,
        ports=SkipPorts(
            now=lambda: "now",
            management_authorize=lambda _project, _actor: {"ok": True},
            new_run_id=lambda: "run-2",
            on_project_completed=None,
        ),
    )
    completion = reconcile_stage("project-1", "run-1", repository=repository, now=lambda: "later", new_run_id=lambda: "run-duplicate")

    assert skip_result.result.payload["reconciliation"]["status"] == "stage_advanced"
    assert completion.result.payload["status"] == "stale_run_ignored"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentRunId"] == "run-2"
    assert saved["tasks"][2]["stageRunId"] == "run-2"


def test_stale_autosave_loses_to_current_revision_without_mutation():
    project_data = project(state="paused", revision=5)
    before = copy.deepcopy(project_data)
    store, repository = repo_for(project_data)

    outcome = autosave_orchestration(
        "project-1",
        {
            "revision": 4,
            "assignments": [
                {"taskId": "a", "executionStage": 2},
                {"taskId": "b", "executionStage": 1},
                {"taskId": "c", "executionStage": 1},
            ],
        },
        repository=repository,
        now=lambda: "saved",
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "orchestration_revision_conflict"
    assert outcome.result.payload["currentRevision"] == 5
    assert store.data["projects"][0] == before


def test_recovery_versus_live_execution_preserves_live_attempt_and_reconciles_once():
    project_data = project(
        state="running",
        current_stage=1,
        current_run_id="run-1",
        tasks=[
            task(
                "a",
                1,
                stageRunId="run-1",
                executionState="executing",
                activeAttemptId="attempt-a",
                attempts=[{"id": "attempt-a", "status": "executing", "stageRunId": "run-1"}],
            ),
            task("b", 1, stageRunId="run-1"),
        ],
    )
    _store, repository = repo_for(project_data)
    ports = RecoveryHarnessPorts(repository, live_attempts={"attempt-a"})
    reports = []
    lock = threading.Lock()

    def worker():
        report = recover_marked_projects(repository=repository, ports=ports.ports())
        with lock:
            reports.extend(item.status for item in report.projects)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for item in threads:
        item.start()
    for item in threads:
        item.join()

    assert reports.count("resubmitted") == 1
    assert reports.count("preserved") == 1
    assert ports.prepared == [("project-1", "b", "run-1", "recovered-attempt-1")]
    assert ports.submitted == [("project-1", "b", "run-1", "recovered-attempt-1")]
    saved = repository.get("project-1")
    assert saved["tasks"][0]["activeAttemptId"] == "attempt-a"
    assert saved["tasks"][1]["activeAttemptId"] == "recovered-attempt-1"
