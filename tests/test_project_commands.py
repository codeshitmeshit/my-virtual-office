#!/usr/bin/env python3
"""Direct contract tests for project and task command services."""

import copy
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import project_commands
from services.project_repository import ProjectRepository


class MemoryStore:
    def __init__(self):
        self.data = {"projects": [], "templates": []}

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.data = copy.deepcopy(value)


def dependencies():
    store = MemoryStore()
    repo = ProjectRepository(load_projects=store.load, save_projects=store.save)
    ids = iter(f"id-{index}" for index in range(100))
    activity = []

    def log(project, event, by, detail, task_id=None):
        record = {"id": next(ids), "type": event, "by": by, "detail": detail}
        if task_id:
            record["taskId"] = task_id
        project.setdefault("activity", []).append(record)
        activity.append(record)

    return store, repo, {
        "new_id": lambda: next(ids),
        "now": lambda: "now",
        "log_activity": log,
        "is_archive_manager": lambda value: value == "archive-manager",
    }


def create_project(repo, common, **overrides):
    body = {"title": "Project", **overrides}
    return project_commands.create_project(
        body,
        repository=repo,
        prepare_workspace=lambda title, value, now: {
            "ok": True, "projectExecutionEnabled": bool(value.get("projectExecutionEnabled")),
            "workspacePath": value.get("workspacePath"), "workspaceKind": None,
            "workspaceStatus": {}, "workspaceManagedBy": None, "workspaceCreatedAt": None,
        },
        archive_maintenance_default=lambda project: True,
        **common,
    )


def test_create_project_and_task_preserve_contract_without_http():
    _, repo, common = dependencies()
    project_outcome = create_project(repo, common)
    assert project_outcome.result.status == 200
    project = project_outcome.result.payload["project"]
    task_outcome = project_commands.create_task(
        project["id"], {"title": "Task", "assignee": "executor"}, repository=repo, **common
    )
    assert task_outcome.result.status == 200
    task = task_outcome.result.payload["task"]
    assert task["executionState"] == "backlog"
    assert repo.get(project["id"])["tasks"][0]["id"] == task["id"]


def test_command_validation_and_missing_resources_are_compatible():
    _, repo, common = dependencies()
    assert create_project(repo, common, title="").result.status == 400
    assert create_project(repo, common, defaultExecutorAgentId="archive-manager").result.payload["code"] == "archive_manager_not_assignable"
    assert project_commands.create_task("missing", {"title": "Task"}, repository=repo, **common).result.status == 404
    assert project_commands.add_task_comment("missing", "task", {"text": "x"}, repository=repo, log_activity=common["log_activity"], new_id=common["new_id"], now=common["now"]).result.status == 404


def test_comment_columns_update_and_delete_use_repository():
    _, repo, common = dependencies()
    project = create_project(repo, common).result.payload["project"]
    task = project_commands.create_task(project["id"], {"title": "Task"}, repository=repo, **common).result.payload["task"]
    comment = project_commands.add_task_comment(project["id"], task["id"], {"text": "hello"}, repository=repo, log_activity=common["log_activity"], new_id=common["new_id"], now=common["now"])
    assert comment.result.payload["comment"]["text"] == "hello"
    columns = project_commands.update_columns(project["id"], {"columns": [{"title": "Only"}]}, repository=repo, log_activity=common["log_activity"], new_id=common["new_id"], now=common["now"])
    assert columns.result.payload["columns"][0]["order"] == 0
    assert project_commands.delete_task(project["id"], task["id"], repository=repo, now=common["now"]).result.status == 200
    assert project_commands.delete_task(project["id"], task["id"], repository=repo, now=common["now"]).result.status == 404


def test_update_and_reorder_enforce_execution_column_gates():
    _, repo, common = dependencies()
    project = create_project(repo, common, projectExecutionEnabled=True).result.payload["project"]
    task = project_commands.create_task(project["id"], {"title": "Task"}, repository=repo, **common).result.payload["task"]
    repo.update(project["id"], lambda value: next(item for item in value["tasks"] if item["id"] == task["id"]).update({"executionState": "executing"}))
    update = project_commands.update_task(
        project["id"], task["id"], {"columnId": project["columns"][-1]["id"]},
        repository=repo, is_archive_manager=common["is_archive_manager"], execution_enabled=lambda value: value.get("projectExecutionEnabled") is True,
        column_locked=lambda value: value.get("executionState") == "executing", checklist_complete=lambda value: False,
        can_complete_after_checklist=lambda value: False, mark_done=lambda *args: {"ok": False}, log_activity=common["log_activity"],
        now=common["now"], is_on_time=lambda value: False,
        score_values={"task_completed": 1, "critical": 0, "high": 0, "medium": 0, "on_time": 0, "checklist": 0},
    )
    assert update.result.status == 409
    assert update.result.payload["code"] == "project_execution_column_locked"


def test_project_commands_module_has_no_server_or_http_dependency():
    path = os.path.join(APP_DIR, "services", "project_commands.py")
    with open(path, encoding="utf-8") as source_file:
        source = source_file.read()
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source


def test_project_update_cannot_forge_managed_workspace_metadata():
    _, repo, common = dependencies()
    project = create_project(repo, common).result.payload["project"]
    outcome = project_commands.update_project(
        project["id"], {"workspaceManagedBy": "system", "workspaceCreatedAt": "forged", "workspacePath": "/tmp/victim"},
        repository=repo, is_archive_manager=common["is_archive_manager"], execution_enabled=lambda value: False,
        validate_workspace=lambda value: {"ok": True, "path": value, "kind": "directory"}, log_activity=common["log_activity"], now=common["now"],
    )
    assert outcome.result.status == 200
    stored = repo.get(project["id"])
    assert stored.get("workspaceManagedBy") is None
    assert stored.get("workspaceCreatedAt") is None


def test_invalid_project_ids_keep_not_found_contract():
    _, repo, common = dependencies()
    for project_id in (" ", "../escape", "bad\x01id", "x" * 257):
        outcome = project_commands.create_task(project_id, {"title": "Task"}, repository=repo, **common)
        assert outcome.result.status == 404
