#!/usr/bin/env python3
"""Focused tests for project actor references and legacy projections."""

import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import project_actors


AGENTS = {
    "agent-a": {"id": "agent-a", "providerKind": "codex"},
    "agent-b": {"id": "agent-b", "providerKind": "openclaw"},
    "archive-manager": {"id": "archive-manager", "providerKind": "openclaw"},
}


def lookup_agent(agent_id):
    return AGENTS.get(agent_id)


def is_excluded(agent_id):
    return agent_id == "archive-manager"


def validate(task):
    return project_actors.validate_task_actor_references(
        task, lookup_agent=lookup_agent, is_excluded_agent=is_excluded,
    )


def test_same_agent_can_be_responsible_and_executor_with_optional_reviewer():
    actors = validate({
        "responsibleActor": {"type": "agent", "id": "agent-a"},
        "executorActor": {"type": "agent", "id": "agent-a"},
        "reviewerActor": None,
    })

    assert actors == {
        "responsible": {"type": "agent", "id": "agent-a"},
        "executor": {"type": "agent", "id": "agent-a"},
        "reviewer": None,
    }
    assert project_actors.legacy_task_role_fields(actors) == {
        "assignee": "agent-a", "executorAgentId": "agent-a", "reviewerAgentId": None,
    }


def test_distinct_agents_and_registered_reviewer_are_valid():
    actors = validate({
        "responsibleActor": {"type": "agent", "id": "agent-a"},
        "executorActor": {"type": "agent", "id": "agent-b"},
        "reviewerActor": {"type": "agent", "id": "agent-a"},
    })

    assert project_actors.legacy_task_role_fields(actors) == {
        "assignee": "agent-a", "executorAgentId": "agent-b", "reviewerAgentId": "agent-a",
    }


def test_local_user_is_supported_for_responsible_and_executor_roles():
    actors = validate({
        "responsibleActor": {"type": "user", "id": "user"},
        "executorActor": {"type": "user", "id": "user:local"},
    })

    assert actors["responsible"] == {"type": "user", "id": "user:local"}
    assert actors["executor"] == {"type": "user", "id": "user:local"}
    assert project_actors.legacy_task_role_fields(actors) == {
        "assignee": "user:local", "executorAgentId": None, "reviewerAgentId": None,
    }


@pytest.mark.parametrize("missing_role", ["responsibleActor", "executorActor"])
def test_missing_required_actor_has_stable_role_error(missing_role):
    task = {
        "responsibleActor": {"type": "agent", "id": "agent-a"},
        "executorActor": {"type": "agent", "id": "agent-b"},
    }
    task[missing_role] = None

    with pytest.raises(project_actors.ActorReferenceError) as captured:
        validate(task)

    assert captured.value.code == "actor_required"
    assert captured.value.role == missing_role.removesuffix("Actor")


@pytest.mark.parametrize(
    ("agent_id", "expected_code"),
    [("missing", "agent_not_found"), ("archive-manager", "agent_not_assignable")],
)
def test_unknown_and_excluded_agents_are_rejected(agent_id, expected_code):
    with pytest.raises(project_actors.ActorReferenceError) as captured:
        validate({
            "responsibleActor": {"type": "agent", "id": agent_id},
            "executorActor": {"type": "agent", "id": "agent-b"},
        })

    assert captured.value.code == expected_code
    assert captured.value.role == "responsible"
    assert captured.value.actor_id == agent_id


def test_reviewer_must_be_registered_agent_when_present():
    with pytest.raises(project_actors.ActorReferenceError) as captured:
        validate({
            "responsibleActor": {"type": "agent", "id": "agent-a"},
            "executorActor": {"type": "agent", "id": "agent-b"},
            "reviewerActor": {"type": "user", "id": "user:local"},
        })

    assert captured.value.code == "agent_actor_required"
    assert captured.value.role == "reviewer"


def test_legacy_fields_are_read_as_typed_actor_references():
    actors = project_actors.task_actor_references({
        "assignee": "agent-a",
        "executorAgentId": "agent-b",
        "reviewerAgentId": "agent-a",
    })

    assert actors == {
        "responsible": {"type": "agent", "id": "agent-a"},
        "executor": {"type": "agent", "id": "agent-b"},
        "reviewer": {"type": "agent", "id": "agent-a"},
    }


def test_explicit_modern_null_reviewer_overrides_legacy_reviewer():
    actors = project_actors.task_actor_references({
        "assignee": "agent-a",
        "executorAgentId": "agent-b",
        "reviewerAgentId": "agent-a",
        "reviewerActor": None,
    })

    assert actors["reviewer"] is None
