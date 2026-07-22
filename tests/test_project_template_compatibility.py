#!/usr/bin/env python3
"""Compatibility coverage between immutable and legacy browser templates."""

import copy
from datetime import datetime, timezone
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-project-template-compatibility-")

import server
from project_store import MarkdownProjectStore
from services.project_authoring import ProjectAuthoringService
from services.project_authoring_store import ProjectAuthoringRootStore, TEMPLATES_KEY
from services.project_repository import ProjectRepository
from services.project_templates import append_template_version


AGENTS = {agent_id: {"id": agent_id} for agent_id in ("owner", "builder", "reviewer")}


def _draft(title, task_title):
    return {
        "title": title,
        "description": f"Description for {title}",
        "projectType": "reusable",
        "columns": [{"id": "todo", "title": "Todo", "color": "#666"}],
        "tasks": [{
            "title": task_title,
            "columnId": "todo",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerActor": {"type": "agent", "id": "reviewer"},
            "reviewerRecommendation": {
                "recommended": True,
                "triggers": ["critical_delivery"],
                "rationale": "Release gate",
                "candidate": {"type": "agent", "id": "reviewer"},
            },
        }],
        "agentMaintenanceMode": "strict_confirmation",
        "projectExecutionEnabled": False,
    }


def _record(versions, title, task_title, version_day):
    return append_template_version(
        versions,
        template_id="template-release",
        name=title,
        draft=_draft(title, task_title),
        created_at=f"2025-01-{version_day:02d}T00:00:00Z",
        created_by="user:local",
    )


def test_new_template_versions_affect_only_future_instances(tmp_path):
    versions = []
    _record(versions, "Release v1", "Task v1", 1)
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({
        "projects": [],
        "templates": [{"id": "template-release", "title": "Release", "version": 1}],
        TEMPLATES_KEY: {"template-release": versions},
    })
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    ids = iter(("instance-v1", "instance-v2"))
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda _agent_id: False,
        clock=lambda: datetime(2025, 2, 1, tzinfo=timezone.utc),
        new_id=lambda: next(ids),
    )

    first = service.instantiate_template(
        "template-release", 1, idempotency_key="template:future-v1",
    )["project"]

    def add_v2(root):
        _record(root[TEMPLATES_KEY]["template-release"], "Release v2", "Task v2", 2)

    service.store.update(add_v2)
    second = service.instantiate_template(
        "template-release", 2, idempotency_key="template:future-v2",
    )["project"]

    persisted = markdown.load_all()["projects"]
    persisted_first = next(item for item in persisted if item["id"] == first["id"])
    assert persisted_first["title"] == "Release v1"
    assert persisted_first["tasks"][0]["title"] == "Task v1"
    assert persisted_first["templateRef"]["version"] == 1
    assert second["title"] == "Release v2"
    assert second["tasks"][0]["title"] == "Task v2"
    assert second["templateRef"]["version"] == 2


def test_browser_template_list_and_creation_accept_latest_version_without_breaking_legacy(monkeypatch):
    versions = []
    _record(versions, "Release v1", "Task v1", 1)
    _record(versions, "Release v2", "Task v2", 2)
    legacy = {
        "id": "legacy-browser",
        "title": "Legacy browser",
        "description": "Existing flat template",
        "columns": [{"title": "Backlog", "color": "#777"}],
        "taskTemplates": [{"title": "Legacy task", "columnIndex": 0}],
    }
    state = {
        "projects": [],
        "templates": [copy.deepcopy(legacy), {"id": "template-release", "title": "Summary"}],
        TEMPLATES_KEY: {"template-release": versions},
    }
    monkeypatch.setattr(server, "_load_projects", lambda: copy.deepcopy(state))

    def save(data):
        state.clear()
        state.update(copy.deepcopy(data))

    monkeypatch.setattr(server, "_save_projects", save)
    monkeypatch.setattr(
        server,
        "_PROJECT_REPOSITORY",
        ProjectRepository(load_projects=lambda: copy.deepcopy(state), save_projects=save),
    )
    generated_ids = iter(("column-new", "task-new", "project-new"))
    monkeypatch.setattr(server, "_proj_uuid", lambda: next(generated_ids))
    monkeypatch.setattr(server, "_proj_now", lambda: "2025-02-01T00:00:00+00:00")

    listed = server._handle_projects_templates()["templates"]
    legacy_listed = next(item for item in listed if item["id"] == "legacy-browser")
    versioned = next(item for item in listed if item["id"] == "template-release")

    assert legacy_listed == legacy
    assert versioned["version"] == 2
    assert versioned["taskTemplates"][0]["title"] == "Task v2"
    assert versioned["taskTemplates"][0]["executorActor"] == {"type": "agent", "id": "builder"}

    created = server._handle_project_from_template({
        "templateId": "template-release",
        "title": "Browser-created versioned project",
    })

    assert created["ok"] is True
    task = created["project"]["tasks"][0]
    assert task["title"] == "Task v2"
    assert task["responsibleActor"] == {"type": "agent", "id": "owner"}
    assert task["executorActor"] == {"type": "agent", "id": "builder"}
    assert task["reviewerActor"] == {"type": "agent", "id": "reviewer"}
    assert created["project"]["templateRef"] == {"id": "template-release", "version": 2}


def test_browser_template_creation_service_has_no_server_dependency():
    path = os.path.join(APP_DIR, "services", "browser_project_creation.py")
    with open(path, encoding="utf-8") as source_file:
        source = source_file.read()
    assert "import server" not in source
    assert "_load_projects" not in source
    assert "_save_projects" not in source
