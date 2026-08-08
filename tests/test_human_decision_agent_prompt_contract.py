"""Executable prompt contracts that let meeting/project Agents raise decisions."""

from services import (
    meeting_prompt_documents,
    project_execution_prompt_formatting,
    workflow_prompt_formatting,
)


def test_meeting_turn_exposes_exact_decision_skill_request_contract():
    prompt = meeting_prompt_documents.turn_prompt(
        meeting={
            "id": "meeting-decision-contract",
            "topic": "Choose rollout",
            "participants": ["meeting-agent"],
            "round": 1,
            "maxRounds": 2,
        },
        speaker="meeting-agent",
        stage="active_discussion",
        context_values={},
    )

    assert "/skills/vo-human-decision/SKILL.md" in prompt
    assert "/api/agent/human-decisions" in prompt
    assert "X-VO-Agent-Action" in prompt
    assert "human-decision" in prompt
    assert "X-VO-Agent-Id" in prompt
    assert "meeting-agent" in prompt
    assert "meeting-decision-contract" in prompt
    assert "End the affected turn after the request is created" in prompt


def test_project_execution_exposes_exact_decision_skill_request_contract():
    prompt = project_execution_prompt_formatting.render_project_execution_prompt(
        project={"id": "project-decision-contract", "title": "Project", "description": "Ship"},
        task={"id": "task-decision-contract", "title": "Task", "description": "Choose rollout"},
        attempt={
            "id": "attempt-decision-contract",
            "executor": {"id": "project-agent"},
        },
        workspace="/tmp/project-decision-contract",
        checklist_text="- verify rollout",
        rework_feedback="",
    )

    assert "/skills/vo-human-decision/SKILL.md" in prompt
    assert "/api/agent/human-decisions" in prompt
    assert "X-VO-Agent-Action" in prompt
    assert "human-decision" in prompt
    assert "X-VO-Agent-Id" in prompt
    assert "project-agent" in prompt
    assert "project-decision-contract" in prompt
    assert "task-decision-contract" in prompt
    assert "End the affected turn after the request is created" in prompt


def test_project_workflow_exposes_exact_decision_skill_request_contract():
    prompt = workflow_prompt_formatting.render_workflow_task_prompt(
        task={
            "id": "workflow-task-decision-contract",
            "title": "Workflow task",
            "description": "Choose rollout",
            "assignee": "workflow-agent",
        },
        acceptance_checklist=[{"id": "verify", "text": "Verify rollout", "done": False}],
        project={
            "id": "workflow-project-decision-contract",
            "title": "Workflow project",
            "description": "Ship",
        },
        warning_text="",
        project_specific_checklist_text=False,
    )

    assert "/skills/vo-human-decision/SKILL.md" in prompt
    assert "/api/agent/human-decisions" in prompt
    assert "workflow-agent" in prompt
    assert "workflow-project-decision-contract" in prompt
    assert "workflow-task-decision-contract" in prompt
