#!/usr/bin/env python3
"""Versioned project-template snapshot and legacy adapter tests."""

import copy
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_templates import (
    ProjectTemplateError,
    adapt_legacy_template,
    append_template_version,
    build_template_snapshot,
    resolve_template_version,
)


def _draft(title="Release", description="Ship safely"):
    return {
        "title": title,
        "description": description,
        "projectType": "reusable",
        "priority": "high",
        "tags": ["release"],
        "columns": [
            {"id": "todo", "title": "Todo", "color": "#123456"},
            {"id": "done", "title": "Done", "color": "#654321"},
        ],
        "tasks": [{
            "id": "task-blueprint",
            "title": "Implement",
            "description": "Build the change",
            "columnId": "todo",
            "priority": "high",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerActor": {"type": "agent", "id": "reviewer"},
            "reviewerRecommendation": {
                "recommended": True,
                "triggers": ["critical_delivery"],
                "rationale": "Release gate",
                "candidate": {"type": "agent", "id": "reviewer"},
            },
            "requiresUserAcceptance": True,
            "allowReviewerlessExecution": False,
            "scheduledRepeatEnabled": False,
            "executionState": "in_progress",
            "attempts": [{"id": "runtime-attempt"}],
        }],
        "agentMaintenanceMode": "autonomous",
        "projectExecutionEnabled": True,
        "projectExecutionStartMode": "continuous",
        "executionPolicy": {"maxActiveTasks": 2},
        "defaultExecutorAgentId": "builder",
        "defaultReviewerAgentId": "reviewer",
    }


def test_snapshot_contains_complete_blueprints_roles_reviewer_and_execution_policy():
    snapshot = build_template_snapshot(_draft())
    task = snapshot["tasks"][0]

    assert snapshot["schemaVersion"] == 1
    assert snapshot["columns"][0]["id"] == "todo"
    assert task["responsibleActor"] == {"type": "agent", "id": "owner"}
    assert task["executorActor"] == {"type": "agent", "id": "builder"}
    assert task["reviewerActor"] == {"type": "agent", "id": "reviewer"}
    assert task["reviewerRecommendation"]["triggers"] == ["critical_delivery"]
    assert task["requiresUserAcceptance"] is True
    assert "executionState" not in task
    assert "attempts" not in task
    assert snapshot["reviewerPolicy"] == "optional_user_confirmed_per_task"
    assert snapshot["agentMaintenanceMode"] == "autonomous"
    assert snapshot["executionSettings"] == {
        "projectExecutionEnabled": True,
        "projectExecutionStartMode": "continuous",
        "executionPolicy": {"maxActiveTasks": 2},
        "defaultExecutorAgentId": "builder",
        "defaultReviewerAgentId": "reviewer",
    }


def test_append_only_versions_do_not_mutate_prior_snapshots():
    versions = []
    first_draft = _draft()
    first = append_template_version(
        versions,
        template_id="template-release",
        name="Release",
        draft=first_draft,
        created_at="2025-01-01T00:00:00Z",
        created_by="user:local",
        source_request_id="request-1",
    )
    persisted_first = copy.deepcopy(versions[0])
    first_draft["tasks"][0]["title"] = "Caller mutation"
    first["snapshot"]["title"] = "Return mutation"

    second = append_template_version(
        versions,
        template_id="template-release",
        name="Release v2",
        draft=_draft("Release v2", "Updated"),
        created_at="2025-01-02T00:00:00Z",
        created_by="user:local",
        source_request_id="request-2",
    )

    assert versions[0] == persisted_first
    assert versions[0]["snapshot"]["tasks"][0]["title"] == "Implement"
    assert second["version"] == 2
    assert second["snapshotDigest"] != first["snapshotDigest"]


def test_legacy_browser_template_is_readable_as_implicit_v1_without_mutation():
    legacy = {
        "id": "legacy-template",
        "title": "Legacy",
        "description": "Existing browser template",
        "columns": [{"title": "Backlog", "color": "#666"}],
        "taskTemplates": [{
            "title": "Old task",
            "columnIndex": 0,
            "priority": "medium",
        }],
    }
    original = copy.deepcopy(legacy)

    version = adapt_legacy_template(legacy)
    resolved = resolve_template_version({}, [legacy], "legacy-template", 1)

    assert legacy == original
    assert version == resolved
    assert version["version"] == 1 and version["legacy"] is True
    assert version["snapshot"]["columns"][0]["id"] == "column-1"
    task = version["snapshot"]["tasks"][0]
    assert task["columnId"] == "column-1"
    assert task["responsibleActor"] is None
    assert task["executorActor"] is None
    with pytest.raises(ProjectTemplateError) as missing:
        resolve_template_version({}, [legacy], "legacy-template", 2)
    assert missing.value.code == "template_version_not_found"


def test_explicit_version_takes_precedence_over_same_id_legacy_template():
    explicit = append_template_version(
        [],
        template_id="shared",
        name="Explicit",
        draft=_draft(),
        created_at="2025-01-01T00:00:00Z",
        created_by="user:local",
    )
    legacy = {"id": "shared", "title": "Legacy", "columns": [], "taskTemplates": []}

    resolved = resolve_template_version({"shared": [explicit]}, [legacy], "shared", 1)

    assert resolved["name"] == "Explicit"
    assert resolved.get("legacy") is not True

