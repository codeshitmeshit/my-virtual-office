#!/usr/bin/env python3
"""Project authoring request state-machine and idempotency tests."""

import copy
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
        "projectExecutionEnabled": False,
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
    edited["projectExecutionEnabled"] = True
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


def test_enabled_confirmation_requires_workspace_and_never_downgrades(tmp_path):
    markdown, _, service = _service(tmp_path)
    enabled = _draft()
    enabled.pop("projectExecutionEnabled")
    _create(service, draft=enabled)

    result = service.confirm_and_materialize(
        "request-1",
        expected_revision=1,
        confirmation_key="confirm:enabled-no-workspace",
    )

    assert result["ok"] is False
    assert result["code"] == "workspace_preparation_required"
    root = markdown.load_all()
    assert root["projects"] == []
    assert root[REQUESTS_KEY]["request-1"]["approvedSnapshot"]["projectExecutionEnabled"] is True


def test_tracking_only_confirmation_skips_workspace_preparation(tmp_path):
    _, _, service = _service(tmp_path)
    _create(service)
    calls = []

    result = service.confirm_and_materialize(
        "request-1",
        expected_revision=1,
        confirmation_key="confirm:tracking-only",
        prepare_workspace=lambda *_: calls.append(True) or {"ok": False},
    )

    assert result["ok"] is True
    assert result["project"]["projectExecutionEnabled"] is False
    assert calls == []


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
    enabled = _draft()
    enabled["projectExecutionEnabled"] = True
    _create(service, draft=enabled)
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
    enabled = _draft()
    enabled["projectExecutionEnabled"] = True
    _create(service, draft=enabled)
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


def test_manual_template_instantiation_is_version_pinned_atomic_and_idempotent(tmp_path):
    markdown, _, service = _service(tmp_path)
    reusable = _draft("Reusable launch")
    reusable.update({
        "projectType": "reusable",
        "template": {"mode": "create", "name": "Launch template"},
    })
    _create(service, draft=reusable)
    source = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:template-source",
    )["project"]
    root_before = markdown.load_all()
    snapshot_before = copy.deepcopy(
        root_before[TEMPLATES_KEY]["template-request-1"][0]["snapshot"],
    )

    created = service.instantiate_template(
        "template-request-1",
        1,
        idempotency_key="template:manual-1",
        overrides={"title": "Independent launch", "dueDate": "2025-05-01"},
        actor="user:local",
    )
    repeated = service.instantiate_template(
        "template-request-1",
        1,
        idempotency_key="template:manual-1",
        overrides={"title": "Ignored retry"},
        actor="user:local",
    )

    assert created["created"] is True
    assert repeated["created"] is False
    assert created["project"]["id"] == repeated["project"]["id"]
    assert created["project"]["id"] != source["id"]
    assert created["project"]["title"] == "Independent launch"
    assert created["project"]["templateRef"] == {"id": "template-request-1", "version": 1}
    assert created["project"]["authoringSource"] == {
        "kind": "manual_template_instance",
        "templateId": "template-request-1",
        "templateVersion": 1,
    }
    task = created["project"]["tasks"][0]
    assert task["responsibleActor"] == {"type": "agent", "id": "owner"}
    assert task["executorActor"] == {"type": "agent", "id": "builder"}
    assert task["executionState"] == "backlog"
    assert task["attempts"] == []
    root = markdown.load_all()
    assert len(root["projects"]) == 2
    assert root[TEMPLATES_KEY]["template-request-1"][0]["snapshot"] == snapshot_before


def test_manual_template_instantiation_revalidates_actors_without_partial_project(tmp_path):
    markdown, _, service = _service(tmp_path)
    reusable = _draft("Reusable launch")
    reusable.update({
        "projectType": "reusable",
        "template": {"mode": "create", "name": "Launch template"},
    })
    _create(service, draft=reusable)
    service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:template-source",
    )
    before = copy.deepcopy(markdown.load_all()["projects"])
    service.lookup_agent = lambda agent_id: None if agent_id == "builder" else AGENTS.get(agent_id)

    with pytest.raises(ProjectAuthoringCommandError) as invalid:
        service.instantiate_template(
            "template-request-1", 1,
            idempotency_key="template:invalid-actor",
            actor="user:local",
        )

    assert invalid.value.code == "agent_not_found"
    assert markdown.load_all()["projects"] == before


@pytest.mark.parametrize(
    ("maintenance_mode", "allows_routine_update"),
    (("strict_confirmation", False), ("autonomous", True)),
)
def test_confirmed_project_persists_mode_and_hash_only_scoped_grant(
    tmp_path, maintenance_mode, allows_routine_update,
):
    markdown, _, service = _service(tmp_path)
    draft = _draft()
    draft["agentMaintenanceMode"] = maintenance_mode
    plaintext = "one-time-project-secret"
    _create(service, draft=draft, request_secret_hash=hash_request_secret(plaintext))

    result = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:grant-mode",
    )
    root = markdown.load_all()
    project = root["projects"][0]
    grant = root["projectAuthoringGrants"][project["id"]]

    assert result["project"]["agentMaintenanceMode"] == maintenance_mode
    assert project["agentMaintenanceMode"] == maintenance_mode
    assert grant["projectId"] == project["id"]
    assert grant["requestingAgentId"] == "author"
    assert grant["maintenanceMode"] == maintenance_mode
    assert grant["secretHash"].startswith("sha256:")
    assert plaintext not in grant["secretHash"]
    assert ("routine_task_update" in grant["allowedOperations"]) is allows_routine_update
    public = service.authenticate_project_grant(
        project["id"], requesting_agent_id="author", grant_secret=plaintext,
    )
    assert "secretHash" not in public


def test_strict_maintenance_request_is_idempotent_and_applies_only_after_confirmation(tmp_path):
    markdown, _, service = _service(tmp_path)
    secret = "strict-maintenance-secret"
    _create(service, request_secret_hash=hash_request_secret(secret))
    materialized = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:maintenance",
    )
    project_id = materialized["project"]["id"]
    mutation = {"operation": "update_project", "changes": {"title": "Managed title"}}

    requested = service.create_maintenance_request(
        project_id,
        mutation,
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="maintenance:key-1",
    )
    repeated = service.create_maintenance_request(
        project_id,
        {"invalid": "retry payload is ignored"},
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="maintenance:key-1",
    )

    assert requested["created"] is True
    assert repeated["created"] is False
    assert repeated["request"]["id"] == requested["request"]["id"]
    assert markdown.load_all()["projects"][0]["title"] == "Launch"

    applied = service.confirm_maintenance_request(
        project_id,
        requested["request"]["id"],
        expected_revision=1,
        actor="user:local",
    )
    assert applied["project"]["title"] == "Managed title"
    assert applied["request"]["state"] == "confirmed"
    assert markdown.load_all()["projects"][0]["title"] == "Managed title"


def test_autonomous_protected_role_change_stays_pending_and_revalidates_actors(tmp_path):
    markdown, _, service = _service(tmp_path)
    draft = _draft()
    draft["agentMaintenanceMode"] = "autonomous"
    secret = "autonomous-maintenance-secret"
    _create(service, draft=draft, request_secret_hash=hash_request_secret(secret))
    project = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:autonomous",
    )["project"]
    task_id = project["tasks"][0]["id"]

    pending = service.create_maintenance_request(
        project["id"],
        {
            "operation": "reassign_roles",
            "taskId": task_id,
            "changes": {"executorActor": {"type": "agent", "id": "owner"}},
        },
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="maintenance:roles-1",
    )
    stored_task = markdown.load_all()["projects"][0]["tasks"][0]
    assert stored_task["executorActor"]["id"] == "builder"

    applied = service.confirm_maintenance_request(
        project["id"], pending["request"]["id"], expected_revision=1,
    )
    assert applied["project"]["tasks"][0]["executorActor"]["id"] == "owner"
    assert applied["project"]["tasks"][0]["executorAgentId"] == "owner"


def test_invalid_maintenance_application_is_atomic_and_revoked_grant_cannot_request(tmp_path):
    markdown, _, service = _service(tmp_path)
    secret = "maintenance-failure-secret"
    _create(service, request_secret_hash=hash_request_secret(secret))
    project = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:failure",
    )["project"]
    pending = service.create_maintenance_request(
        project["id"],
        {"operation": "update_project", "changes": {"id": "forbidden"}},
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="maintenance:invalid-1",
    )

    with pytest.raises(ProjectAuthoringCommandError) as invalid:
        service.confirm_maintenance_request(
            project["id"], pending["request"]["id"], expected_revision=1,
        )
    assert invalid.value.code == "protected_maintenance_field"
    root = markdown.load_all()
    assert root["projects"][0]["id"] == project["id"]
    grant_request = root["projectAuthoringGrants"][project["id"]]["maintenanceRequests"][pending["request"]["id"]]
    assert grant_request["state"] == "pending"

    service.revoke_project_grant(project["id"])
    with pytest.raises(ProjectAuthoringCommandError) as revoked:
        service.create_maintenance_request(
            project["id"],
            {"operation": "archive_project"},
            requesting_agent_id="author",
            grant_secret=secret,
            idempotency_key="maintenance:revoked-1",
        )
    assert revoked.value.code == "invalid_project_grant"


def test_autonomous_assigned_agent_can_apply_only_routine_task_fields(tmp_path):
    markdown, _, service = _service(tmp_path)
    draft = _draft()
    draft["agentMaintenanceMode"] = "autonomous"
    draft["tasks"][0]["responsibleActor"] = {"type": "agent", "id": "author"}
    draft["tasks"][0]["executorActor"] = {"type": "agent", "id": "author"}
    secret = "autonomous-routine-secret"
    _create(service, draft=draft, request_secret_hash=hash_request_secret(secret))
    project = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:routine",
    )["project"]
    task_id = project["tasks"][0]["id"]

    updated = service.apply_autonomous_routine_update(
        project["id"],
        task_id,
        {
            "description": "Updated autonomously",
            "executionState": "in_progress",
            "evidence": {"summary": "Work started"},
            "dueDate": "2025-04-01",
        },
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="routine:update-1",
    )
    repeated = service.apply_autonomous_routine_update(
        project["id"],
        task_id,
        {"reviewerActor": {"type": "agent", "id": "reviewer"}},
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="routine:update-1",
    )

    assert updated["created"] is True
    assert repeated["created"] is False
    stored = markdown.load_all()["projects"][0]["tasks"][0]
    assert stored["description"] == "Updated autonomously"
    assert stored["executionState"] == "in_progress"
    assert stored["evidence"] == {"summary": "Work started"}
    assert stored["maintenanceHistory"][-1]["changedFields"] == [
        "description", "dueDate", "evidence", "executionState",
    ]
    assert len(stored["maintenanceHistory"]) == 1


@pytest.mark.parametrize(
    "forbidden_field",
    ("reviewerActor", "executorActor", "workspacePath", "status", "tasks", "agentMaintenanceMode"),
)
def test_autonomous_routine_update_rejects_structural_and_role_fields(tmp_path, forbidden_field):
    markdown, _, service = _service(tmp_path)
    draft = _draft()
    draft["agentMaintenanceMode"] = "autonomous"
    draft["tasks"][0]["executorActor"] = {"type": "agent", "id": "author"}
    secret = "autonomous-forbidden-secret"
    _create(service, draft=draft, request_secret_hash=hash_request_secret(secret))
    project = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:forbidden",
    )["project"]
    before = markdown.load_all()["projects"][0]

    with pytest.raises(ProjectAuthoringCommandError) as rejected:
        service.apply_autonomous_routine_update(
            project["id"],
            project["tasks"][0]["id"],
            {forbidden_field: "attempted escalation"},
            requesting_agent_id="author",
            grant_secret=secret,
            idempotency_key=f"routine:forbidden-{forbidden_field}",
        )

    assert rejected.value.code == "autonomous_field_not_allowed"
    assert markdown.load_all()["projects"][0] == before


def test_autonomous_routine_update_rejects_strict_unassigned_and_revoked_grants(tmp_path):
    markdown, _, service = _service(tmp_path)
    secret = "routine-denied-secret"
    _create(service, request_secret_hash=hash_request_secret(secret))
    project = service.confirm_and_materialize(
        "request-1", expected_revision=1, confirmation_key="confirm:strict-denied",
    )["project"]
    task_id = project["tasks"][0]["id"]

    with pytest.raises(ProjectAuthoringCommandError) as strict:
        service.apply_autonomous_routine_update(
            project["id"], task_id, {"description": "No"},
            requesting_agent_id="author", grant_secret=secret,
            idempotency_key="routine:strict-denied",
        )
    assert strict.value.code == "invalid_project_grant"

    service.confirm_maintenance_request(
        project["id"],
        service.create_maintenance_request(
            project["id"],
            {"operation": "maintenance_mode_change", "changes": {"agentMaintenanceMode": "autonomous"}},
            requesting_agent_id="author", grant_secret=secret,
            idempotency_key="maintenance:enable-auto",
        )["request"]["id"],
        expected_revision=1,
    )
    with pytest.raises(ProjectAuthoringCommandError) as unassigned:
        service.apply_autonomous_routine_update(
            project["id"], task_id, {"description": "No"},
            requesting_agent_id="author", grant_secret=secret,
            idempotency_key="routine:unassigned",
        )
    assert unassigned.value.code == "agent_not_assigned_to_task"

    service.revoke_project_grant(project["id"])
    with pytest.raises(ProjectAuthoringCommandError) as revoked:
        service.apply_autonomous_routine_update(
            project["id"], task_id, {"description": "No"},
            requesting_agent_id="author", grant_secret=secret,
            idempotency_key="routine:revoked",
        )
    assert revoked.value.code == "invalid_project_grant"
    assert markdown.load_all()["projects"][0]["tasks"][0]["description"] != "No"
