#!/usr/bin/env python3
"""Conversation-confirmed direct project creation domain tests."""

from datetime import datetime, timezone
import hashlib
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_authoring import ProjectAuthoringService
from services.project_authoring_config import ProjectAuthoringCapacityError
from services.project_direct_creation import DirectProjectCreationError
from services.project_authoring_security import hash_request_secret
from services.project_materialization import (
    CANONICAL_PROJECT_BASE_FIELDS,
    CANONICAL_TASK_BASE_FIELDS,
)
from services.project_authoring_store import (
    GRANTS_KEY,
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
SUMMARY_TEXT = """我准备创建这个 VO 项目，请确认：

项目名称：Direct project
项目类型：one_time
项目目标：Created after conversation confirmation
维护模式：strict_confirmation
Project Execution：仅跟踪（projectExecutionEnabled=false）
默认执行 Agent：未指定（使用任务级执行人 builder）
Reviewer 默认策略：不指定；如有建议，仅作为建议，确认分配前不会写入 reviewer。
创建后状态：确认后会创建真实项目并保持未启动；只有用户显式要求执行才会开始。
启动模式：continuous（启动后连续推进整个项目）

任务清单：

| # | 任务名称 | 所属列 | 任务细节 | 验收标准 | 负责人 | 执行人 | Reviewer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Implement | Backlog | Created after conversation confirmation | 完成任务 | owner | builder | 不指定 |

模板/复用配置：无
周期配置：无
周期执行模式：不适用
需要你确认的点：无

请确认是否按以上方案创建真实项目。"""
SUMMARY_DIGEST = hashlib.sha256(SUMMARY_TEXT.encode("utf-8")).hexdigest()


def _project(title="Direct project"):
    return {
        "title": title,
        "description": "Created after conversation confirmation",
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
            "checklist": [{"text": "完成任务", "done": False}],
        }],
        "template": {"mode": "none"},
        "recurrence": {"enabled": False},
    }


def _service(tmp_path, *, recurrence_enabled=False, authoring_enabled=lambda: True):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda _agent_id: False,
        submission_enabled=authoring_enabled,
        recurrence_enabled=lambda: recurrence_enabled,
        clock=lambda: datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        new_id=lambda: "creation-1",
        new_secret=lambda: "one-time-project-secret",
    )
    return markdown, service


def _create(service, project=None, **kwargs):
    return service.create_confirmed_project(
        project or _project(),
        requesting_agent_id=kwargs.pop("requesting_agent_id", "author"),
        idempotency_key=kwargs.pop("idempotency_key", "author:direct-1"),
        confirmation=kwargs.pop("confirmation", {
            "confirmed": True,
            "summaryDigest": SUMMARY_DIGEST,
            "summaryText": SUMMARY_TEXT,
        }),
        source={"surface": "agent_http"},
        **kwargs,
    )


def test_direct_creation_commits_complete_unstarted_project_and_one_time_grant(tmp_path):
    markdown, service = _service(tmp_path)

    created = _create(service)
    repeated = _create(service)
    root = markdown.load_all()

    assert created["ok"] is True and created["created"] is True
    assert created["projectGrantSecret"] == "one-time-project-secret"
    assert repeated["ok"] is True and repeated["created"] is False
    assert "projectGrantSecret" not in repeated
    assert created["project"]["id"] == repeated["project"]["id"] == "project-creation-1"
    assert len(root["projects"]) == 1
    assert root[REQUESTS_KEY] == {}
    project = root["projects"][0]
    assert CANONICAL_PROJECT_BASE_FIELDS <= set(project)
    assert CANONICAL_TASK_BASE_FIELDS <= set(project["tasks"][0])
    assert project["authoringSource"] == {
        "kind": "conversation_confirmed_agent",
        "creationId": "creation-1",
        "confirmationSummaryDigest": SUMMARY_DIGEST,
        "surface": "agent_http",
    }
    assert project["workflowActive"] is False
    assert project["projectExecutionFlowActive"] is False
    assert project["tasks"][0]["executionState"] == "backlog"
    assert project["tasks"][0]["checklist"][0]["text"] == "完成任务"
    assert project["tasks"][0]["checklist"][0]["id"].startswith("checklist-")
    assert project["tasks"][0]["responsibleActor"] == {"type": "agent", "id": "owner"}
    assert project["tasks"][0]["executorActor"] == {"type": "agent", "id": "builder"}
    grant = root[GRANTS_KEY][project["id"]]
    assert grant["secretHash"] == hash_request_secret("one-time-project-secret")
    assert "one-time-project-secret" not in str(root)
    assert root[IDEMPOTENCY_KEY]["direct-create:author:author:direct-1"]["projectId"] == project["id"]


def test_rollout_flag_off_then_on_gates_direct_creation_without_partial_state(tmp_path):
    enabled = {"value": False}
    markdown, service = _service(
        tmp_path, authoring_enabled=lambda: enabled["value"],
    )

    with pytest.raises(ProjectAuthoringCapacityError) as disabled:
        _create(service)
    assert disabled.value.code == "project_authoring_disabled"
    assert markdown.load_all()["projects"] == []

    enabled["value"] = True
    created = _create(service)
    assert created["created"] is True
    assert len(markdown.load_all()["projects"]) == 1


def test_direct_enabled_creation_requires_prepared_workspace_without_downgrade(tmp_path):
    markdown, service = _service(tmp_path)
    enabled = _project()
    enabled.pop("projectExecutionEnabled")

    with pytest.raises(DirectProjectCreationError) as missing:
        _create(service, enabled)
    assert missing.value.code == "workspace_preparation_required"
    assert markdown.load_all()["projects"] == []

    with pytest.raises(DirectProjectCreationError) as invalid:
        _create(service, enabled, prepare_workspace=lambda *_: {"ok": True})
    assert invalid.value.code == "workspace_preparation_failed"
    assert markdown.load_all()["projects"] == []

    calls = []
    created = _create(
        service,
        enabled,
        prepare_workspace=lambda normalized, *_: calls.append(normalized) or {
            "ok": True,
            "projectExecutionEnabled": True,
            "workspacePath": "/tmp/enabled-workspace",
            "workspaceKind": "directory",
            "workspaceStatus": {"ok": True},
            "workspaceManagedBy": "system",
            "workspaceCreatedAt": "2026-07-18T12:00:00+00:00",
            "createdInAttempt": True,
        },
    )
    assert calls[0]["projectExecutionEnabled"] is True
    assert created["project"]["projectExecutionEnabled"] is True
    assert created["project"]["workspaceManagedBy"] == "system"
    assert created["project"]["workspaceCreatedAt"] == "2026-07-18T12:00:00+00:00"
    assert "createdInAttempt" not in created["project"]
    assert created["project"]["workflowActive"] is False
    assert created["project"]["projectExecutionFlowActive"] is False

    explicit = _project()
    explicit["projectExecutionEnabled"] = True
    repeated = _create(
        service,
        explicit,
        prepare_workspace=lambda *_: calls.append("unexpected") or {"ok": False},
    )
    assert repeated["created"] is False
    assert len(calls) == 1


def test_direct_tracking_only_creation_skips_workspace_preparation(tmp_path):
    _, service = _service(tmp_path)
    calls = []

    created = _create(
        service,
        prepare_workspace=lambda *_: calls.append(True) or {"ok": False},
    )

    assert created["project"]["projectExecutionEnabled"] is False
    assert calls == []


def test_direct_enabled_creation_preserves_user_managed_workspace(tmp_path):
    _, service = _service(tmp_path)
    enabled = _project()
    enabled["projectExecutionEnabled"] = True
    cleanup_calls = []

    created = _create(
        service,
        enabled,
        prepare_workspace=lambda *_: {
            "ok": True,
            "projectExecutionEnabled": True,
            "workspacePath": "/workspace/user",
            "workspaceKind": "directory",
            "workspaceStatus": {"ok": True},
            "workspaceManagedBy": "user",
            "workspaceCreatedAt": None,
            "createdInAttempt": False,
        },
        cleanup_workspace=cleanup_calls.append,
    )

    assert created["project"]["workspacePath"] == "/workspace/user"
    assert created["project"]["workspaceManagedBy"] == "user"
    assert created["project"]["workspaceCreatedAt"] is None
    assert cleanup_calls == []


def test_direct_creation_requires_confirmation_and_sha256_summary(tmp_path):
    markdown, service = _service(tmp_path)

    for confirmation, code in (
        (
            {"confirmed": False, "summaryDigest": SUMMARY_DIGEST, "summaryText": SUMMARY_TEXT},
            "project_confirmation_required",
        ),
        (
            {"confirmed": True, "summaryDigest": "not-a-digest", "summaryText": SUMMARY_TEXT},
            "invalid_confirmation_summary_digest",
        ),
        (
            {"confirmed": True, "summaryDigest": SUMMARY_DIGEST},
            "confirmation_summary_text_required",
        ),
        (
            {"confirmed": True, "summaryDigest": SUMMARY_DIGEST, "summaryText": "确认创建"},
            "invalid_confirmation_summary_format",
        ),
        (
            {"confirmed": True, "summaryDigest": "b" * 64, "summaryText": SUMMARY_TEXT},
            "confirmation_summary_digest_mismatch",
        ),
    ):
        with pytest.raises(DirectProjectCreationError) as raised:
            _create(service, confirmation=confirmation)
        assert raised.value.code == code

    missing_execution_marker = SUMMARY_TEXT.replace("Project Execution：", "执行配置：")
    with pytest.raises(DirectProjectCreationError) as marker_error:
        _create(service, confirmation={
            "confirmed": True,
            "summaryDigest": hashlib.sha256(missing_execution_marker.encode("utf-8")).hexdigest(),
            "summaryText": missing_execution_marker,
        })
    assert marker_error.value.code == "invalid_confirmation_summary_format"
    assert markdown.load_all()["projects"] == []


def test_direct_creation_rejects_idempotency_key_reuse_for_changed_content(tmp_path):
    markdown, service = _service(tmp_path)
    _create(service)

    with pytest.raises(DirectProjectCreationError) as raised:
        _create(service, _project("Changed project"))

    assert raised.value.code == "project_creation_idempotency_conflict"
    assert len(markdown.load_all()["projects"]) == 1


def test_direct_creation_workspace_failure_and_commit_failure_leave_no_partial_state(tmp_path, monkeypatch):
    markdown, service = _service(tmp_path)
    enabled = _project()
    enabled["projectExecutionEnabled"] = True
    cleanup = []
    failed_workspace = {
        "ok": False,
        "error": "workspace unavailable",
        "workspacePath": "/tmp/direct-partial",
        "workspaceManagedBy": "system",
        "createdInAttempt": True,
    }
    with pytest.raises(DirectProjectCreationError) as raised:
        _create(
            service,
            enabled,
            prepare_workspace=lambda *_args: failed_workspace,
            cleanup_workspace=cleanup.append,
        )
    assert raised.value.code == "workspace_preparation_failed"
    assert cleanup == [failed_workspace]
    assert markdown.load_all()["projects"] == []

    prepared = {
        "ok": True,
        "projectExecutionEnabled": True,
        "workspacePath": "/tmp/direct-created",
        "workspaceKind": "directory",
        "workspaceStatus": {"ok": True},
        "workspaceManagedBy": "system",
        "workspaceCreatedAt": "2026-07-18T12:00:00+00:00",
        "createdInAttempt": True,
    }
    original_update = service.store.update

    def fail_commit(_mutator):
        raise OSError("root commit failed")

    monkeypatch.setattr(service.store, "update", fail_commit)
    with pytest.raises(OSError, match="root commit failed"):
        _create(
            service,
            enabled,
            prepare_workspace=lambda *_args: prepared,
            cleanup_workspace=cleanup.append,
        )
    monkeypatch.setattr(service.store, "update", original_update)
    assert cleanup[-1] == prepared
    assert markdown.load_all()["projects"] == []


def test_direct_recurring_creation_commits_template_recurrence_and_outbox(tmp_path):
    markdown, service = _service(tmp_path, recurrence_enabled=True)
    project = _project("Weekly direct")
    project.update({
        "projectType": "recurring",
        "template": {"mode": "create", "name": "Weekly direct template"},
        "recurrence": {
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "UTC"},
        },
    })

    result = _create(service, project)
    project["recurrence"]["executionMode"] = "create_only"
    repeated = _create(service, project)
    root = markdown.load_all()

    assert repeated["created"] is False
    assert result["project"]["templateRef"] == {"id": "template-creation-1", "version": 1}
    assert result["project"]["recurrenceRef"] == {"id": "recurrence-creation-1"}
    assert root[TEMPLATES_KEY]["template-creation-1"][0]["version"] == 1
    assert root[RECURRENCES_KEY]["recurrence-creation-1"]["sourceProjectId"] == "project-creation-1"
    assert root[RECURRENCES_KEY]["recurrence-creation-1"]["executionMode"] == "create_only"
    assert root[OUTBOX_KEY][0]["recurrenceId"] == "recurrence-creation-1"


def test_direct_recurring_creation_respects_action_time_feature_gate(tmp_path):
    markdown, service = _service(tmp_path, recurrence_enabled=False)
    project = _project("Disabled recurrence")
    project.update({
        "projectType": "recurring",
        "template": {"mode": "create", "name": "Disabled recurrence template"},
        "recurrence": {
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "UTC"},
        },
    })

    with pytest.raises(ProjectAuthoringCapacityError) as raised:
        _create(service, project)

    assert getattr(raised.value, "code", "") == "project_recurrence_disabled"
    root = markdown.load_all()
    assert root["projects"] == []
    assert root[TEMPLATES_KEY] == {}
    assert root[RECURRENCES_KEY] == {}
    assert root[OUTBOX_KEY] == []
