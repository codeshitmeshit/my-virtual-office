#!/usr/bin/env python3
"""Characterize the five project/task materialization paths before convergence."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import os
import sys
from typing import Any, Callable

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services import project_commands
from services.project_authoring import ProjectAuthoringService
from services.project_authoring_store import ProjectAuthoringRootStore
from services.project_materialization import (
    CANONICAL_PROJECT_BASE_FIELDS,
    CANONICAL_TASK_BASE_FIELDS,
)
from services.project_repository import ProjectRepository


AGENTS = {
    "author": {"id": "author"},
    "owner": {"id": "owner"},
    "builder": {"id": "builder"},
    "reviewer": {"id": "reviewer"},
}
NOW = "2026-07-23T01:02:03+00:00"
MISSING = "<missing>"
SUMMARY_TEXT = """我准备创建这个 VO 项目，请确认：

项目名称：Characterization
项目类型：one_time
项目目标：Capture current materialization
维护模式：strict_confirmation
Project Execution：仅跟踪（projectExecutionEnabled=false）
默认执行 Agent：未指定（使用任务级执行人 builder）
Reviewer 默认策略：不指定；如有建议，仅作为建议，确认分配前不会写入 reviewer。
创建后状态：确认后会创建真实项目并保持未启动；只有用户显式要求执行才会开始。
启动模式：continuous（启动后连续推进整个项目）

任务清单：

| # | 任务名称 | 所属列 | 任务细节 | 验收标准 | 负责人 | 执行人 | Reviewer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Implement | Backlog | Capture current fields | Complete it | owner | builder | 不指定 |

模板/复用配置：无
周期配置：无
周期执行模式：不适用
需要你确认的点：无

请确认是否按以上方案创建真实项目。"""
SUMMARY_DIGEST = hashlib.sha256(SUMMARY_TEXT.encode("utf-8")).hexdigest()
CHECKLIST_ID = "checklist-" + hashlib.sha256("complete it".encode("utf-8")).hexdigest()[:12]


MANUAL_PROJECT_KEYS = (
    "activeAgent", "activeTaskId", "activity", "archiveMaintenance", "archiveMaintenanceEnabled",
    "branch", "columns",
    "createdAt", "createdBy", "defaultExecutorAgentId", "defaultReviewerAgentId", "description",
    "dueDate", "executionDirtyConfirmations", "executionPolicy", "highPriorityAiMeetingAutoApprove",
    "id", "longTermProject", "priority", "projectExecutionEnabled", "projectExecutionFlowActive",
    "projectExecutionFlowStopReason", "projectExecutionStartMode", "scheduledCronPaused", "status",
    "projectType", "tags", "tasks", "template", "title", "updatedAt", "workflowActive",
    "workflowPhase", "workspaceCreatedAt", "workspaceKind", "workspaceManagedBy", "workspacePath",
    "workspaceStatus",
)
MANUAL_TASK_KEYS = (
    "activeAttemptId", "allowReviewerlessExecution", "assignee", "assigneeBranch", "attachments",
    "attempts", "blockedReason", "checklist", "columnId", "comments", "completedAt", "createdAt",
    "description", "dueDate", "evidence", "executionState", "executorActor", "executorAgentId", "id", "lastError",
    "meetingActionItems", "meetingDecisionHistory", "meetingDiscussionPoints", "meetingRecords", "order",
    "priority", "requiresUserAcceptance", "responsibleActor", "reviewerActor", "reviewerAgentId",
    "reviewerRecommendation", "scheduledRepeatEnabled", "source", "tags",
    "title", "updatedAt",
)
BROWSER_TEMPLATE_PROJECT_KEYS = MANUAL_PROJECT_KEYS + (
    "authoringSource", "recurrenceRef", "templateRef",
)
BROWSER_TEMPLATE_TASK_KEYS = MANUAL_TASK_KEYS
AGENT_PROJECT_KEYS = tuple(sorted(CANONICAL_PROJECT_BASE_FIELDS | {
    "agentMaintenanceMode", "authoringAgentId", "authoringSource", "recurrenceRef", "templateRef",
}))
VERSIONED_TEMPLATE_PROJECT_KEYS = tuple(sorted(CANONICAL_PROJECT_BASE_FIELDS | {
    "agentMaintenanceMode", "authoringSource", "recurrenceRef", "templateRef",
}))
LEGACY_TEMPLATE_PROJECT_KEYS = (
    "activeAgent", "activeTaskId", "activity", "agentMaintenanceMode", "authoringSource", "branch",
    "columns", "createdAt", "createdBy", "defaultExecutorAgentId", "defaultReviewerAgentId", "description",
    "dueDate", "executionPolicy", "id", "longTermProject", "priority", "projectExecutionEnabled",
    "projectExecutionFlowActive", "projectExecutionStartMode", "projectType", "recurrenceRef", "status",
    "tags", "tasks", "templateRef", "title", "updatedAt", "workflowActive", "workflowPhase",
)
AUTHORED_TASK_KEYS = (
    "activeAttemptId", "assignee", "attempts", "checklist", "columnId", "completedAt", "createdAt", "description",
    "executionState", "executorActor", "executorAgentId", "id", "order", "responsibleActor", "reviewerActor",
    "reviewerAgentId", "reviewerRecommendation", "title", "updatedAt",
)
DIRECT_TASK_KEYS = tuple(sorted(CANONICAL_TASK_BASE_FIELDS))


def _sorted_keys(value: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(value))


def _sensitive_defaults(project: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    project_fields = (
        "archiveMaintenanceEnabled", "archiveMaintenance", "highPriorityAiMeetingAutoApprove",
        "projectExecutionEnabled", "projectExecutionFlowActive", "projectExecutionFlowStopReason",
        "workflowActive", "workflowPhase", "scheduledCronPaused", "executionDirtyConfirmations", "template",
        "defaultExecutorAgentId", "defaultReviewerAgentId", "workspaceManagedBy", "workspaceCreatedAt",
    )
    task_fields = (
        "assigneeBranch", "executionState", "activeAttemptId", "attempts", "evidence", "blockedReason",
        "lastError", "checklist", "source", "comments", "attachments", "meetingActionItems",
        "meetingDecisionHistory", "meetingDiscussionPoints", "meetingRecords",
    )
    return {
        "project": {field: copy.deepcopy(project.get(field, MISSING)) for field in project_fields},
        "task": {field: copy.deepcopy(task.get(field, MISSING)) for field in task_fields},
    }


def _manual_creation() -> tuple[dict[str, Any], dict[str, Any]]:
    state = {"projects": [], "templates": []}
    repository = ProjectRepository(
        load_projects=lambda: copy.deepcopy(state),
        save_projects=lambda value: (state.clear(), state.update(copy.deepcopy(value))),
    )
    ids = iter(f"manual-{index}" for index in range(20))

    def new_id() -> str:
        return next(ids)

    def log_activity(project, event, by, detail, task_id=None):
        activity = {"id": new_id(), "type": event, "by": by, "detail": detail}
        if task_id:
            activity["taskId"] = task_id
        project.setdefault("activity", []).append(activity)

    project = project_commands.create_project(
        {"title": "Manual characterization"},
        repository=repository,
        prepare_workspace=lambda _title, _body, _now: {
            "ok": True,
            "projectExecutionEnabled": False,
            "workspacePath": None,
            "workspaceKind": None,
            "workspaceStatus": {},
            "workspaceManagedBy": None,
            "workspaceCreatedAt": None,
        },
        system_agent_assignment_error=lambda _value, _scope: None,
        archive_maintenance_default=lambda _project: True,
        log_activity=log_activity,
        new_id=new_id,
        now=lambda: NOW,
    ).result.payload["project"]
    task = project_commands.create_task(
        project["id"],
        {"title": "Manual task", "assignee": "owner", "executorAgentId": "builder"},
        repository=repository,
        system_agent_assignment_error=lambda _value, _scope: None,
        log_activity=log_activity,
        new_id=new_id,
        now=lambda: NOW,
    ).result.payload["task"]
    return repository.get(project["id"]), task


def _browser_template_creation(monkeypatch, tmp_path) -> tuple[dict[str, Any], dict[str, Any]]:
    monkeypatch.setenv("VO_STATUS_DIR", str(tmp_path / "browser-status"))
    import server

    state = {"projects": [], "templates": []}
    template = {
        "id": "browser-template",
        "title": "Browser template",
        "description": "Characterize browser template materialization",
        "versioned": True,
        "version": 2,
        "columns": [{"title": "Backlog", "color": "#6c757d"}],
        "taskTemplates": [{
            "title": "Browser task",
            "columnIndex": 0,
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerActor": None,
            "reviewerRecommendation": {"recommended": False, "triggers": []},
            "assignee": "owner",
            "executorAgentId": "builder",
        }],
    }

    def save(value):
        state.clear()
        state.update(copy.deepcopy(value))

    ids = iter(f"browser-{index}" for index in range(20))
    monkeypatch.setattr(server, "_load_projects", lambda: copy.deepcopy(state))
    monkeypatch.setattr(server, "_save_projects", save)
    monkeypatch.setattr(
        server,
        "_PROJECT_REPOSITORY",
        ProjectRepository(load_projects=lambda: copy.deepcopy(state), save_projects=save),
    )
    monkeypatch.setattr(server, "_project_browser_templates", lambda _data: [copy.deepcopy(template)])
    monkeypatch.setattr(server, "_system_agent_assignment_error", lambda _value, _scope: None)
    monkeypatch.setattr(server, "_proj_uuid", lambda: next(ids))
    monkeypatch.setattr(server, "_proj_now", lambda: NOW)

    result = server._handle_project_from_template({
        "templateId": "browser-template",
        "title": "Browser characterization",
    })
    assert result["ok"] is True
    project = result["project"]
    return project, project["tasks"][0]


def _authoring_service(path, identifiers: tuple[str, ...]) -> ProjectAuthoringService:
    markdown = MarkdownProjectStore(str(path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    ids = iter(identifiers)
    return ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda _agent_id: False,
        submission_enabled=lambda: True,
        recurrence_enabled=lambda: True,
        recurrence_paused=lambda: False,
        clock=lambda: datetime(2026, 7, 23, 1, 2, 3, tzinfo=timezone.utc),
        new_id=lambda: next(ids),
        new_secret=lambda: "characterization-secret",
    )


def _draft(*, project_type="one_time", template_mode="none", recurring=False) -> dict[str, Any]:
    return {
        "title": "Authoring characterization",
        "description": "Capture current materialization",
        "projectType": project_type,
        "agentMaintenanceMode": "strict_confirmation",
        "projectExecutionEnabled": False,
        "columns": [{"id": "backlog", "title": "Backlog"}],
        "tasks": [{
            "title": "Authored task",
            "columnId": "backlog",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerRecommendation": {"recommended": False, "triggers": []},
            "checklist": [{"text": "Complete it", "done": False}],
        }],
        "template": (
            {"mode": "create", "name": "Characterization template"}
            if template_mode == "create" else {"mode": "none"}
        ),
        "recurrence": (
            {
                "enabled": True,
                "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "UTC"},
            }
            if recurring else {"enabled": False}
        ),
    }


def _confirmed_create(service: ProjectAuthoringService, draft: dict[str, Any]) -> dict[str, Any]:
    return service.create_confirmed_project(
        draft,
        requesting_agent_id="author",
        idempotency_key=f"characterization:{draft['projectType']}",
        confirmation={
            "confirmed": True,
            "summaryDigest": SUMMARY_DIGEST,
            "summaryText": SUMMARY_TEXT,
        },
        source={"surface": "characterization"},
    )["project"]


def _agent_direct_creation(tmp_path) -> tuple[dict[str, Any], dict[str, Any]]:
    service = _authoring_service(tmp_path / "agent", ("agent-source",))
    project = _confirmed_create(service, _draft())
    return project, project["tasks"][0]


def _versioned_template_creation(tmp_path) -> tuple[dict[str, Any], dict[str, Any]]:
    service = _authoring_service(tmp_path / "template", ("template-source", "template-instance"))
    _confirmed_create(service, _draft(project_type="reusable", template_mode="create"))
    result = service.instantiate_template(
        "template-template-source",
        1,
        idempotency_key="characterization:template-instance",
        actor="user",
    )
    project = result["project"]
    return project, project["tasks"][0]


def _recurring_creation(tmp_path) -> tuple[dict[str, Any], dict[str, Any]]:
    service = _authoring_service(tmp_path / "recurrence", ("recurrence-source", "occurrence-claim"))
    _confirmed_create(
        service,
        _draft(project_type="recurring", template_mode="create", recurring=True),
    )
    result = service.materialize_recurrence_occurrence(
        "recurrence-recurrence-source",
        "occurrence-2026-07-23",
    )
    project = result["project"]
    return project, project["tasks"][0]


@pytest.mark.parametrize(
    ("case", "creator", "project_keys", "task_keys"),
    (
        ("manual", lambda monkeypatch, tmp_path: _manual_creation(), MANUAL_PROJECT_KEYS, MANUAL_TASK_KEYS),
        ("browser_template", _browser_template_creation, BROWSER_TEMPLATE_PROJECT_KEYS, BROWSER_TEMPLATE_TASK_KEYS),
        ("agent_direct", lambda monkeypatch, tmp_path: _agent_direct_creation(tmp_path), AGENT_PROJECT_KEYS, DIRECT_TASK_KEYS),
        ("versioned_template", lambda monkeypatch, tmp_path: _versioned_template_creation(tmp_path), VERSIONED_TEMPLATE_PROJECT_KEYS, DIRECT_TASK_KEYS),
        ("recurrence", lambda monkeypatch, tmp_path: _recurring_creation(tmp_path), LEGACY_TEMPLATE_PROJECT_KEYS, AUTHORED_TASK_KEYS),
    ),
)
def test_creation_paths_preserve_complete_current_field_sets(
    case: str,
    creator: Callable,
    project_keys: tuple[str, ...],
    task_keys: tuple[str, ...],
    monkeypatch,
    tmp_path,
):
    project, task = creator(monkeypatch, tmp_path)

    assert _sorted_keys(project) == tuple(sorted(project_keys)), case
    assert _sorted_keys(task) == tuple(sorted(task_keys)), case


def test_creation_paths_characterize_current_default_divergence(monkeypatch, tmp_path):
    cases = {
        "manual": _manual_creation(),
        "browser_template": _browser_template_creation(monkeypatch, tmp_path),
        "agent_direct": _agent_direct_creation(tmp_path),
        "versioned_template": _versioned_template_creation(tmp_path),
        "recurrence": _recurring_creation(tmp_path),
    }

    projections = {
        name: _sensitive_defaults(project, task)
        for name, (project, task) in cases.items()
    }

    assert projections["manual"] == {
        "project": {
            "archiveMaintenanceEnabled": True,
            "archiveMaintenance": {"enabled": True, "explicit": False, "updatedAt": NOW, "updatedBy": "user"},
            "highPriorityAiMeetingAutoApprove": False,
            "projectExecutionEnabled": False,
            "projectExecutionFlowActive": False,
            "projectExecutionFlowStopReason": None,
            "workflowActive": False,
            "workflowPhase": "idle",
            "scheduledCronPaused": False,
            "executionDirtyConfirmations": [],
            "template": False,
            "defaultExecutorAgentId": None,
            "defaultReviewerAgentId": None,
            "workspaceManagedBy": None,
            "workspaceCreatedAt": None,
        },
        "task": {
            "assigneeBranch": None,
            "executionState": "backlog",
            "activeAttemptId": None,
            "attempts": [],
            "evidence": {},
            "blockedReason": None,
            "lastError": None,
            "checklist": [],
            "source": {},
            "comments": [],
            "attachments": [],
            "meetingActionItems": [],
            "meetingDecisionHistory": [],
            "meetingDiscussionPoints": [],
            "meetingRecords": [],
        },
    }
    assert projections["browser_template"] == {
        "project": projections["manual"]["project"],
        "task": projections["manual"]["task"],
    }
    direct_project_defaults = {
        "archiveMaintenanceEnabled": True,
        "archiveMaintenance": {"enabled": True, "explicit": False, "updatedAt": NOW, "updatedBy": "author"},
        "highPriorityAiMeetingAutoApprove": False,
        "projectExecutionEnabled": False,
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": None,
        "workflowActive": False,
        "workflowPhase": "idle",
        "scheduledCronPaused": False,
        "executionDirtyConfirmations": [],
        "template": False,
        "defaultExecutorAgentId": None,
        "defaultReviewerAgentId": None,
        "workspaceManagedBy": None,
        "workspaceCreatedAt": None,
    }
    direct_task_defaults = {
        **projections["manual"]["task"],
        "checklist": [{"id": CHECKLIST_ID, "text": "Complete it", "done": False}],
    }
    assert projections["agent_direct"] == {
        "project": direct_project_defaults,
        "task": direct_task_defaults,
    }

    authored_project_defaults = {
        "archiveMaintenanceEnabled": MISSING,
        "archiveMaintenance": MISSING,
        "highPriorityAiMeetingAutoApprove": MISSING,
        "projectExecutionEnabled": False,
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": MISSING,
        "workflowActive": False,
        "workflowPhase": "idle",
        "scheduledCronPaused": MISSING,
        "executionDirtyConfirmations": MISSING,
        "template": MISSING,
        "defaultExecutorAgentId": MISSING,
        "defaultReviewerAgentId": MISSING,
        "workspaceManagedBy": MISSING,
        "workspaceCreatedAt": MISSING,
    }
    authored_task_defaults = {
        "assigneeBranch": MISSING,
        "executionState": "backlog",
        "activeAttemptId": None,
        "attempts": [],
        "evidence": MISSING,
        "blockedReason": MISSING,
        "lastError": MISSING,
        "checklist": [{"id": CHECKLIST_ID, "text": "Complete it", "done": False}],
        "source": MISSING,
        "comments": MISSING,
        "attachments": MISSING,
        "meetingActionItems": MISSING,
        "meetingDecisionHistory": MISSING,
        "meetingDiscussionPoints": MISSING,
        "meetingRecords": MISSING,
    }
    template_project_defaults = {
        **authored_project_defaults,
        "defaultExecutorAgentId": None,
        "defaultReviewerAgentId": None,
    }
    assert projections["versioned_template"] == {
        "project": projections["manual"]["project"],
        "task": direct_task_defaults,
    }
    assert projections["recurrence"] == {
        "project": template_project_defaults,
        "task": authored_task_defaults,
    }
