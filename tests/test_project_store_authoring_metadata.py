#!/usr/bin/env python3
"""Persistence coverage for project-authoring root metadata and defaults."""

import json
import os
import stat
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore, ROOT_METADATA_FILENAME
from services.project_repository import ProjectRepository


def _project(project_id="project-1", *, tasks=None):
    return {
        "id": project_id,
        "title": "Authored project",
        "description": "Created from a confirmed request",
        "columns": [{"id": "todo", "title": "Todo"}],
        "tasks": tasks or [],
        "activity": [],
    }


def test_authoring_root_collections_round_trip_and_are_bounded(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    root = {
        "projects": [_project()],
        "templates": [{"id": "legacy-template", "title": "Legacy"}],
        "projectAuthoringRequests": {"request-1": {"state": "pending"}},
        "projectAuthoringIdempotency": {"agent-1:key-1": "request-1"},
        "projectAuthoringGrants": {"project-1": {"secretHash": "sha256:abc"}},
        "projectTemplateVersions": {"template-1": [{"version": 1}]},
        "projectRecurrences": {"recurrence-1": {"state": "active"}},
        "projectAuthoringOutbox": [{"id": "intent-1", "state": "pending"}],
        "unboundedUnknownCollection": {"must": "not persist"},
    }

    store.save_all(root)
    loaded = MarkdownProjectStore(str(tmp_path)).load_all()

    for key in (
        "templates",
        "projectAuthoringRequests",
        "projectAuthoringIdempotency",
        "projectAuthoringGrants",
        "projectTemplateVersions",
        "projectRecurrences",
        "projectAuthoringOutbox",
    ):
        assert loaded[key] == root[key]
    assert "unboundedUnknownCollection" not in loaded

    metadata_path = tmp_path / ROOT_METADATA_FILENAME
    assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600


def test_damaged_root_metadata_is_repaired_without_losing_projects(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [_project()], "templates": []})
    metadata_path = tmp_path / ROOT_METADATA_FILENAME
    metadata_path.write_text(
        json.dumps({
            "templates": "invalid",
            "projectAuthoringRequests": {"request-1": {"state": "pending"}},
            "unknown": ["discard me"],
        }),
        encoding="utf-8",
    )
    metadata_path.chmod(0o644)

    loaded = store.load_all()

    assert [project["id"] for project in loaded["projects"]] == ["project-1"]
    assert loaded["templates"] == []
    assert loaded["projectAuthoringRequests"] == {"request-1": {"state": "pending"}}
    repaired = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert set(repaired) == {
        "templates",
        "projectAuthoringRequests",
        "projectAuthoringIdempotency",
        "projectAuthoringGrants",
        "projectTemplateVersions",
        "projectRecurrences",
        "projectAuthoringOutbox",
    }
    assert repaired["templates"] == []
    assert "unknown" not in repaired
    assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600


def test_authoring_project_and_task_fields_round_trip_with_legacy_actor_defaults(tmp_path):
    typed_task = {
        "id": "typed-task",
        "title": "Typed roles",
        "columnId": "todo",
        "responsibleActor": {"type": "user", "id": "user:local"},
        "executorActor": {"type": "agent", "id": "builder"},
        "reviewerActor": {"type": "agent", "id": "reviewer"},
        "reviewerRecommendation": {"recommended": True, "reason": "critical delivery"},
    }
    legacy_task = {
        "id": "legacy-task",
        "title": "Legacy roles",
        "columnId": "todo",
        "assignee": "owner-agent",
        "executorAgentId": "executor-agent",
    }
    project = _project(tasks=[typed_task, legacy_task])
    project.update({
        "agentMaintenanceMode": "autonomous",
        "authoringAgentId": "author-agent",
        "authoringRequestId": "request-1",
        "authoringSource": {"kind": "confirmed_draft"},
        "templateRef": {"id": "template-1", "version": 3},
        "recurrenceRef": {"id": "recurrence-1", "occurrenceId": "occurrence-9"},
    })
    store = MarkdownProjectStore(str(tmp_path))

    store.save_all({"projects": [project], "templates": []})
    loaded = store.load_all()["projects"][0]

    assert loaded["agentMaintenanceMode"] == "autonomous"
    assert loaded["authoringAgentId"] == "author-agent"
    assert loaded["authoringRequestId"] == "request-1"
    assert loaded["authoringSource"] == {"kind": "confirmed_draft"}
    assert loaded["templateRef"] == {"id": "template-1", "version": 3}
    assert loaded["recurrenceRef"] == {"id": "recurrence-1", "occurrenceId": "occurrence-9"}

    tasks = {task["id"]: task for task in loaded["tasks"]}
    assert tasks["typed-task"]["responsibleActor"] == {"type": "user", "id": "user:local"}
    assert tasks["typed-task"]["executorActor"] == {"type": "agent", "id": "builder"}
    assert tasks["typed-task"]["reviewerActor"] == {"type": "agent", "id": "reviewer"}
    assert tasks["typed-task"]["reviewerRecommendation"] == {
        "recommended": True,
        "reason": "critical delivery",
    }
    assert tasks["legacy-task"]["responsibleActor"] == {"type": "agent", "id": "owner-agent"}
    assert tasks["legacy-task"]["executorActor"] == {"type": "agent", "id": "executor-agent"}
    assert tasks["legacy-task"]["reviewerActor"] is None


def test_legacy_projects_receive_conservative_authoring_defaults(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [_project()], "templates": []})

    loaded = store.load_all()["projects"][0]

    assert loaded["agentMaintenanceMode"] == "strict_confirmation"
    assert loaded["authoringAgentId"] is None
    assert loaded["authoringRequestId"] is None
    assert loaded["authoringSource"] == {}
    assert loaded["templateRef"] == {}
    assert loaded["recurrenceRef"] == {}


def test_repository_root_update_persists_authoring_metadata_across_store_instances(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [_project()], "templates": []})
    repository = ProjectRepository(
        load_projects=store.load_all,
        save_projects=store.save_all,
        cache_namespace=lambda: (store, store.revision()),
    )

    repository.update_root(
        lambda root: root["projectAuthoringRequests"].update({
            "request-2": {"state": "confirmed", "projectId": "project-1"},
        })
    )

    restarted = MarkdownProjectStore(str(tmp_path)).load_all()
    assert restarted["projectAuthoringRequests"] == {
        "request-2": {"state": "confirmed", "projectId": "project-1"},
    }


def test_external_root_metadata_edit_invalidates_repository_cache(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [_project()], "templates": []})
    store.poll_external_revision()
    repository = ProjectRepository(
        load_projects=store.load_all,
        save_projects=store.save_all,
        cache_namespace=lambda: (store, store.revision()),
    )
    assert repository.load_all()["projectRecurrences"] == {}

    metadata_path = tmp_path / ROOT_METADATA_FILENAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["projectRecurrences"] = {"recurrence-2": {"state": "paused"}}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert store.poll_external_revision()["changed"] is True

    assert repository.load_all()["projectRecurrences"] == {
        "recurrence-2": {"state": "paused"},
    }
