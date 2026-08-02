#!/usr/bin/env python3
"""Persistent completion-report worker orchestration contracts."""

from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_generation import CompletionReportGenerationError
from services.project_completion_report_worker import (
    CompletionReportWorkerPorts,
    ProjectCompletionReportWorker,
)
from services.project_completion_reporting import stage_completion_report_occurrence
from services.project_repository import ProjectRepository


NOW = "2026-08-03T04:00:00+00:00"


class MemoryStore:
    def __init__(self, projects):
        self.data = {"projects": copy.deepcopy(projects), "templates": []}

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.data = copy.deepcopy(value)


def _project(project_id="project-1", run_id="run-1"):
    project = {
        "id": project_id,
        "title": project_id,
        "status": "completed",
        "workspacePath": "/workspace",
        "feishuCompletionReportEnabled": True,
        "orchestration": {"completedAt": NOW},
        "tasks": [],
    }
    stage_completion_report_occurrence(project, run_id=run_id, completed_at=NOW)
    return project


def _worker(projects, *, generate=None, deliver=None, timer_factory=None, batch_size=10):
    store = MemoryStore(projects)
    repository = ProjectRepository(load_projects=store.load, save_projects=store.save)
    events = []

    def collect(project):
        events.append(("collect", project["id"]))
        return {"artifacts": [], "omissions": []}

    def default_generate(project, occurrence, collected):
        events.append(("generate", project["id"], occurrence["occurrenceId"]))
        return {
            "report": {
                "goal": "Goal", "conclusion": "Done", "keyResults": [],
                "nonFatalExceptions": [], "followUps": [], "importantArtifacts": [],
            },
            "markdown": "# Report\n",
            "reportingAgentId": "agent",
        }

    def store_report(project, occurrence, markdown):
        events.append(("store", project["id"], markdown))
        return {"markdownPath": "report.md", "digest": "digest", "created": True}

    def default_deliver(project, occurrence, report):
        events.append(("deliver", project["id"], occurrence["occurrenceId"]))
        return {"ok": True, "status": "sent", "messageId": f"message-{project['id']}"}

    ports = CompletionReportWorkerPorts(
        repository=repository,
        now=lambda: NOW,
        new_token=(lambda counter=iter(range(100)): f"claim-{next(counter)}"),
        collect=collect,
        generate=generate or default_generate,
        store=store_report,
        deliver=deliver or default_deliver,
    )
    worker = ProjectCompletionReportWorker(
        ports,
        batch_size=batch_size,
        timer_factory=timer_factory,
    )
    return worker, store, events


def test_worker_processes_pending_occurrence_to_delivered_state():
    worker, store, events = _worker([_project()])

    result = worker.run_once()

    assert result == {"selected": 1, "delivered": 1, "failed": 0, "skipped": 0}
    occurrence = store.data["projects"][0]["orchestration"]["completionReports"][0]
    assert occurrence["state"] == "delivered"
    assert occurrence["visibleStatus"] == "delivered"
    assert occurrence["messageId"] == "message-project-1"
    assert occurrence["reportMarkdownPath"] == "report.md"
    assert [event[0] for event in events] == ["collect", "generate", "store", "deliver"]


def test_worker_isolates_one_generation_failure_and_continues_batch():
    def generate(project, occurrence, collected):
        if project["id"] == "project-1":
            raise CompletionReportGenerationError("reporting_agent_missing", "missing", recoverable=False)
        return {
            "report": {
                "goal": "Goal", "conclusion": "Done", "keyResults": [],
                "nonFatalExceptions": [], "followUps": [], "importantArtifacts": [],
            },
            "markdown": "# Report\n",
            "reportingAgentId": "agent",
        }

    worker, store, _events = _worker([_project("project-1"), _project("project-2")], generate=generate)

    result = worker.run_once()

    assert result == {"selected": 2, "delivered": 1, "failed": 1, "skipped": 0}
    states = {
        project["id"]: project["orchestration"]["completionReports"][0]["state"]
        for project in store.data["projects"]
    }
    assert states == {"project-1": "failed", "project-2": "delivered"}


def test_worker_limits_each_scan_to_ten_due_occurrences():
    projects = [_project(f"project-{index}") for index in range(12)]
    worker, store, _events = _worker(projects, batch_size=10)

    result = worker.run_once()

    assert result["selected"] == 10
    delivered = sum(
        project["orchestration"]["completionReports"][0]["state"] == "delivered"
        for project in store.data["projects"]
    )
    assert delivered == 10


def test_worker_recovers_expired_generation_claim_after_process_restart():
    project = _project()
    occurrence = project["orchestration"]["completionReports"][0]
    occurrence.update({
        "state": "generating",
        "claim": {
            "token": "dead-process",
            "claimedAt": "2026-08-03T03:00:00+00:00",
            "expiresAt": "2026-08-03T03:01:00+00:00",
        },
    })
    worker, store, _events = _worker([project])

    result = worker.run_once()

    assert result["delivered"] == 1
    recovered = store.data["projects"][0]["orchestration"]["completionReports"][0]
    assert recovered["state"] == "delivered"
    assert recovered["attemptCount"] == 1


def test_worker_start_uses_fifteen_second_periodic_timer_and_stop_delegates():
    constructed = []

    class FakeTimer:
        def __init__(self, callback, *, interval_seconds, name, on_error):
            constructed.append((callback, interval_seconds, name, on_error))
            self.started = False
            self.stopped = False

        def start(self):
            self.started = True
            return True

        def stop(self, timeout_seconds=5):
            self.stopped = True

    worker, _store, _events = _worker([_project()], timer_factory=FakeTimer)

    assert worker.start() is True
    assert constructed[0][1] == 15
    assert constructed[0][2] == "project-completion-report-worker"
    assert worker.start() is False
    worker.stop()
    assert worker._timer.stopped is True
