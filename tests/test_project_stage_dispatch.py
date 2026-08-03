#!/usr/bin/env python3
"""Tests for bounded project stage dispatch infrastructure."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-stage-dispatch-test-"))

from services.project_stage_dispatch import (
    DEFAULT_STAGE_DISPATCH_QUEUE_CAPACITY,
    DEFAULT_STAGE_DISPATCH_WORKERS,
    QUEUE_FULL_CODE,
    BoundedProjectExecutionDispatcher,
    prepare_reserved_task_attempt,
    reconcile_stage,
    reserve_stage_run,
    resume_paused_project,
    start_marked_project,
    submit_reserved_stage,
)
from services.project_orchestration import (
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
)
from services.project_repository import ProjectRepository


class _MemoryStore:
    def __init__(self, project):
        import copy

        self.data = {"projects": [copy.deepcopy(project)], "templates": []}
        self.save_calls = 0

    def load(self):
        import copy

        return copy.deepcopy(self.data)

    def save(self, value):
        import copy

        self.save_calls += 1
        self.data = copy.deepcopy(value)


class _Ports:
    def __init__(self, *, authorize=None, workspace=None, git_state=None, roles=None):
        self.authorize_result = authorize or {"ok": True}
        self.workspace = workspace or {"ok": True, "path": "/work/project", "kind": "local"}
        self.git_state = git_state or {"ok": True, "dirty": False, "files": [], "fingerprint": "", "truncated": False}
        self.roles = roles or {"ok": True, "executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}}
        self.workspace_calls = []
        self.git_calls = []
        self.role_calls = []
        self.authorize_calls = []
        self.run_ids = ["run-1"]

    def validate_workspace(self, path):
        self.workspace_calls.append(path)
        return dict(self.workspace)

    def git_snapshot(self, path):
        self.git_calls.append(path)
        return dict(self.git_state)

    def resolve_roles(self, project, task, allow_skip_reviewer):
        self.role_calls.append((project.get("id"), task.get("id"), allow_skip_reviewer))
        if callable(self.roles):
            return self.roles(project, task, allow_skip_reviewer)
        return dict(self.roles)

    def authorize(self, project, actor):
        self.authorize_calls.append((project.get("id"), dict(actor)))
        if callable(self.authorize_result):
            return self.authorize_result(project, actor)
        return dict(self.authorize_result)

    def now(self):
        return "now"

    def new_run_id(self):
        return self.run_ids.pop(0)


class _AttemptPorts:
    def __init__(self):
        self.attempt_ids = ["attempt-1", "attempt-2", "attempt-3"]
        self.seeded = []
        self.transitions = []
        self.pending_meeting_tasks = set()

    def now(self):
        return "now"

    def new_attempt_id(self):
        return self.attempt_ids.pop(0)

    def requires_acceptance(self, task):
        return bool(task.get("requiresUserAcceptance"))

    def seed_checklist(self, task, actor):
        self.seeded.append((task.get("id"), actor))
        task.setdefault("checklist", [{"id": "main", "text": "Do work", "done": False}])
        return True

    def has_pending_meeting_actions(self, task):
        return task.get("id") in self.pending_meeting_tasks

    def transition(self, project, task, next_state, actor, reason, attempt_id):
        self.transitions.append((project.get("id"), task.get("id"), next_state, actor, reason, attempt_id))
        task["executionState"] = next_state
        task.setdefault("stateHistory", []).append({
            "state": next_state,
            "actor": actor,
            "reason": reason,
            "attemptId": attempt_id,
        })


def _task(task_id, stage, **overrides):
    task = {
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
    task.update(overrides)
    return task


def _project(**overrides):
    project = {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": default_orchestration_state(),
        "projectExecutionEnabled": True,
        "workspacePath": "/work/project",
        "tasks": [_task("a", 1), _task("b", 1), _task("c", 2)],
    }
    project.update(overrides)
    return project


def _repo(project):
    store = _MemoryStore(project)
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def test_dispatcher_defaults_to_eight_workers_and_authored_task_queue_capacity():
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: item.task_id)
    try:
        diagnostics = dispatcher.diagnostics()
        assert diagnostics["workerCount"] == 8
        assert diagnostics["queueCapacity"] == 100
        assert DEFAULT_STAGE_DISPATCH_WORKERS == 8
        assert DEFAULT_STAGE_DISPATCH_QUEUE_CAPACITY == 100
    finally:
        dispatcher.shutdown()


def test_dispatcher_can_run_submissions_deterministically_without_worker_threads():
    calls = []
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: calls.append((item.project_id, item.task_id, item.run_id, item.payload)) or "done",
        worker_count=2,
        queue_capacity=2,
        autostart=False,
    )

    accepted = dispatcher.submit(
        project_id="project-1",
        task_id="task-1",
        run_id="run-1",
        payload={"attemptId": "attempt-1"},
    )

    assert accepted.accepted is True
    assert accepted.code == "accepted"
    assert accepted.queued == 1

    result = dispatcher.run_next_for_tests()

    assert result is not None
    assert result.ok is True
    assert result.result == "done"
    assert calls == [("project-1", "task-1", "run-1", {"attemptId": "attempt-1"})]
    assert dispatcher.diagnostics() == {
        "workerCount": 2,
        "queueCapacity": 2,
        "queued": 0,
        "inFlight": 0,
        "submitted": 1,
        "accepted": 1,
        "rejected": 0,
        "completed": 1,
        "failed": 0,
        "shutdown": False,
    }


def test_dispatcher_rejects_when_queue_is_full_without_dropping_accepted_work():
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: item.task_id,
        worker_count=1,
        queue_capacity=1,
        autostart=False,
    )

    first = dispatcher.submit(project_id="project-1", task_id="task-1", run_id="run-1")
    second = dispatcher.submit(project_id="project-1", task_id="task-2", run_id="run-1")

    assert first.accepted is True
    assert second.accepted is False
    assert second.code == QUEUE_FULL_CODE
    diagnostics = dispatcher.diagnostics()
    assert diagnostics["queued"] == 1
    assert diagnostics["accepted"] == 1
    assert diagnostics["rejected"] == 1

    result = dispatcher.run_next_for_tests()
    assert result is not None
    assert result.ok is True
    assert result.item.task_id == "task-1"
    assert dispatcher.run_next_for_tests() is None


def test_dispatcher_records_runner_failures_without_crashing_worker_accounting():
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: (_ for _ in ()).throw(RuntimeError("provider failed")),
        worker_count=1,
        queue_capacity=1,
        autostart=False,
    )

    dispatcher.submit(project_id="project-1", task_id="task-1", run_id="run-1")
    result = dispatcher.run_next_for_tests()

    assert result is not None
    assert result.ok is False
    assert result.error == "provider failed"
    diagnostics = dispatcher.diagnostics()
    assert diagnostics["failed"] == 1
    assert diagnostics["completed"] == 0
    assert diagnostics["inFlight"] == 0


def test_dispatcher_rejects_new_work_after_shutdown():
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: item.task_id,
        worker_count=1,
        queue_capacity=1,
        autostart=False,
    )

    dispatcher.shutdown()
    rejected = dispatcher.submit(project_id="project-1", task_id="task-1", run_id="run-1")

    assert rejected.accepted is False
    assert rejected.code == "dispatcher_shutdown"
    assert dispatcher.diagnostics()["rejected"] == 1


def test_dispatcher_wait_until_idle_observes_worker_completion():
    calls = []
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: calls.append(item.task_id),
        worker_count=2,
        queue_capacity=4,
    )
    try:
        for index in range(4):
            submission = dispatcher.submit(
                project_id="project-1",
                task_id=f"task-{index}",
                run_id="run-1",
            )
            assert submission.accepted is True

        assert dispatcher.wait_until_idle(timeout=2.0) is True
        assert sorted(calls) == ["task-0", "task-1", "task-2", "task-3"]
        diagnostics = dispatcher.diagnostics()
        assert diagnostics["completed"] == 4
        assert diagnostics["queued"] == 0
        assert diagnostics["inFlight"] == 0
    finally:
        dispatcher.shutdown()


def test_reserve_stage_run_preflights_and_atomically_reserves_all_current_stage_tasks():
    store, repo = _repo(_project())
    ports = _Ports()

    outcome = reserve_stage_run(
        "project-1",
        {"revision": 0, "stage": 1, "actor": {"type": "management", "id": "owner"}},
        repository=repo,
        ports=ports,
    )

    assert outcome.result.status == 200
    assert outcome.reservation is not None
    assert outcome.reservation.run_id == "run-1"
    assert outcome.reservation.stage == 1
    assert outcome.reservation.task_ids == ("a", "b")
    assert set(outcome.reservation.roles_by_task_id) == {"a", "b"}
    assert store.save_calls == 1
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "starting"
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved["orchestration"]["revision"] == 1
    assert [(task["id"], task.get("stageRunId")) for task in saved["tasks"]] == [
        ("a", "run-1"),
        ("b", "run-1"),
        ("c", None),
    ]
    assert ports.workspace_calls == ["/work/project"]
    assert ports.git_calls == ["/work/project"]
    assert ports.role_calls == [
        ("project-1", "a", False),
        ("project-1", "b", False),
    ]
    assert ports.authorize_calls == [("project-1", {"type": "management", "id": "owner"})]


def test_reserve_stage_run_honors_task_reviewerless_execution_without_request_confirmation():
    project = _project(tasks=[
        _task("a", 1, reviewerAgentId=None, allowReviewerlessExecution=True),
    ])
    store, repo = _repo(project)
    ports = _Ports(roles=lambda _project, task, allow_skip: (
        {"ok": True, "executor": {"id": "executor"}}
        if allow_skip
        else {
            "ok": False,
            "confirmationRequired": True,
            "code": "reviewer_skip_confirmation_required",
            "error": "No reviewer is configured",
        }
    ))

    outcome = reserve_stage_run(
        "project-1",
        {"revision": 0, "stage": 1},
        repository=repo,
        ports=ports,
    )

    assert outcome.result.status == 200
    assert ports.role_calls == [("project-1", "a", True)]
    assert store.save_calls == 1


def test_reserve_stage_run_rejects_stale_revision_without_saving():
    project = _project()
    project["orchestration"]["revision"] = 3
    store, repo = _repo(project)

    outcome = reserve_stage_run("project-1", {"revision": 2, "stage": 1}, repository=repo, ports=_Ports())

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "orchestration_revision_conflict"
    assert store.save_calls == 0
    assert store.data["projects"][0] == project


def test_reserve_stage_run_rejects_unauthorized_actor_without_workspace_or_role_checks():
    project = _project()
    store, repo = _repo(project)
    ports = _Ports(authorize={"ok": False, "code": "management_token_required", "error": "nope"})

    outcome = reserve_stage_run(
        "project-1",
        {"revision": 0, "stage": 1, "actor": {"type": "anonymous"}},
        repository=repo,
        ports=ports,
    )

    assert outcome.result.status == 409
    assert any(item["code"] == "management_token_required" for item in outcome.result.payload["blockers"])
    assert store.save_calls == 0


def test_reserve_stage_run_requires_dirty_workspace_confirmation():
    project = _project()
    store, repo = _repo(project)
    ports = _Ports(git_state={
        "ok": True,
        "dirty": True,
        "files": ["a.py", "b.py"],
        "fingerprint": "dirty-1",
        "truncated": False,
    })

    rejected = reserve_stage_run("project-1", {"revision": 0, "stage": 1}, repository=repo, ports=ports)
    accepted = reserve_stage_run(
        "project-1",
        {"revision": 0, "stage": 1, "dirtyFingerprint": "dirty-1"},
        repository=repo,
        ports=ports,
    )

    assert rejected.result.status == 409
    assert rejected.result.payload["dirtyFingerprint"] == "dirty-1"
    assert any(item["code"] == "dirty_worktree_confirmation_required" for item in rejected.result.payload["blockers"])
    assert accepted.result.status == 200
    assert store.save_calls == 1


def test_reserve_stage_run_aggregates_role_and_active_attempt_blockers_without_saving():
    project = _project(tasks=[
        _task("a", 1, activeAttemptId="attempt-1", attempts=[{"id": "attempt-1", "status": "executing"}]),
        _task("b", 1, reviewerAgentId=None),
    ])
    store, repo = _repo(project)
    ports = _Ports(roles=lambda _project, task, _allow: (
        {"ok": False, "code": "reviewer_required", "error": "reviewer missing"}
        if task["id"] == "b"
        else {"ok": True, "executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}}
    ))

    outcome = reserve_stage_run("project-1", {"revision": 0, "stage": 1}, repository=repo, ports=ports)

    assert outcome.result.status == 409
    codes = [item["code"] for item in outcome.result.payload["blockers"]]
    assert "active_attempt_exists" in codes
    assert "reviewer_required" in codes
    assert store.save_calls == 0


def test_reserve_stage_run_revalidates_inside_repository_update_before_saving():
    project = _project()
    store, repo = _repo(project)
    ports = _Ports()
    original_update = repo.update

    def concurrent_update(project_id, mutator):
        def wrapped(changed):
            changed["orchestration"]["revision"] = 1
            return mutator(changed)
        return original_update(project_id, wrapped)

    repo.update = concurrent_update

    outcome = reserve_stage_run("project-1", {"revision": 0, "stage": 1}, repository=repo, ports=ports)

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "orchestration_revision_conflict"
    assert store.save_calls == 0


def test_prepare_reserved_task_attempt_creates_attempt_without_project_singular_active_authority():
    project = _project()
    project["orchestration"].update({"state": "starting", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0]["stageRunId"] = "run-1"
    project["tasks"][1]["stageRunId"] = "run-1"
    store, repo = _repo(project)
    ports = _AttemptPorts()

    outcome = prepare_reserved_task_attempt(
        "project-1",
        "a",
        "run-1",
        repository=repo,
        ports=ports,
        workspace={"path": "/work/project", "kind": "local"},
        git_state={"dirty": False, "files": [], "fingerprint": ""},
        roles={"executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}},
        body={"by": "stage-dispatch", "autoReviewAfterExecution": True},
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["attemptId"] == "attempt-1"
    assert outcome.preparation is not None
    assert outcome.preparation.idempotent is False
    saved = store.data["projects"][0]
    task = saved["tasks"][0]
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved.get("activeTaskId") is None
    assert saved.get("activeAgent") is None
    assert saved.get("projectExecutionFlowActive") is None
    assert task["activeAttemptId"] == "attempt-1"
    assert task["attempts"][-1]["stageRunId"] == "run-1"
    assert task["attempts"][-1]["startMode"] == "stage"
    assert task["attempts"][-1]["projectFlow"] is True
    assert task["attempts"][-1]["autoReviewAfterExecution"] is True
    assert ports.seeded == []
    assert ports.transitions[-1][:3] == ("project-1", "a", "executing")


def test_prepare_reserved_task_attempt_is_idempotent_for_same_task_and_run():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "activeAttemptId": "attempt-existing",
        "attempts": [{"id": "attempt-existing", "status": "executing", "stageRunId": "run-1"}],
    })
    store, repo = _repo(project)
    ports = _AttemptPorts()

    outcome = prepare_reserved_task_attempt(
        "project-1",
        "a",
        "run-1",
        repository=repo,
        ports=ports,
        workspace={"path": "/work/project", "kind": "local"},
        git_state={"dirty": False},
        roles={"executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}},
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "already_started"
    assert outcome.result.payload["attemptId"] == "attempt-existing"
    assert outcome.result.payload["idempotent"] is True
    assert outcome.preparation is not None
    assert outcome.preparation.idempotent is True
    assert store.save_calls == 1
    assert len(store.data["projects"][0]["tasks"][0]["attempts"]) == 1
    assert ports.seeded == []
    assert ports.transitions == []


def test_prepare_reserved_task_attempt_allows_parallel_current_stage_tasks():
    project = _project()
    project["orchestration"].update({"state": "starting", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0]["stageRunId"] = "run-1"
    project["tasks"][1]["stageRunId"] = "run-1"
    store, repo = _repo(project)
    ports = _AttemptPorts()

    first = prepare_reserved_task_attempt(
        "project-1",
        "a",
        "run-1",
        repository=repo,
        ports=ports,
        workspace={"path": "/work/project", "kind": "local"},
        git_state={"dirty": False},
        roles={"executor": {"id": "executor-a"}, "reviewer": {"id": "reviewer"}},
    )
    second = prepare_reserved_task_attempt(
        "project-1",
        "b",
        "run-1",
        repository=repo,
        ports=ports,
        workspace={"path": "/work/project", "kind": "local"},
        git_state={"dirty": False},
        roles={"executor": {"id": "executor-b"}, "reviewer": {"id": "reviewer"}},
    )

    assert first.result.status == 200
    assert second.result.status == 200
    saved = store.data["projects"][0]
    assert saved["tasks"][0]["activeAttemptId"] == "attempt-1"
    assert saved["tasks"][1]["activeAttemptId"] == "attempt-2"
    assert saved.get("activeTaskId") is None
    assert saved.get("activeAgent") is None


def test_prepare_reserved_task_attempt_rejects_mismatched_run_and_unreserved_task():
    project = _project()
    project["orchestration"].update({"state": "starting", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0]["stageRunId"] = "run-2"
    store, repo = _repo(project)

    outcome = prepare_reserved_task_attempt(
        "project-1",
        "a",
        "run-1",
        repository=repo,
        ports=_AttemptPorts(),
        workspace={"path": "/work/project", "kind": "local"},
        git_state={"dirty": False},
        roles={"executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}},
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "task_not_reserved_for_run"
    assert store.save_calls == 0


def test_prepare_reserved_task_attempt_rejects_other_active_attempt():
    project = _project()
    project["orchestration"].update({"state": "starting", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "activeAttemptId": "attempt-other",
        "attempts": [{"id": "attempt-other", "status": "executing", "stageRunId": "run-other"}],
    })
    store, repo = _repo(project)

    outcome = prepare_reserved_task_attempt(
        "project-1",
        "a",
        "run-1",
        repository=repo,
        ports=_AttemptPorts(),
        workspace={"path": "/work/project", "kind": "local"},
        git_state={"dirty": False},
        roles={"executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}},
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "active_attempt_exists"
    assert store.save_calls == 0


def test_start_marked_project_reserves_prepares_and_submits_current_stage():
    store, repo = _repo(_project())
    preflight_ports = _Ports()
    attempt_ports = _AttemptPorts()
    dispatched = []
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: dispatched.append((item.task_id, item.payload["attemptId"])),
        worker_count=1,
        queue_capacity=4,
        autostart=False,
    )
    cancel_flags = {}

    outcome = start_marked_project(
        "project-1",
        {"by": "owner"},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: cancel_flags.setdefault(attempt_id, f"flag:{attempt_id}"),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "stage_started"
    assert outcome.result.payload["taskIds"] == ["a", "b"]
    assert [item["attemptId"] for item in outcome.result.payload["attempts"]] == ["attempt-1", "attempt-2"]
    assert [submission.accepted for submission in outcome.submissions] == [True, True]
    assert cancel_flags == {"attempt-1": "flag:attempt-1", "attempt-2": "flag:attempt-2"}
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved["orchestration"]["state"] == "running"
    assert saved["tasks"][0]["activeAttemptId"] == "attempt-1"
    assert saved["tasks"][1]["activeAttemptId"] == "attempt-2"
    assert saved["tasks"][2].get("stageRunId") is None
    assert saved.get("activeTaskId") is None
    assert saved.get("activeAgent") is None
    assert saved.get("projectExecutionFlowActive") is None
    assert dispatcher.diagnostics()["queued"] == 2
    assert dispatcher.run_next_for_tests().ok is True
    assert dispatcher.run_next_for_tests().ok is True
    assert dispatched == [("a", "attempt-1"), ("b", "attempt-2")]


def test_start_marked_project_rejects_legacy_start_payload_fields():
    store, repo = _repo(_project())
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: None, autostart=False)

    outcome = start_marked_project(
        "project-1",
        {"mode": "single", "startMode": "continuous", "restartPipeline": True},
        repository=repo,
        preflight_ports=_Ports(),
        attempt_ports=_AttemptPorts(),
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: object(),
    )

    assert outcome.result.status == 400
    assert outcome.result.payload["code"] == "marked_project_legacy_start_payload_forbidden"
    assert outcome.result.payload["fields"] == ["mode", "startMode", "restartPipeline"]
    assert store.save_calls == 0


def test_start_marked_project_restarts_completed_reusable_project_with_fresh_runtime_state():
    project = _project(
        projectType="reusable",
        status="completed",
        tasks=[
            _task(
                "a",
                1,
                columnId="done",
                executionState="done",
                completedAt="done-at",
                stageRunId="run-old",
                activeAttemptId="attempt-old",
                blockedReason="old block",
                lastError="old error",
                reworkFeedback="old feedback",
                reworkCount=2,
                evidence={"summary": "old"},
                reviewResult={"status": "pass"},
                checklist=[
                    {
                        "id": "deliverable",
                        "text": "Produce report",
                        "done": True,
                        "completedAt": "done-at",
                        "completedBy": "executor",
                        "completionEvidence": "old evidence",
                    },
                    {
                        "id": "meeting",
                        "text": "Meeting action",
                        "done": True,
                        "source": "meeting_action_item",
                    },
                ],
                meetingBlocker={"requestId": "req-1"},
                meetingActionItems=[{"id": "m1"}],
                meetingDecisionHistory=[{"id": "d1"}],
                meetingDiscussionPoints=[{"id": "p1"}],
                meetingRecords=[{"id": "r1"}],
                attempts=[{"id": "attempt-old", "status": "completed", "stageRunId": "run-old"}],
            ),
            _task(
                "later",
                2,
                executionState="done",
                completedAt="done-at",
                stageRunId="run-later",
            ),
        ],
    )
    project["orchestration"].update({
        "state": "completed",
        "currentStage": 2,
        "currentRunId": None,
        "completedAt": "done-at",
        "revision": 5,
    })
    store, repo = _repo(project)
    preflight_ports = _Ports()
    preflight_ports.run_ids = ["run-fresh"]
    attempt_ports = _AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: item.task_id, worker_count=1, queue_capacity=2, autostart=False)

    outcome = start_marked_project(
        "project-1",
        {"revision": 5, "by": "owner"},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["currentStage"] == 1
    assert outcome.result.payload["currentRunId"] == "run-fresh"
    saved = store.data["projects"][0]
    task = saved["tasks"][0]
    assert saved["status"] == "active"
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["currentRunId"] == "run-fresh"
    assert saved["orchestration"]["completedAt"] is None
    assert task["stageRunId"] == "run-fresh"
    assert task["executionState"] == "executing"
    assert task["completedAt"] is None
    assert task["activeAttemptId"] == "attempt-1"
    assert task["blockedReason"] is None
    assert task["lastError"] is None
    assert task["reworkFeedback"] is None
    assert task["reworkCount"] == 0
    assert task["evidence"] == {}
    assert task["reviewResult"] == {}
    assert task["meetingBlocker"] == {}
    assert task["meetingBlockerHistory"][0]["requestId"] == "req-1"
    assert task["meetingActionItems"] == []
    assert task["meetingDecisionHistory"] == []
    assert task["meetingDiscussionPoints"] == []
    assert task["meetingRecords"] == []
    assert task["checklist"] == [{"id": "meeting", "text": "Meeting action", "done": True, "source": "meeting_action_item"}]
    assert [attempt["id"] for attempt in task["attempts"]] == ["attempt-old", "attempt-1"]
    assert saved["tasks"][1]["stageRunId"] is None
    assert saved["tasks"][1]["executionState"] == "backlog"
    assert dispatcher.diagnostics()["queued"] == 1


def test_start_marked_project_restarts_inactive_running_blocked_stage_task_with_fresh_rework_window():
    project = _project(tasks=[
        *[
            _task(f"done-{stage}", stage, executionState="done", completedAt="done-at", stageRunId=f"run-{stage}")
            for stage in range(1, 6)
        ],
        _task(
            "risk",
            6,
            executionState="blocked",
            stageRunId="run-old",
            reworkCount=3,
            blockedReason="Acceptance checklist is still incomplete after three automatic rework cycles.",
            lastError="checklist_incomplete_rework_limit",
        ),
    ])
    project["orchestration"].update({
        "state": "running",
        "currentStage": 6,
        "currentRunId": "run-old",
        "revision": 4,
    })
    store, repo = _repo(project)
    preflight_ports = _Ports()
    preflight_ports.run_ids = ["run-retry"]
    attempt_ports = _AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: item.task_id, worker_count=1, queue_capacity=2, autostart=False)

    outcome = start_marked_project(
        "project-1",
        {"revision": 4, "stage": 6, "by": "owner"},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["currentStage"] == 6
    saved = store.data["projects"][0]
    task = next(item for item in saved["tasks"] if item["id"] == "risk")
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentRunId"] == "run-retry"
    assert task["stageRunId"] == "run-retry"
    assert task["executionState"] == "executing"
    assert task["activeAttemptId"] == "attempt-1"
    assert task["reworkCount"] == 0
    assert task["blockedReason"] is None
    assert task["lastError"] is None


def test_start_marked_project_recovers_stale_running_backlog_stage_residue():
    project = _project(tasks=[
        *[
            _task(f"done-{stage}", stage, executionState="done", completedAt="done-at", stageRunId=f"run-{stage}")
            for stage in range(1, 8)
        ],
        _task(
            "review-meeting",
            8,
            executionState="backlog",
            stageRunId="run-old",
            activeAttemptId="attempt-old",
            attempts=[{"id": "attempt-old", "status": "executing", "stageRunId": "run-old"}],
        ),
    ])
    project["orchestration"].update({
        "state": "running",
        "currentStage": 8,
        "currentRunId": "run-old",
        "revision": 9,
    })
    store, repo = _repo(project)
    preflight_ports = _Ports()
    preflight_ports.run_ids = ["run-recovered"]
    attempt_ports = _AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: item.task_id, worker_count=1, queue_capacity=2, autostart=False)

    outcome = start_marked_project(
        "project-1",
        {"revision": 9, "stage": 8, "by": "owner"},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
    )

    assert outcome.result.status == 200
    saved = store.data["projects"][0]
    task = next(item for item in saved["tasks"] if item["id"] == "review-meeting")
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentRunId"] == "run-recovered"
    assert task["previousStageRunId"] == "run-old"
    assert task["stageRunId"] == "run-recovered"
    assert task["activeAttemptId"] == "attempt-1"
    assert task["attempts"][0]["status"] == "stale"
    assert task["attempts"][0]["staleReason"]
    assert task["attempts"][1]["id"] == "attempt-1"
    assert task["executionState"] == "executing"


def test_resume_paused_project_starts_first_unfinished_stage_with_new_run_id():
    project = _project(tasks=[
        _task("done", 1, executionState="done", completedAt="done-at", stageRunId="run-old"),
        _task(
            "resume-a",
            2,
            executionState="pending",
            stageRunId=None,
            attempts=[{"id": "old-a", "status": "cancelled", "stageRunId": "run-old"}],
        ),
        _task("resume-b", 2, executionState="pending", stageRunId=None),
        _task("later", 3, executionState="pending", stageRunId=None),
    ])
    project["orchestration"].update({"state": "paused", "currentStage": 1, "currentRunId": None, "revision": 7})
    store, repo = _repo(project)
    preflight_ports = _Ports()
    preflight_ports.run_ids = ["run-resume"]
    attempt_ports = _AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: item.task_id, worker_count=1, queue_capacity=4, autostart=False)
    cancel_flags = []

    outcome = resume_paused_project(
        "project-1",
        {"revision": 7, "stage": 3, "actor": {"type": "management", "id": "owner"}},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: cancel_flags.append(attempt_id) or {"attemptId": attempt_id},
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "stage_started"
    assert outcome.result.payload["currentStage"] == 2
    assert outcome.result.payload["currentRunId"] == "run-resume"
    assert outcome.result.payload["taskIds"] == ["resume-a", "resume-b"]
    saved = store.data["projects"][0]
    by_id = {task["id"]: task for task in saved["tasks"]}
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentStage"] == 2
    assert saved["orchestration"]["currentRunId"] == "run-resume"
    assert saved["orchestration"]["revision"] == 8
    assert by_id["done"]["stageRunId"] == "run-old"
    assert by_id["done"]["executionState"] == "done"
    assert by_id["resume-a"]["stageRunId"] == "run-resume"
    assert by_id["resume-a"]["activeAttemptId"] == "attempt-1"
    assert [attempt["id"] for attempt in by_id["resume-a"]["attempts"]] == ["old-a", "attempt-1"]
    assert by_id["resume-a"]["attempts"][-1]["stageRunId"] == "run-resume"
    assert by_id["resume-b"]["activeAttemptId"] == "attempt-2"
    assert by_id["later"]["stageRunId"] is None
    assert cancel_flags == ["attempt-1", "attempt-2"]
    assert dispatcher.diagnostics()["queued"] == 2


def test_resume_paused_project_rejects_non_paused_or_fully_completed_project():
    running_store, running_repo = _repo(_project())
    running = resume_paused_project(
        "project-1",
        {"revision": 0},
        repository=running_repo,
        preflight_ports=_Ports(),
        attempt_ports=_AttemptPorts(),
        dispatcher=BoundedProjectExecutionDispatcher(lambda item: item.task_id, autostart=False),
        create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
    )

    assert running.result.status == 409
    assert running.result.payload["code"] == "orchestration_not_resumable"
    assert running_store.save_calls == 0

    project = _project(tasks=[
        _task("done-a", 1, executionState="done", completedAt="done-at"),
        _task("done-b", 2, executionState="completed"),
    ])
    project["orchestration"].update({"state": "paused", "currentStage": 2, "currentRunId": None})
    completed_store, completed_repo = _repo(project)
    completed = resume_paused_project(
        "project-1",
        {"revision": 0},
        repository=completed_repo,
        preflight_ports=_Ports(),
        attempt_ports=_AttemptPorts(),
        dispatcher=BoundedProjectExecutionDispatcher(lambda item: item.task_id, autostart=False),
        create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
    )

    assert completed.result.status == 409
    assert completed.result.payload["code"] == "no_unfinished_stage"
    assert completed_store.save_calls == 0


def test_start_marked_project_returns_aggregated_preflight_blockers_before_mutation():
    project = _project()
    store, repo = _repo(project)
    preflight_ports = _Ports(
        git_state={
            "ok": True,
            "dirty": True,
            "files": ["dirty.txt"],
            "fingerprint": "dirty-fp",
            "truncated": False,
        },
        roles=lambda _project, task, _allow: (
            {"ok": False, "code": "reviewer_required", "error": "reviewer missing"}
            if task["id"] == "b"
            else {"ok": True, "executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}}
        ),
    )
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: None, autostart=False)

    outcome = start_marked_project(
        "project-1",
        {},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=_AttemptPorts(),
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: object(),
    )

    assert outcome.result.status == 409
    codes = [item["code"] for item in outcome.result.payload["blockers"]]
    assert "dirty_worktree_confirmation_required" in codes
    assert "reviewer_required" in codes
    assert store.save_calls == 0
    assert store.data["projects"][0] == project
    assert dispatcher.diagnostics()["submitted"] == 0


def test_start_marked_project_blocks_rejected_task_and_preserves_submitted_truth():
    store, repo = _repo(_project())
    preflight_ports = _Ports()
    attempt_ports = _AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: None,
        worker_count=1,
        queue_capacity=1,
        autostart=False,
    )

    outcome = start_marked_project(
        "project-1",
        {},
        repository=repo,
        preflight_ports=preflight_ports,
        attempt_ports=attempt_ports,
        dispatcher=dispatcher,
        create_cancel_flag=lambda attempt_id: f"flag:{attempt_id}",
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == QUEUE_FULL_CODE
    assert outcome.result.payload["taskId"] == "b"
    assert outcome.result.payload["submittedTaskIds"] == ["a"]
    assert [submission.accepted for submission in outcome.submissions] == [True, False]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "blocked"
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["pauseReason"] == QUEUE_FULL_CODE
    by_id = {task["id"]: task for task in saved["tasks"]}
    assert by_id["a"]["activeAttemptId"] == "attempt-1"
    assert by_id["a"]["executionState"] == "executing"
    assert by_id["a"]["attempts"][-1]["status"] == "executing"
    assert by_id["b"]["activeAttemptId"] is None
    assert by_id["b"]["executionState"] == "blocked"
    assert by_id["b"]["blockedReason"] == QUEUE_FULL_CODE
    assert by_id["b"]["attempts"][-1]["status"] == "blocked"
    assert by_id["b"]["attempts"][-1]["blockedReason"] == QUEUE_FULL_CODE
    assert by_id["c"].get("stageRunId") is None
    assert by_id["c"]["executionState"] == "pending"
    assert dispatcher.diagnostics()["queued"] == 1


def test_reconcile_stage_waits_until_every_current_stage_task_is_accepted_terminal():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({"stageRunId": "run-1", "executionState": "done", "completedAt": "done-at"})
    project["tasks"][1].update({"stageRunId": "run-1", "executionState": "executing"})
    store, repo = _repo(project)

    outcome = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "now",
        new_run_id=lambda: "run-2",
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "stage_waiting"
    assert outcome.result.payload["pendingTaskIds"] == ["b"]
    assert outcome.reconciliation is not None
    assert outcome.reconciliation.idempotent is True
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved["tasks"][2].get("stageRunId") is None


def test_reconcile_stage_does_not_advance_while_project_is_pausing():
    project = _project(tasks=[
        _task("a", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
        _task("b", 2),
    ])
    project["orchestration"].update({
        "state": "pausing",
        "currentStage": 1,
        "currentRunId": "run-1",
        "pauseReason": "rebalance stages",
        "pauseSnapshot": {"activeAttemptIds": ["attempt-a"], "activeAttempts": []},
    })
    store, repo = _repo(project)

    outcome = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "now",
        new_run_id=lambda: "run-2",
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "stage_pausing"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "pausing"
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved["orchestration"]["pauseSnapshot"]["activeAttemptIds"] == ["attempt-a"]
    assert saved["tasks"][1]["stageRunId"] is None


def test_reserve_stage_run_rejects_new_dispatch_while_project_is_pausing():
    project = _project()
    project["orchestration"].update({
        "state": "pausing",
        "currentStage": 1,
        "currentRunId": "run-1",
        "revision": 4,
        "pauseReason": "rebalance stages",
        "pauseSnapshot": {"activeAttemptIds": ["attempt-a"], "activeAttempts": []},
    })
    store, repo = _repo(project)

    outcome = reserve_stage_run(
        "project-1",
        {"revision": 4, "stage": 1, "actor": {"type": "management", "id": "manager"}},
        repository=repo,
        ports=_Ports(),
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "orchestration_not_startable"
    assert outcome.result.payload["blockers"][0]["code"] == "orchestration_not_startable"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "pausing"
    assert saved["tasks"][0]["stageRunId"] is None


def test_reconcile_stage_advances_current_run_once_and_ignores_duplicate_callback():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "executionState": "done",
        "completedAt": "done-at",
        "finalResult": {
            "status": "available",
            "summary": "Task A complete.",
            "markdownPath": "projects-md/project/tasks/a/TASK_FINAL_RESULT.md",
            "sourceAttemptId": "attempt-a",
            "artifactRefs": [{"kind": "file", "path": "a.md"}],
        },
    })
    project["tasks"][1].update({
        "stageRunId": "run-1",
        "executionState": "completed",
        "finalResult": {
            "status": "available",
            "summary": "Task B complete.",
            "markdownPath": "projects-md/project/tasks/b/TASK_FINAL_RESULT.md",
            "sourceAttemptId": "attempt-b",
            "artifactRefs": [],
        },
    })
    store, repo = _repo(project)
    allocated = []

    def new_run_id():
        allocated.append("run-2")
        return "run-2"

    first = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "now",
        new_run_id=new_run_id,
    )
    duplicate = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "later",
        new_run_id=lambda: "run-duplicate",
    )

    assert first.result.status == 200
    assert first.result.payload["status"] == "stage_advanced"
    assert first.result.payload["currentRunId"] == "run-2"
    assert duplicate.result.status == 200
    assert duplicate.result.payload["status"] == "stale_run_ignored"
    assert duplicate.result.payload["idempotent"] is True
    assert allocated == ["run-2"]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "starting"
    assert saved["orchestration"]["currentStage"] == 2
    assert saved["orchestration"]["currentRunId"] == "run-2"
    assert saved["orchestration"]["revision"] == 1
    handoff = saved["orchestration"]["stageHandoffs"]["1"]
    assert handoff["stage"] == 1
    assert [task["taskId"] for task in handoff["tasks"]] == ["a", "b"]
    assert handoff["tasks"][0]["summary"] == "Task A complete."
    assert handoff["tasks"][0]["markdownPath"].endswith("TASK_FINAL_RESULT.md")
    assert saved["tasks"][2]["stageRunId"] == "run-2"


def test_submit_reserved_stage_dispatches_reconciled_next_stage_even_when_workspace_dirty():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "executionState": "done",
        "completedAt": "done-a",
        "finalResult": {"status": "available", "summary": "Task A complete.", "markdownPath": "a/TASK_FINAL_RESULT.md"},
    })
    project["tasks"][1].update({
        "stageRunId": "run-1",
        "executionState": "done",
        "completedAt": "done-b",
        "finalResult": {"status": "available", "summary": "Task B complete.", "markdownPath": "b/TASK_FINAL_RESULT.md"},
    })
    store, repo = _repo(project)

    advanced = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "advanced-at",
        new_run_id=lambda: "run-2",
    )
    assert advanced.result.payload["status"] == "stage_advanced"

    preflight = _Ports(git_state={
        "ok": True,
        "dirty": True,
        "files": ["stage1_alpha.md", "stage1_beta.md"],
        "fingerprint": "stage-output-fingerprint",
        "truncated": False,
    })
    attempts = _AttemptPorts()
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: {"ok": True, "taskId": item.task_id}, autostart=False)
    try:
        submitted = submit_reserved_stage(
            "project-1",
            "run-2",
            {"by": "stage-dispatch"},
            repository=repo,
            preflight_ports=preflight,
            attempt_ports=attempts,
            dispatcher=dispatcher,
            create_cancel_flag=lambda attempt_id: {"attemptId": attempt_id},
        )

        assert submitted.result.status == 200
        assert submitted.result.payload["status"] == "reserved_stage_submitted"
        assert submitted.result.payload["taskIds"] == ["c"]
        assert submitted.result.payload["attempts"][0]["attemptId"] == "attempt-1"
        saved = store.data["projects"][0]
        assert saved["orchestration"]["state"] == "running"
        assert saved["orchestration"]["currentStage"] == 2
        assert saved["tasks"][2]["executionState"] == "executing"
        assert saved["tasks"][2]["activeAttemptId"] == "attempt-1"
        assert saved["tasks"][2]["attempts"][0]["dirtyConfirmed"] is True
        assert dispatcher.run_next_for_tests().item.task_id == "c"
    finally:
        dispatcher.shutdown()


def test_reconcile_stage_serializes_parallel_terminal_callbacks_to_one_advancement():
    import threading

    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({"stageRunId": "run-1", "executionState": "done", "completedAt": "done-at"})
    project["tasks"][1].update({"stageRunId": "run-1", "orchestrationSkip": {**default_skip_state(), "status": "approved"}})
    store, repo = _repo(project)
    ids = iter(["run-2", "run-duplicate"])
    results = []
    lock = threading.Lock()

    def worker():
        outcome = reconcile_stage(
            "project-1",
            "run-1",
            repository=repo,
            now=lambda: "now",
            new_run_id=lambda: next(ids),
        )
        with lock:
            results.append(outcome.result.payload["status"])

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["stage_advanced", "stale_run_ignored"]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentRunId"] == "run-2"
    assert saved["tasks"][2]["stageRunId"] == "run-2"


def test_reconcile_stage_completes_orchestration_when_final_stage_is_accepted_terminal():
    project = _project(tasks=[
        _task("a", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
        _task("b", 1, stageRunId="run-1", executionState="completed"),
    ])
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store, repo = _repo(project)

    outcome = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "completed-at",
        new_run_id=lambda: "unused",
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "project_completed"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "completed"
    assert saved["orchestration"]["currentRunId"] is None
    assert saved["orchestration"]["completedAt"] == "completed-at"
    assert saved["status"] == "completed"
    final_report = saved["orchestration"]["finalReport"]
    assert final_report["status"] == "available"
    assert final_report["markdownPath"] == "PROJECT_FINAL_REPORT.md"
    assert final_report["taskCount"] == 2
    assert final_report["completedTaskCount"] == 2


def test_reconcile_stage_notifies_once_when_final_project_completes():
    project = _project(tasks=[
        _task("a", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
        _task("b", 1, stageRunId="run-1", orchestrationSkip={**default_skip_state(), "status": "approved"}),
    ])
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store, repo = _repo(project)
    notifications = []

    def notify(completed_project, reason):
        notifications.append((completed_project["id"], completed_project["status"], reason))
        completed_project.setdefault("feishuNotifications", {})["project-complete:project-1:2"] = {
            "ok": True,
            "status": "sent",
        }
        return {"ok": True, "status": "sent"}

    completed = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "completed-at",
        new_run_id=lambda: "unused",
        on_project_completed=notify,
    )
    duplicate = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "later",
        new_run_id=lambda: "unused",
        on_project_completed=notify,
    )

    assert completed.result.status == 200
    assert completed.result.payload["status"] == "project_completed"
    assert completed.result.payload["notification"] == {"ok": True, "status": "sent"}
    assert duplicate.result.payload["status"] == "stale_run_ignored"
    assert notifications == [(
        "project-1",
        "completed",
        "Project pipeline completed after the final stage reached accepted terminal outcomes.",
    )]
    saved = store.data["projects"][0]
    assert saved["feishuNotifications"]["project-complete:project-1:2"]["ok"] is True


def test_reconcile_stage_completion_survives_notification_failure():
    project = _project(tasks=[
        _task("a", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
    ])
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store, repo = _repo(project)

    def fail_notification(_project, _reason):
        raise RuntimeError("feishu unavailable")

    outcome = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "completed-at",
        new_run_id=lambda: "unused",
        on_project_completed=fail_notification,
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "project_completed"
    assert outcome.result.payload["notification"] == {
        "ok": False,
        "status": "delivery_failed",
        "error": "feishu unavailable",
    }
    saved = store.data["projects"][0]
    assert saved["status"] == "completed"
    assert saved["orchestration"]["state"] == "completed"
    assert "feishuNotifications" not in saved


def test_reconcile_stage_does_not_complete_while_human_acceptance_task_is_pending():
    project = _project(tasks=[
        _task("implementation", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
        _task("human-acceptance", 1, stageRunId="run-1", executionState="awaiting_user_acceptance", requiresUserAcceptance=True),
    ])
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store, repo = _repo(project)
    notifications = []

    outcome = reconcile_stage(
        "project-1",
        "run-1",
        repository=repo,
        now=lambda: "now",
        new_run_id=lambda: "unused",
        on_project_completed=lambda project, reason: notifications.append(reason),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "stage_waiting"
    assert outcome.result.payload["pendingTaskIds"] == ["human-acceptance"]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "running"
    assert saved.get("status") != "completed"
    assert notifications == []
