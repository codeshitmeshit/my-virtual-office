#!/usr/bin/env python3
"""End-to-end completion-report flow with fake Agent and notification app."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_api import resend_completion_report
from services.project_completion_report_runtime import CompletionReportRuntimeDependencies, build_completion_report_worker
from services.project_completion_reporting import stage_completion_report_occurrence
from services.project_repository import ProjectRepository


class _Store:
    def __init__(self, projects):
        self.data = {"projects": copy.deepcopy(projects), "templates": []}

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.data = copy.deepcopy(value)


class _Clock:
    def __init__(self):
        self.value = datetime(2026, 8, 3, tzinfo=timezone.utc)

    def now(self):
        return self.value.isoformat()

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def _project(workspace: Path, project_id="p1"):
    return {
        "id": project_id,
        "title": "Completion Demo",
        "status": "completed",
        "workspacePath": str(workspace),
        "tasks": [{
            "id": "task-1",
            "executionStage": 1,
            "finalResult": {
                "markdownPath": "task-result.md",
                "artifactRefs": ["credentials.env", "binary.zip"],
            },
        }],
        "orchestration": {
            "completedAt": "2026-08-03T00:00:00+00:00",
            "finalReport": {"markdownPath": "FINAL.md"},
        },
    }


def _runtime(projects, clock, agent_calls, notification_calls, notification_results):
    store = _Store(projects)
    repository = ProjectRepository(load_projects=store.load, save_projects=store.save)

    def read_artifact(context, path, **_options):
        full = Path(context["root"]) / path
        if not full.is_file():
            return {"ok": False, "error": "missing"}
        return {"ok": True, "artifact": {"content": full.read_text(), "kind": "markdown", "size": full.stat().st_size}}

    def generate_agent(**options):
        agent_calls.append(options)
        return {"ok": True, "reply": json.dumps({
            "goal": "Ship the project",
            "conclusion": "The project completed successfully",
            "keyResults": ["Final artifact generated"],
            "nonFatalExceptions": [],
            "followUps": ["Review the result"],
            "importantArtifacts": [{"label": "Final", "path": "FINAL.md", "note": "Primary result"}],
        })}

    def send_notification(intent, **options):
        notification_calls.append((intent, options))
        return notification_results.pop(0) if notification_results else {"ok": True, "messageId": "message"}

    dependencies = CompletionReportRuntimeDependencies(
        reporting_agent_id=lambda: "feishu-main-agent",
        artifact_context=lambda project: {"ok": True, "root": project["workspacePath"]},
        read_artifact=read_artifact,
        generate_agent=generate_agent,
        notification_app_config=lambda: {
            "appId": "notification-app",
            "appSecret": "notification-secret",
            "receiveIdType": "open_id",
            "receiveId": "owner-open-id",
        },
        send_notification=send_notification,
        project_url=lambda project_id: f"https://office/#projects?projectId={project_id}",
        now=clock.now,
        new_token=(lambda counter=iter(range(100)): f"token-{next(counter)}"),
    )
    return build_completion_report_worker(repository, dependencies), repository, store


def test_default_enabled_delivery_is_idempotent_versioned_and_scrubs_sensitive_artifacts(tmp_path):
    (tmp_path / "FINAL.md").write_text("Final result\napi_key=top-secret-value\n")
    (tmp_path / "task-result.md").write_text("Task complete")
    (tmp_path / "credentials.env").write_text("PASSWORD=must-never-leak")
    project = _project(tmp_path)
    first = stage_completion_report_occurrence(project, run_id="run-1", completed_at=project["orchestration"]["completedAt"])
    duplicate = stage_completion_report_occurrence(project, run_id="run-1", completed_at=project["orchestration"]["completedAt"])
    clock = _Clock()
    agent_calls, notification_calls = [], []
    worker, repository, store = _runtime([project], clock, agent_calls, notification_calls, [])

    delivered = worker.run_once()
    repository.update("p1", lambda saved: stage_completion_report_occurrence(saved, run_id="run-2", completed_at=clock.now()))
    delivered_v2 = worker.run_once()

    reports = store.data["projects"][0]["orchestration"]["completionReports"]
    assert first["created"] is True and duplicate["created"] is False
    assert delivered["delivered"] == 1 and delivered_v2["delivered"] == 1
    assert [(item["version"], item["state"]) for item in reports] == [(1, "delivered"), (2, "delivered")]
    assert "top-secret-value" not in agent_calls[0]["prompt"]
    assert "must-never-leak" not in agent_calls[0]["prompt"]
    assert "[REDACTED]" in agent_calls[0]["prompt"]
    assert notification_calls[0][1]["allow_webhook"] is False
    assert notification_calls[0][1]["app_config"]["appId"] == "notification-app"
    assert all(item["reportMarkdownPath"].endswith("FEISHU_COMPLETION_REPORT.md") for item in reports)


def test_explicitly_disabled_project_creates_no_delivery_intent(tmp_path):
    project = _project(tmp_path)
    project["feishuCompletionReportEnabled"] = False

    staged = stage_completion_report_occurrence(project, run_id="run-disabled", completed_at="2026-08-03T00:00:00+00:00")

    assert staged["status"] == "skipped_disabled"
    assert project["orchestration"]["completionReports"] == []


def test_retry_exhaustion_and_manual_resend_keep_project_completed_and_reuse_same_report(tmp_path):
    (tmp_path / "FINAL.md").write_text("Final result")
    (tmp_path / "task-result.md").write_text("Task result")
    project = _project(tmp_path)
    stage_completion_report_occurrence(project, run_id="run-retry", completed_at="2026-08-03T00:00:00+00:00")
    clock = _Clock()
    agent_calls, notification_calls = [], []
    failures = [
        {"ok": False, "status": "feishu_error", "code": 500, "error": "temporary"},
        {"ok": False, "status": "feishu_error", "code": 500, "error": "temporary"},
        {"ok": False, "status": "feishu_error", "code": 500, "error": "temporary"},
        {"ok": True, "status": "sent", "messageId": "manual-success"},
    ]
    worker, repository, store = _runtime([project], clock, agent_calls, notification_calls, failures)

    assert worker.run_once()["failed"] == 1
    clock.advance(31)
    assert worker.run_once()["failed"] == 1
    clock.advance(121)
    assert worker.run_once()["failed"] == 1
    failed = store.data["projects"][0]["orchestration"]["completionReports"][0]
    assert failed["state"] == "failed" and failed["attemptCount"] == 3

    outcome = resend_completion_report(
        "p1", failed["occurrenceId"], {}, repository=repository, now=clock.now,
        owner_authorized=True, wake=lambda: None,
    )
    assert outcome.status == 200
    assert worker.run_once()["delivered"] == 1
    saved_project = store.data["projects"][0]
    delivered = saved_project["orchestration"]["completionReports"][0]
    assert delivered["version"] == 1
    assert delivered["state"] == "delivered"
    assert delivered["messageId"] == "manual-success"
    assert saved_project["status"] == "completed"
    assert len(agent_calls) == 1
    assert len(notification_calls) == 4
