#!/usr/bin/env python3
"""Independent recurring-project occurrence claim and materialization tests."""

import copy
from datetime import datetime, timedelta, timezone
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_authoring import ProjectAuthoringCommandError, ProjectAuthoringService
from services.project_authoring_store import RECURRENCES_KEY, ProjectAuthoringRootStore
from services.project_repository import ProjectRepository


AGENTS = {agent_id: {"id": agent_id} for agent_id in ("author", "owner", "builder")}


def _draft(*, execution=False):
    return {
        "title": "Weekly release",
        "description": "Create an independent weekly project",
        "projectType": "recurring",
        "agentMaintenanceMode": "strict_confirmation",
        "projectExecutionEnabled": execution,
        "columns": [{"id": "todo", "title": "Todo"}],
        "tasks": [{
            "title": "Prepare release",
            "columnId": "todo",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerRecommendation": {"recommended": False, "triggers": []},
        }],
        "template": {"mode": "create", "name": "Weekly release template"},
        "recurrence": {
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "UTC"},
        },
    }


def _service(tmp_path, *, execution=False):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    identifiers = iter(("request-1", "claim-1", "claim-2", "claim-3", "claim-4"))
    current = [datetime(2025, 4, 1, tzinfo=timezone.utc)]
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda _agent_id: False,
        submission_enabled=lambda: True,
        recurrence_enabled=lambda: True,
        recurrence_paused=lambda: False,
        clock=lambda: current[0],
        new_id=lambda: next(identifiers),
    )
    service.create_pending(
        _draft(execution=execution),
        requesting_agent_id="author",
        idempotency_key="recurrence:draft-1",
        request_secret_hash="sha256:test",
    )
    source = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:recurrence-source",
    )["project"]
    return markdown, service, current, source


def test_occurrence_creates_one_independent_version_pinned_project(tmp_path):
    markdown, service, _, source = _service(tmp_path)

    first = service.materialize_recurrence_occurrence(
        "recurrence-request-1", "gateway-occurrence-2025-04-07",
    )
    repeated = service.materialize_recurrence_occurrence(
        "recurrence-request-1", "gateway-occurrence-2025-04-07",
    )

    assert first["created"] is True
    assert repeated["created"] is False
    assert first["project"]["id"] == repeated["project"]["id"]
    assert first["project"]["id"] != source["id"]
    assert first["project"]["templateRef"] == {"id": "template-request-1", "version": 1}
    assert first["project"]["recurrenceRef"] == {
        "id": "recurrence-request-1",
        "occurrenceId": "gateway-occurrence-2025-04-07",
    }
    assert first["project"]["authoringSource"] == {
        "kind": "recurrence_occurrence",
        "recurrenceId": "recurrence-request-1",
        "occurrenceId": "gateway-occurrence-2025-04-07",
        "templateId": "template-request-1",
        "templateVersion": 1,
    }
    assert first["project"]["workflowActive"] is False
    assert first["project"]["projectExecutionFlowActive"] is False
    root = markdown.load_all()
    assert len(root["projects"]) == 2
    occurrence = root[RECURRENCES_KEY]["recurrence-request-1"]["occurrences"][
        "gateway-occurrence-2025-04-07"
    ]
    assert occurrence["state"] == "created"
    assert "claimToken" not in occurrence


def test_live_claim_is_not_stolen_and_expired_claim_recovers_after_restart(tmp_path):
    markdown, service, current, _ = _service(tmp_path)
    recurrence_id = "recurrence-request-1"

    def live_claim(root):
        root[RECURRENCES_KEY][recurrence_id]["occurrences"] = {
            "live": {
                "occurrenceId": "live",
                "state": "claimed",
                "claimToken": "other-worker",
                "claimExpiresAt": (current[0] + timedelta(minutes=2)).isoformat(),
                "attempts": 1,
            },
            "expired": {
                "occurrenceId": "expired",
                "state": "claimed",
                "claimToken": "dead-worker",
                "claimExpiresAt": (current[0] - timedelta(seconds=1)).isoformat(),
                "attempts": 1,
            },
        }

    service.store.update(live_claim)

    live = service.materialize_recurrence_occurrence(recurrence_id, "live")
    recovered = service.materialize_recurrence_occurrence(recurrence_id, "expired")

    assert live["status"] == "in_progress" and live["_status"] == 202
    assert recovered["created"] is True
    root = markdown.load_all()
    assert root[RECURRENCES_KEY][recurrence_id]["occurrences"]["live"]["claimToken"] == "other-worker"
    assert root[RECURRENCES_KEY][recurrence_id]["occurrences"]["expired"]["attempts"] == 2


def test_workspace_failure_cleans_up_and_records_retryable_occurrence(tmp_path):
    markdown, service, _, _ = _service(tmp_path, execution=True)
    workspace = {
        "ok": False,
        "code": "workspace_failed",
        "error": "Authorization=Bearer workspace-secret",
        "path": "/tmp/partial-recurring-workspace",
        "managed": True,
        "created": True,
    }
    cleanup = []

    with pytest.raises(ProjectAuthoringCommandError) as failed:
        service.materialize_recurrence_occurrence(
            "recurrence-request-1",
            "workspace-failure",
            prepare_workspace=lambda *_args: workspace,
            cleanup_workspace=cleanup.append,
        )

    assert failed.value.code == "workspace_failed"
    assert cleanup == [workspace]
    root = markdown.load_all()
    assert len(root["projects"]) == 1
    record = root[RECURRENCES_KEY]["recurrence-request-1"]["occurrences"]["workspace-failure"]
    assert record["state"] == "failed" and record["retryable"] is True
    assert "workspace-secret" not in str(record)


def test_lost_claim_cannot_commit_and_cleans_prepared_workspace(tmp_path):
    markdown, service, _, _ = _service(tmp_path, execution=True)
    cleanup = []

    def prepare(_configuration, _project_id, _occurrence_id):
        def steal(root):
            record = root[RECURRENCES_KEY]["recurrence-request-1"]["occurrences"]["stolen"]
            record["claimToken"] = "new-worker"

        service.store.update(steal)
        return {
            "ok": True,
            "path": "/tmp/prepared-recurring-workspace",
            "kind": "directory",
            "managed": True,
            "created": True,
        }

    with pytest.raises(ProjectAuthoringCommandError) as lost:
        service.materialize_recurrence_occurrence(
            "recurrence-request-1",
            "stolen",
            prepare_workspace=prepare,
            cleanup_workspace=cleanup.append,
        )

    assert lost.value.code == "occurrence_claim_lost"
    assert cleanup[0]["path"] == "/tmp/prepared-recurring-workspace"
    assert len(markdown.load_all()["projects"]) == 1


def test_dispatch_feature_and_global_pause_are_enforced_before_claim(tmp_path):
    markdown, service, _, _ = _service(tmp_path)
    service.recurrence_enabled = lambda: False
    with pytest.raises(ProjectAuthoringCommandError) as disabled:
        service.materialize_recurrence_occurrence("recurrence-request-1", "disabled")
    assert disabled.value.code == "project_recurrence_disabled"

    service.recurrence_enabled = lambda: True
    service.recurrence_paused = lambda: True
    with pytest.raises(ProjectAuthoringCommandError) as paused:
        service.materialize_recurrence_occurrence("recurrence-request-1", "paused")
    assert paused.value.code == "project_recurrence_dispatch_paused"
    recurrence = markdown.load_all()[RECURRENCES_KEY]["recurrence-request-1"]
    assert recurrence.get("occurrences") in (None, {})

