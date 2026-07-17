#!/usr/bin/env python3
"""Sanitized project-authoring audit coverage."""

from datetime import datetime, timezone
import json
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_authoring import ProjectAuthoringCommandError, ProjectAuthoringService
from services.project_authoring_audit import build_audit_event, sanitize_audit_text
from services.project_authoring_security import hash_request_secret
from services.project_authoring_store import GRANTS_KEY, REQUESTS_KEY, ProjectAuthoringRootStore
from services.project_repository import ProjectRepository


AGENTS = {agent_id: {"id": agent_id} for agent_id in ("author", "owner", "builder")}


def _draft(*, autonomous=False):
    responsible = "author" if autonomous else "owner"
    executor = "author" if autonomous else "builder"
    return {
        "title": "Audited project",
        "description": "Safe description",
        "projectType": "one_time",
        "agentMaintenanceMode": "autonomous" if autonomous else "strict_confirmation",
        "columns": [{"id": "backlog", "title": "Backlog"}],
        "tasks": [{
            "title": "Audited task",
            "columnId": "backlog",
            "responsibleActor": {"type": "agent", "id": responsible},
            "executorActor": {"type": "agent", "id": executor},
            "reviewerRecommendation": {"recommended": False, "triggers": []},
        }],
        "template": {"mode": "none"},
        "recurrence": {"enabled": False},
    }


def _service(path, *, autonomous=False):
    path.mkdir()
    markdown = MarkdownProjectStore(str(path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    sequence = iter(datetime(2025, 2, day, tzinfo=timezone.utc) for day in range(1, 28))
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda _agent_id: False,
        submission_enabled=lambda: True,
        clock=lambda: next(sequence),
        new_id=lambda: "audit-1",
    )
    secret = "plaintext-project-secret"
    service.create_pending(
        _draft(autonomous=autonomous),
        requesting_agent_id="author",
        idempotency_key="audit:key-1",
        request_secret_hash=hash_request_secret(secret),
        source={"surface": "skill"},
    )
    return markdown, service, secret


def test_audit_builder_redacts_credentials_bounds_values_and_drops_unknown_context():
    raw = (
        "Authorization: Bearer auth-value token=token-value secret: secret-value "
        "password=password-value cookie=session-value api_key=key-value Bearer loose-value"
    )

    sanitized = sanitize_audit_text(raw, limit=90)
    event = build_audit_event(
        "failed", raw, "system", "2025-01-01T00:00:00Z", "failed",
        error=raw, requestId="request-1", unknown="must-not-persist",
    )
    encoded = json.dumps(event)

    for credential in (
        "auth-value", "token-value", "secret-value", "password-value",
        "session-value", "key-value", "loose-value", "must-not-persist",
    ):
        assert credential not in sanitized
        assert credential not in encoded
    assert "[REDACTED]" in sanitized
    assert sanitized.endswith("...[truncated]")
    assert event["requestId"] == "request-1"


def test_draft_confirmation_materialization_and_rejection_events_include_safe_ids(tmp_path):
    confirmed_store, confirmed, secret = _service(tmp_path / "confirmed")
    result = confirmed.confirm_and_materialize(
        "audit-1", expected_revision=1, confirmation_key="confirm:audit",
        actor="user:local",
    )
    request = confirmed_store.load_all()[REQUESTS_KEY]["audit-1"]

    assert [event["action"] for event in request["audit"]] == [
        "draft_submitted", "confirmation_started", "project_materialized",
    ]
    assert all(event["requestId"] == "audit-1" for event in request["audit"])
    assert request["audit"][-1]["projectId"] == result["project"]["id"]

    rejected_store, rejected, _ = _service(tmp_path / "rejected")
    rejected.reject_pending(
        "audit-1", expected_revision=1, reason="Out of scope", actor="user:local",
    )
    rejected_event = rejected_store.load_all()[REQUESTS_KEY]["audit-1"]["audit"][-1]
    assert rejected_event["action"] == "draft_rejected"
    assert rejected_event["requestId"] == "audit-1"

    encoded = json.dumps({"confirmed": request["audit"], "rejected": rejected_event})
    assert secret not in encoded
    assert "requestSecretHash" not in encoded


def test_materialization_and_maintenance_failures_are_sanitized_and_retryable(tmp_path):
    store, service, secret = _service(tmp_path / "failed")
    result = service.confirm_and_materialize(
        "audit-1",
        expected_revision=1,
        confirmation_key="confirm:failed",
        prepare_workspace=lambda *_args: {
            "ok": False,
            "error": "Authorization=Bearer workspace-credential token=other-credential",
        },
    )
    request = store.load_all()[REQUESTS_KEY]["audit-1"]
    encoded = json.dumps(request["audit"])

    assert result["ok"] is False
    assert request["audit"][-1]["action"] == "materialization_failed"
    assert "workspace-credential" not in request["error"]
    assert "other-credential" not in request["error"]
    assert "workspace-credential" not in encoded

    retried = service.confirm_and_materialize(
        "audit-1", expected_revision=3, confirmation_key="confirm:retry",
    )
    project_id = retried["project"]["id"]
    pending = service.create_maintenance_request(
        project_id,
        {"operation": "update_project", "changes": {"id": "forbidden"}},
        requesting_agent_id="author",
        grant_secret=secret,
        idempotency_key="maintenance:audit-failure",
    )["request"]

    with pytest.raises(ProjectAuthoringCommandError):
        service.confirm_maintenance_request(
            project_id,
            pending["id"],
            expected_revision=1,
            actor="user token=management-credential",
        )

    root = store.load_all()
    failed = root[GRANTS_KEY][project_id]["maintenanceRequests"][pending["id"]]
    assert failed["state"] == "pending"
    assert failed["revision"] == 1
    assert failed["audit"][-1]["action"] == "maintenance_apply_failed"
    assert failed["audit"][-1]["projectId"] == project_id
    assert failed["audit"][-1]["maintenanceRequestId"] == pending["id"]
    assert "management-credential" not in json.dumps(failed)


def test_maintenance_success_rejection_and_autonomous_events_are_traceable(tmp_path):
    confirmed_store, service, secret = _service(tmp_path / "maintenance-confirmed")
    project = service.confirm_and_materialize(
        "audit-1", expected_revision=1, confirmation_key="confirm:maintenance",
    )["project"]
    requested = service.create_maintenance_request(
        project["id"],
        {"operation": "update_project", "changes": {"title": "Updated"}},
        requesting_agent_id="author", grant_secret=secret,
        idempotency_key="maintenance:confirmed",
    )["request"]
    service.confirm_maintenance_request(project["id"], requested["id"], expected_revision=1)
    grant = confirmed_store.load_all()[GRANTS_KEY][project["id"]]
    confirmed_events = grant["maintenanceRequests"][requested["id"]]["audit"]
    assert [event["action"] for event in confirmed_events] == [
        "maintenance_requested", "maintenance_confirmed",
    ]
    assert grant["audit"][-1]["action"] == "maintenance_applied"

    rejected_store, rejected_service, rejected_secret = _service(tmp_path / "maintenance-rejected")
    rejected_project = rejected_service.confirm_and_materialize(
        "audit-1", expected_revision=1, confirmation_key="confirm:reject-maintenance",
    )["project"]
    rejected_request = rejected_service.create_maintenance_request(
        rejected_project["id"], {"operation": "archive_project"},
        requesting_agent_id="author", grant_secret=rejected_secret,
        idempotency_key="maintenance:rejected",
    )["request"]
    rejected_service.reject_maintenance_request(
        rejected_project["id"], rejected_request["id"], expected_revision=1,
        reason="Keep active",
    )
    rejected_audit = rejected_store.load_all()[GRANTS_KEY][rejected_project["id"]][
        "maintenanceRequests"
    ][rejected_request["id"]]["audit"]
    assert rejected_audit[-1]["action"] == "maintenance_rejected"

    autonomous_store, autonomous, autonomous_secret = _service(
        tmp_path / "maintenance-autonomous", autonomous=True,
    )
    autonomous_project = autonomous.confirm_and_materialize(
        "audit-1", expected_revision=1, confirmation_key="confirm:autonomous",
    )["project"]
    task_id = autonomous_project["tasks"][0]["id"]
    autonomous.apply_autonomous_routine_update(
        autonomous_project["id"], task_id, {"description": "Done"},
        requesting_agent_id="author", grant_secret=autonomous_secret,
        idempotency_key="maintenance:autonomous",
    )
    event = autonomous_store.load_all()[GRANTS_KEY][autonomous_project["id"]]["audit"][-1]
    assert event["action"] == "autonomous_routine_update"
    assert event["taskId"] == task_id
    assert event["changedFields"] == ["description"]

