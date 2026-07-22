#!/usr/bin/env python3
"""Characterize local project CLI materialization before convergence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OFFICE = ROOT / "app" / "office.py"

CLI_PROJECT_KEYS = {
    "activity",
    "branch",
    "columns",
    "createdAt",
    "createdBy",
    "description",
    "dueDate",
    "id",
    "priority",
    "status",
    "tags",
    "tasks",
    "template",
    "title",
    "updatedAt",
}
CLI_TASK_KEYS = {
    "assignee",
    "assigneeBranch",
    "attachments",
    "checklist",
    "columnId",
    "comments",
    "completedAt",
    "createdAt",
    "description",
    "dueDate",
    "id",
    "order",
    "priority",
    "tags",
    "title",
    "updatedAt",
}


def _run_cli(status_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(OFFICE), "--proj", *args],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "VO_STATUS_DIR": str(status_dir),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def _read_projects(status_dir: Path) -> list[dict]:
    return json.loads((status_dir / "projects.json").read_text(encoding="utf-8"))["projects"]


def test_cli_create_empty_project_arguments_output_and_persistence(tmp_path: Path):
    status_dir = tmp_path / "status"
    result = _run_cli(
        status_dir,
        "create",
        "CLI Empty",
        "--desc",
        "Created locally",
        "--priority",
        "high",
        "--due",
        "2026-08-01",
        "--by",
        "operator",
        "--tags",
        "cli, baseline",
        "--branch",
        "feature/cli",
    )

    assert result.returncode == 0, result.stderr
    projects_path = status_dir / "projects.json"
    assert projects_path.is_file()
    assert result.stdout.splitlines() == [
        "✅ Project created: CLI Empty",
        "   ID: " + _read_projects(status_dir)[0]["id"],
        "   Columns: Backlog, To Do, In Progress, Review, Done",
    ]

    project = _read_projects(status_dir)[0]
    assert set(project) == CLI_PROJECT_KEYS
    assert {
        key: project[key]
        for key in (
            "title",
            "description",
            "status",
            "priority",
            "dueDate",
            "createdBy",
            "tags",
            "branch",
            "tasks",
            "activity",
            "template",
        )
    } == {
        "title": "CLI Empty",
        "description": "Created locally",
        "status": "active",
        "priority": "high",
        "dueDate": "2026-08-01",
        "createdBy": "operator",
        "tags": ["cli", "baseline"],
        "branch": "feature/cli",
        "tasks": [],
        "activity": [],
        "template": False,
    }
    assert project["createdAt"] == project["updatedAt"]
    assert [(column["title"], column["color"]) for column in project["columns"]] == [
        ("Backlog", "#6c757d"),
        ("To Do", "#0d6efd"),
        ("In Progress", "#ffc107"),
        ("Review", "#fd7e14"),
        ("Done", "#198754"),
    ]
    assert [column["order"] for column in project["columns"]] == list(range(5))
    assert all(set(column) == {"id", "title", "color", "order"} for column in project["columns"])


def test_cli_create_builtin_template_materializes_template_columns_and_tasks(tmp_path: Path):
    status_dir = tmp_path / "status"
    result = _run_cli(
        status_dir,
        "create",
        "CLI Software",
        "--template",
        "tpl-software",
    )

    assert result.returncode == 0, result.stderr
    project = _read_projects(status_dir)[0]
    assert result.stdout.splitlines() == [
        "✅ Project created: CLI Software",
        "   ID: " + project["id"],
        "   Columns: Backlog, Sprint, In Progress, Code Review, QA, Done",
        "   Template tasks: 3",
    ]
    assert set(project) == CLI_PROJECT_KEYS
    assert [column["title"] for column in project["columns"]] == [
        "Backlog",
        "Sprint",
        "In Progress",
        "Code Review",
        "QA",
        "Done",
    ]
    assert [column["order"] for column in project["columns"]] == list(range(6))
    assert [task["title"] for task in project["tasks"]] == [
        "Set up development environment",
        "Define acceptance criteria",
        "Write unit tests",
    ]
    assert [task["priority"] for task in project["tasks"]] == ["high", "medium", "medium"]
    assert all(set(task) == CLI_TASK_KEYS for task in project["tasks"])
    assert all(task["columnId"] == project["columns"][0]["id"] for task in project["tasks"])
    assert [task["order"] for task in project["tasks"]] == [0, 0, 0]
    assert all(task["createdAt"] == project["createdAt"] for task in project["tasks"])
    assert all(task["updatedAt"] == project["createdAt"] for task in project["tasks"])
    assert all(
        {
            key: task[key]
            for key in (
                "description",
                "assignee",
                "assigneeBranch",
                "dueDate",
                "tags",
                "checklist",
                "comments",
                "attachments",
                "completedAt",
            )
        }
        == {
            "description": "",
            "assignee": None,
            "assigneeBranch": None,
            "dueDate": None,
            "tags": [],
            "checklist": [],
            "comments": [],
            "attachments": [],
            "completedAt": None,
        }
        for task in project["tasks"]
    )


def test_cli_add_task_preserves_column_order_arguments_and_output(tmp_path: Path):
    status_dir = tmp_path / "status"
    created = _run_cli(status_dir, "create", "CLI Tasks")
    assert created.returncode == 0, created.stderr
    project_id = _read_projects(status_dir)[0]["id"]

    first = _run_cli(
        status_dir,
        "add-task",
        project_id[:8],
        "First task",
        "--col",
        "To Do",
        "--desc",
        "First description",
        "--priority",
        "high",
        "--assign",
        "builder",
        "--due",
        "2026-08-02",
        "--tags",
        "cli,task",
    )
    second = _run_cli(status_dir, "add-task", project_id, "Second task", "--col", "to do")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    project = _read_projects(status_dir)[0]
    first_task, second_task = project["tasks"]
    assert first.stdout.splitlines() == [
        "✅ Task added to [To Do]: First task",
        "   ID: " + first_task["id"],
        "   Assigned: builder",
    ]
    assert second.stdout.splitlines() == [
        "✅ Task added to [To Do]: Second task",
        "   ID: " + second_task["id"],
    ]
    assert all(set(task) == CLI_TASK_KEYS for task in project["tasks"])
    assert first_task == {
        "id": first_task["id"],
        "title": "First task",
        "description": "First description",
        "columnId": project["columns"][1]["id"],
        "order": 0,
        "priority": "high",
        "assignee": "builder",
        "assigneeBranch": None,
        "dueDate": "2026-08-02T00:00:00Z",
        "tags": ["cli", "task"],
        "checklist": [],
        "comments": [],
        "attachments": [],
        "createdAt": first_task["createdAt"],
        "updatedAt": first_task["createdAt"],
        "completedAt": None,
    }
    assert second_task["columnId"] == first_task["columnId"]
    assert second_task["order"] == 1
    assert second_task["priority"] == "medium"
    assert second_task["assignee"] is None
    assert second_task["description"] == ""
    assert second_task["assigneeBranch"] is None
    assert second_task["dueDate"] is None
    assert second_task["tags"] == []
    assert second_task["checklist"] == []
    assert second_task["comments"] == []
    assert second_task["attachments"] == []
    assert second_task["completedAt"] is None
    assert second_task["createdAt"] == second_task["updatedAt"]
    assert project["updatedAt"] == second_task["updatedAt"]
