#!/usr/bin/env python3
"""Complete project-authoring draft validation coverage."""

import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_authoring_config import ProjectAuthoringConfig
from services.project_authoring_validation import (
    DraftValidationError,
    validate_idempotency_key,
    validate_project_draft,
)


AGENTS = {
    "owner": {"id": "owner"},
    "builder": {"id": "builder"},
    "reviewer": {"id": "reviewer"},
    "excluded": {"id": "excluded"},
}


def _draft(**updates):
    result = {
        "title": "Launch project",
        "description": "Ship a complete deliverable",
        "projectType": "one_time",
        "agentMaintenanceMode": "strict_confirmation",
        "columns": [{"id": "backlog", "title": "Backlog"}],
        "tasks": [{
            "title": "Implement",
            "description": "Build it",
            "columnId": "backlog",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerRecommendation": {"recommended": False, "triggers": []},
        }],
        "template": {"mode": "none"},
        "recurrence": {"enabled": False},
    }
    result.update(updates)
    return result


def _validate(draft, **kwargs):
    return validate_project_draft(
        draft,
        idempotency_key=kwargs.pop("idempotency_key", "agent:key-1234"),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda agent_id: agent_id == "excluded",
        **kwargs,
    )


def _codes(error):
    return {issue.code for issue in error.value.issues}


def test_complete_draft_normalizes_roles_and_legacy_execution_fields():
    normalized = _validate(_draft())

    assert normalized["projectExecutionEnabled"] is True
    assert normalized["projectExecutionStartMode"] == "continuous"
    assert normalized["executionPolicy"] == {"maxActiveTasks": 1}
    assert normalized["defaultExecutorAgentId"] is None
    assert normalized["defaultReviewerAgentId"] is None
    task = normalized["tasks"][0]
    assert task["responsibleActor"] == {"type": "agent", "id": "owner"}
    assert task["executorActor"] == {"type": "agent", "id": "builder"}
    assert task["reviewerActor"] is None
    assert task["assignee"] == "owner"
    assert task["executorAgentId"] == "builder"
    assert task["reviewerAgentId"] is None


def test_same_actor_and_local_user_roles_are_supported():
    same = _draft()
    same["tasks"][0]["executorActor"] = {"type": "agent", "id": "owner"}
    assert _validate(same)["tasks"][0]["executorAgentId"] == "owner"

    human = _draft()
    human["tasks"][0]["responsibleActor"] = {"type": "user", "id": "user:local"}
    human["tasks"][0]["executorActor"] = {"type": "user", "id": "user:local"}
    with pytest.raises(DraftValidationError) as enabled_error:
        _validate(human)
    assert "executable_agent_required" in _codes(enabled_error)

    human["projectExecutionEnabled"] = False
    task = _validate(human)["tasks"][0]
    assert task["assignee"] == "user:local"
    assert task["executorAgentId"] is None


def test_execution_enabled_human_task_can_resolve_project_default_agent():
    draft = _draft(defaultExecutorAgentId="builder", defaultReviewerAgentId="reviewer")
    draft["tasks"][0]["executorActor"] = {"type": "user", "id": "user:local"}

    normalized = _validate(draft)

    assert normalized["projectExecutionEnabled"] is True
    assert normalized["defaultExecutorAgentId"] == "builder"
    assert normalized["defaultReviewerAgentId"] == "reviewer"
    assert normalized["tasks"][0]["executorAgentId"] is None


def test_execution_configuration_rejects_invalid_values_and_agents():
    draft = _draft(
        projectExecutionEnabled="yes",
        projectExecutionStartMode="automatic",
        executionPolicy={"maxActiveTasks": 0},
        defaultExecutorAgentId="missing",
        defaultReviewerAgentId="excluded",
    )

    with pytest.raises(DraftValidationError) as error:
        _validate(draft)

    assert {
        "invalid_project_execution_enabled",
        "invalid_project_execution_start_mode",
        "invalid_max_active_tasks",
        "agent_not_found",
        "agent_not_assignable",
    } <= _codes(error)


def test_acceptance_checklist_is_normalized_without_promoting_meeting_context():
    draft = _draft()
    draft["tasks"][0].update({
        "checklist": ["  Verify   output ", {"id": "docs", "text": "Document output"}],
        "meetingActionItems": [{"title": "Discuss rollout"}],
        "meetingDiscussionPoints": [{"text": "Risk context"}],
    })

    task = _validate(draft)["tasks"][0]

    assert task["checklist"][0]["text"] == "Verify output"
    assert task["checklist"][0]["id"].startswith("checklist-")
    assert task["checklist"][1] == {"id": "docs", "text": "Document output", "done": False}
    assert len(task["checklist"]) == 2
    assert task["meetingActionItems"] == [{"title": "Discuss rollout"}]
    assert task["meetingDiscussionPoints"] == [{"text": "Risk context"}]

    draft["tasks"][0]["checklist"] = "not-a-list"
    with pytest.raises(DraftValidationError) as error:
        _validate(draft)
    assert "invalid_checklist" in _codes(error)


def test_missing_unknown_and_excluded_actors_report_role_paths():
    draft = _draft()
    draft["tasks"][0].pop("responsibleActor")
    draft["tasks"][0]["executorActor"] = {"type": "agent", "id": "missing"}
    draft["tasks"].append({
        **draft["tasks"][0],
        "title": "Excluded",
        "responsibleActor": {"type": "agent", "id": "excluded"},
        "executorActor": {"type": "agent", "id": "builder"},
    })

    with pytest.raises(DraftValidationError) as error:
        _validate(draft)

    assert {"actor_required", "agent_not_found", "agent_not_assignable"} <= _codes(error)
    paths = {issue.path for issue in error.value.issues}
    assert "tasks[0].responsibleActor" in paths
    assert "tasks[0].executorActor" in paths
    assert "tasks[1].responsibleActor" in paths


def test_reviewer_recommendation_does_not_assign_before_user_confirmation():
    draft = _draft()
    draft["tasks"][0]["reviewerRecommendation"] = {
        "recommended": True,
        "triggers": ["critical_delivery"],
        "rationale": "Production launch requires independent review",
        "candidate": {"type": "agent", "id": "reviewer"},
    }
    normalized = _validate(draft)
    assert normalized["tasks"][0]["reviewerActor"] is None
    assert normalized["tasks"][0]["reviewerRecommendation"]["candidate"]["id"] == "reviewer"

    draft["tasks"][0]["reviewerActor"] = {"type": "agent", "id": "reviewer"}
    with pytest.raises(DraftValidationError) as error:
        _validate(draft)
    assert "reviewer_not_user_confirmed" in _codes(error)

    confirmed = _validate(draft, reviewer_assignment_confirmed=True)
    assert confirmed["tasks"][0]["reviewerAgentId"] == "reviewer"


def test_reviewer_recommendation_requires_trigger_rationale_and_agent_candidate():
    draft = _draft()
    draft["tasks"][0]["reviewerRecommendation"] = {
        "recommended": True,
        "triggers": [],
        "candidate": {"type": "user", "id": "user:local"},
    }
    with pytest.raises(DraftValidationError) as error:
        _validate(draft)
    assert {"reviewer_trigger_required", "required", "agent_actor_required"} <= _codes(error)

    draft["tasks"][0]["reviewerRecommendation"] = {
        "recommended": False,
        "triggers": ["high_risk"],
    }
    with pytest.raises(DraftValidationError) as inconsistent:
        _validate(draft)
    assert "reviewer_recommendation_required" in _codes(inconsistent)


def test_recurring_projects_require_templates_while_reusable_attribute_does_not():
    reusable = _validate(_draft(projectType="reusable"))
    assert reusable["template"] == {"mode": "none"}

    with pytest.raises(DraftValidationError) as error:
        _validate(_draft(projectType="recurring"))
    assert "template_required" in _codes(error)


def test_recurring_project_validates_schedule_and_timezone():
    draft = _draft(
        projectType="recurring",
        template={"mode": "create", "name": "Weekly launch"},
        recurrence={
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "Asia/Shanghai"},
        },
    )
    normalized = _validate(draft)
    assert normalized["recurrence"]["paused"] is False
    assert normalized["recurrence"]["executionMode"] == "create_only"

    draft["recurrence"]["executionMode"] = "start_sometimes"
    with pytest.raises(DraftValidationError) as execution_error:
        _validate(draft)
    assert "invalid_recurrence_execution_mode" in _codes(execution_error)

    draft["recurrence"]["executionMode"] = "create_and_execute"
    draft["projectExecutionEnabled"] = False
    with pytest.raises(DraftValidationError) as disabled_error:
        _validate(draft)
    assert "recurrence_execution_requires_project_execution" in _codes(disabled_error)

    draft["recurrence"]["executionMode"] = "create_only"
    draft["recurrence"]["schedule"]["timezone"] = "Mars/Olympus"
    with pytest.raises(DraftValidationError) as error:
        _validate(draft)
    assert "invalid_recurrence_schedule" in _codes(error)


def test_task_limit_and_idempotency_key_are_enforced():
    config_values = ProjectAuthoringConfig.from_env({}).__dict__
    config_values["max_initial_tasks"] = 1
    config = ProjectAuthoringConfig(**config_values)
    draft = _draft(tasks=_draft()["tasks"] * 2)
    with pytest.raises(DraftValidationError) as error:
        _validate(draft, config=config)
    assert "too_many_tasks" in _codes(error)

    with pytest.raises(DraftValidationError) as key_error:
        validate_idempotency_key("short")
    assert key_error.value.issues[0].code == "invalid_idempotency_key"
