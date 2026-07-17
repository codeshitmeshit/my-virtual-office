#!/usr/bin/env python3
"""Project authoring request state-machine and idempotency tests."""

from datetime import datetime, timezone
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_authoring import ProjectAuthoringCommandError, ProjectAuthoringService
from services.project_authoring_security import hash_request_secret
from services.project_authoring_store import (
    IDEMPOTENCY_KEY,
    OUTBOX_KEY,
    RECURRENCES_KEY,
    REQUESTS_KEY,
    TEMPLATES_KEY,
    ProjectAuthoringRootStore,
)
from services.project_repository import ProjectRepository


AGENTS = {
    "author": {"id": "author"},
    "owner": {"id": "owner"},
    "builder": {"id": "builder"},
    "reviewer": {"id": "reviewer"},
}


def _draft(title="Launch"):
    return {
        "title": title,
        "description": "Ship it",
        "projectType": "one_time",
        "agentMaintenanceMode": "strict_confirmation",
        "columns": [{"id": "backlog", "title": "Backlog"}],
        "tasks": [{
            "title": "Implement",
            "columnId": "backlog",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerRecommendation": {"recommended": False, "triggers": []},
        }],
        "template": {"mode": "none"},
        "recurrence": {"enabled": False},
    }


def _service(tmp_path):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    times = iter([
        datetime(2025, 1, day, tzinfo=timezone.utc) for day in range(1, 20)
    ])
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda agent_id: False,
        submission_enabled=lambda: True,
        clock=lambda: next(times),
        new_id=lambda: "request-1",
    )
    return markdown, repository, service


def _create(service, **kwargs):
    return service.create_pending(
        kwargs.pop("draft", _draft()),
        requesting_agent_id=kwargs.pop("requesting_agent_id", "author"),
        idempotency_key=kwargs.pop("idempotency_key", "author:key-1"),
        request_secret_hash=kwargs.pop("request_secret_hash", "sha256:secret"),
        source=kwargs.pop("source", {"surface": "skill"}),
    )


def test_create_pending_is_agent_scoped_idempotent_and_non_materializing(tmp_path):
    markdown, _, service = _service(tmp_path)

    created = _create(service)
    repeated = _create(service, draft=_draft("Different retry payload"))
    invalid_retry = _create(service, draft={"invalid": True})

    assert created["created"] is True
    assert repeated["created"] is False
    assert invalid_retry["created"] is False
    assert created["request"]["id"] == repeated["request"]["id"] == "request-1"
    root = markdown.load_all()
    assert root["projects"] == []
    assert root["templates"] == []
    assert root[OUTBOX_KEY] == []
    assert list(root[REQUESTS_KEY]) == ["request-1"]
    assert root[REQUESTS_KEY]["request-1"]["originalDraft"]["title"] == "Launch"
    assert root[IDEMPOTENCY_KEY]["author:author:key-1"]["requestId"] == "request-1"
    assert "requestSecretHash" not in created["request"]


def test_detail_list_and_agent_status_are_sanitized_and_bounded(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service)

    detail = service.get_management("request-1")
    listing = service.list_management(limit=500)
    agent = service.get_agent_status("request-1", requesting_agent_id="author")

    assert detail["workingDraft"]["title"] == "Launch"
    assert "requestSecretHash" not in detail
    assert listing == [{
        "id": "request-1",
        "requestId": "request-1",
        "requestingAgentId": "author",
        "state": "pending",
        "revision": 1,
        "title": "Launch",
        "projectType": "one_time",
        "taskCount": 1,
        "projectId": None,
        "createdAt": "2025-01-01T00:00:00+00:00",
        "updatedAt": "2025-01-01T00:00:00+00:00",
        "tombstone": False,
    }]
    assert agent["state"] == "pending"
    with pytest.raises(ProjectAuthoringCommandError) as cross_agent:
        service.get_agent_status("request-1", requesting_agent_id="builder")
    assert cross_agent.value.code == "project_authoring_request_not_found"


def test_agent_status_secret_is_bound_to_request_and_requesting_agent(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service, request_secret_hash=hash_request_secret("opaque-request-secret"))

    status = service.authenticate_agent_status(
        "request-1", requesting_agent_id="author", request_secret="opaque-request-secret",
    )

    assert status["state"] == "pending"
    with pytest.raises(ProjectAuthoringCommandError) as wrong_secret:
        service.authenticate_agent_status(
            "request-1", requesting_agent_id="author", request_secret="wrong",
        )
    assert wrong_secret.value.code == "invalid_project_authoring_secret"
    with pytest.raises(ProjectAuthoringCommandError):
        service.authenticate_agent_status(
            "request-1", requesting_agent_id="builder", request_secret="opaque-request-secret",
        )


def test_edit_uses_revision_cas_preserves_original_and_allows_confirmed_reviewer(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service)
    edited_draft = _draft("Edited")
    edited_draft["tasks"][0]["reviewerActor"] = {"type": "agent", "id": "reviewer"}

    edited = service.edit_pending("request-1", edited_draft, expected_revision=1)

    assert edited["revision"] == 2
    assert edited["workingDraft"]["title"] == "Edited"
    assert edited["workingDraft"]["tasks"][0]["reviewerAgentId"] == "reviewer"
    assert edited["originalDraft"]["title"] == "Launch"
    assert edited["history"][0]["draft"]["title"] == "Launch"
    with pytest.raises(ProjectAuthoringCommandError) as conflict:
        service.edit_pending("request-1", edited_draft, expected_revision=1)
    assert conflict.value.code == "request_revision_conflict"
    assert conflict.value.actual_revision == 2


def test_reject_is_auditable_idempotent_and_terminal(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service)

    rejected = service.reject_pending(
        "request-1", expected_revision=1, reason="Not the right scope", actor="user:local",
    )
    repeated = service.reject_pending(
        "request-1", expected_revision=1, reason="Ignored duplicate", actor="user:local",
    )

    assert rejected["state"] == "rejected"
    assert rejected["revision"] == 2
    assert repeated["rejectionReason"] == "Not the right scope"
    assert rejected["audit"][-1]["action"] == "draft_rejected"
    with pytest.raises(ProjectAuthoringCommandError) as invalid_state:
        service.edit_pending("request-1", _draft("Too late"), expected_revision=2)
    assert invalid_state.value.code == "invalid_request_state"


def test_confirmation_snapshot_is_versioned_and_failed_request_can_retry(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service)

    materializing = service.begin_confirmation(
        "request-1", expected_revision=1,
        confirmation_key="confirm:key-1", actor="user:local",
    )
    duplicate = service.begin_confirmation(
        "request-1", expected_revision=1,
        confirmation_key="confirm:key-1", actor="user:local",
    )
    materializing["approvedSnapshot"]["title"] = "Caller mutation"
    persisted = service.get_management("request-1")

    assert duplicate["revision"] == 2
    assert persisted["approvedSnapshot"]["title"] == "Launch"
    assert persisted["approvalHistory"][0]["snapshot"]["title"] == "Launch"

    failed = service.mark_materialization_failed(
        "request-1", expected_revision=2,
        code="workspace_failed", error="Workspace unavailable",
    )
    assert failed["state"] == "failed"
    assert failed["revision"] == 3
    retried = service.begin_confirmation(
        "request-1", expected_revision=3,
        confirmation_key="confirm:key-2", actor="user:local",
    )
    assert retried["state"] == "materializing"
    assert retried["revision"] == 4
    assert len(retried["approvalHistory"]) == 2


def test_submission_checks_feature_and_requesting_agent_before_persistence(tmp_path):
    _, repository, service = _service(tmp_path)
    service.submission_enabled = lambda: False
    with pytest.raises(RuntimeError) as disabled:
        _create(service)
    assert disabled.value.as_dict()["code"] == "project_authoring_disabled"

    service.submission_enabled = lambda: True
    with pytest.raises(ProjectAuthoringCommandError) as missing:
        _create(service, requesting_agent_id="missing")
    assert missing.value.code == "requesting_agent_not_found"
    assert repository.load_all()[REQUESTS_KEY] == {}


def test_confirm_materializes_complete_project_once_without_starting_execution(tmp_path):
    markdown, _, service = _service(tmp_path)
    _create(service)

    result = service.confirm_and_materialize(
        "request-1",
        expected_revision=1,
        confirmation_key="confirm:key-1",
        actor="user:local",
    )
    repeated = service.confirm_and_materialize(
        "request-1",
        expected_revision=1,
        confirmation_key="confirm:key-1",
        actor="user:local",
    )

    assert result["ok"] is True and result["created"] is True
    assert repeated["ok"] is True and repeated["created"] is False
    assert result["project"]["id"] == repeated["project"]["id"] == "project-request-1"
    project = markdown.load_all()["projects"][0]
    assert project["projectType"] == "one_time"
    assert project["authoringRequestId"] == "request-1"
    assert project["authoringAgentId"] == "author"
    assert project["workflowActive"] is False
    assert project["projectExecutionFlowActive"] is False
    assert project["tasks"][0]["executionState"] == "backlog"
    assert project["tasks"][0]["responsibleActor"] == {"type": "agent", "id": "owner"}
    assert project["tasks"][0]["executorActor"] == {"type": "agent", "id": "builder"}
    root = markdown.load_all()
    assert root[REQUESTS_KEY]["request-1"]["state"] == "confirmed"
    assert root[IDEMPOTENCY_KEY]["confirmation:request-1:confirm:key-1"]["projectId"] == "project-request-1"
    assert len(root["projects"]) == 1


def test_user_approved_reviewer_and_prepared_workspace_are_committed(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service)
    edited = _draft()
    edited["tasks"][0]["reviewerActor"] = {"type": "agent", "id": "reviewer"}
    service.edit_pending("request-1", edited, expected_revision=1)
    cleanup_calls = []

    result = service.confirm_and_materialize(
        "request-1",
        expected_revision=2,
        confirmation_key="confirm:key-2",
        prepare_workspace=lambda *_: {
            "ok": True,
            "path": "/tmp/managed-project-request-1",
            "kind": "directory",
            "managed": True,
            "created": True,
        },
        cleanup_workspace=cleanup_calls.append,
    )

    task = result["project"]["tasks"][0]
    assert task["reviewerActor"] == {"type": "agent", "id": "reviewer"}
    assert task["reviewerAgentId"] == "reviewer"
    assert result["project"]["workspaceManagedBy"] == "project_authoring"
    assert cleanup_calls == []


def test_recurring_confirmation_commits_template_recurrence_and_outbox_together(tmp_path):
    markdown, _, service = _service(tmp_path)
    recurring = _draft()
    recurring.update({
        "projectType": "recurring",
        "template": {"mode": "create", "name": "Weekly launch"},
        "recurrence": {
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "UTC"},
        },
    })
    _create(service, draft=recurring)

    result = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:recurring-1",
    )
    root = markdown.load_all()

    assert result["project"]["templateRef"] == {"id": "template-request-1", "version": 1}
    assert result["project"]["recurrenceRef"] == {"id": "recurrence-request-1"}
    assert root[TEMPLATES_KEY]["template-request-1"][0]["version"] == 1
    recurrence = root[RECURRENCES_KEY]["recurrence-request-1"]
    assert recurrence["targetType"] == "projectTemplateInstance"
    assert recurrence["requestingAgentId"] == "author"
    assert root[OUTBOX_KEY] == [{
        "id": "outbox-recurrence-request-1",
        "kind": "register_project_template_instance",
        "recurrenceId": "recurrence-request-1",
        "state": "pending",
        "attempts": 0,
        "createdAt": "2025-01-03T00:00:00+00:00",
        "updatedAt": "2025-01-03T00:00:00+00:00",
    }]


def test_failed_workspace_preparation_cleans_up_and_leaves_retryable_request(tmp_path):
    markdown, _, service = _service(tmp_path)
    _create(service)
    cleanup_calls = []
    prepared = {
        "ok": False,
        "error": "Unable to initialize repository",
        "path": "/tmp/partial-workspace",
        "managed": True,
        "created": True,
    }

    result = service.confirm_and_materialize(
        "request-1",
        expected_revision=1,
        confirmation_key="confirm:workspace-1",
        prepare_workspace=lambda *_: prepared,
        cleanup_workspace=cleanup_calls.append,
    )

    assert result["ok"] is False
    assert result["code"] == "workspace_preparation_failed"
    assert cleanup_calls == [prepared]
    root = markdown.load_all()
    assert root["projects"] == []
    assert root[REQUESTS_KEY]["request-1"]["state"] == "failed"
    assert root[REQUESTS_KEY]["request-1"]["approvedSnapshot"]["title"] == "Launch"


def test_failed_root_commit_cleans_managed_workspace_and_records_failure(tmp_path):
    markdown, _, service = _service(tmp_path)
    _create(service)
    original_update = service.store.update
    update_calls = {"count": 0}
    cleanup_calls = []

    def flaky_update(mutator):
        update_calls["count"] += 1
        if update_calls["count"] == 2:
            raise OSError("simulated root commit failure")
        return original_update(mutator)

    service.store.update = flaky_update
    workspace = {
        "ok": True,
        "path": "/tmp/new-managed-workspace",
        "managed": True,
        "created": True,
    }
    result = service.confirm_and_materialize(
        "request-1",
        expected_revision=1,
        confirmation_key="confirm:commit-1",
        prepare_workspace=lambda *_: workspace,
        cleanup_workspace=cleanup_calls.append,
    )

    assert result["ok"] is False
    assert result["code"] == "materialization_failed"
    assert cleanup_calls == [workspace]
    root = markdown.load_all()
    assert root["projects"] == []
    assert root[REQUESTS_KEY]["request-1"]["state"] == "failed"


def test_missing_referenced_template_fails_without_partial_root_changes(tmp_path):
    markdown, _, service = _service(tmp_path)
    reusable = _draft()
    reusable.update({
        "projectType": "reusable",
        "template": {"mode": "reference", "templateId": "missing", "version": 1},
    })
    _create(service, draft=reusable)

    result = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:template-1",
    )

    assert result["ok"] is False
    assert result["code"] == "template_version_not_found"
    root = markdown.load_all()
    assert root["projects"] == []
    assert root[TEMPLATES_KEY] == {}
    assert root[RECURRENCES_KEY] == {}
    assert root[OUTBOX_KEY] == []
