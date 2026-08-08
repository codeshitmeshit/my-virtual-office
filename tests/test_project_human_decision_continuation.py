import copy
import threading

from app.services.human_decision_chat_continuation import ContinuationDispatchResult
from app.services.human_decisions import HumanDecisionContinuationClaim
from app.services.project_human_decision_continuation import (
    ProjectHumanDecisionContinuation,
    ProjectContinuationPorts,
    mark_attempt_waiting,
)
from app.services.project_repository import ProjectRepository


def repository():
    state = {"projects": [{
        "id": "project-1",
        "tasks": [
            {"id": "task-a", "activeAttemptId": "attempt-a", "attempts": [{
                "id": "attempt-a", "status": "executing", "stageRunId": "run-1",
                "executor": {"id": "agent-1"}, "runnerClaimedAt": "now",
            }]},
            {"id": "task-b", "activeAttemptId": "attempt-b", "attempts": [{
                "id": "attempt-b", "status": "executing", "stageRunId": "run-1",
                "executor": {"id": "agent-2"},
            }]},
        ],
    }]}
    lock = threading.Lock()

    def load():
        with lock:
            return copy.deepcopy(state)

    def save(value):
        with lock:
            state.clear()
            state.update(copy.deepcopy(value))

    return ProjectRepository(load_projects=load, save_projects=save)


def claim():
    return HumanDecisionContinuationClaim(
        decision_id="decision-1", claim_token="claim-1", kind="task", agent_id="agent-1",
        binding={
            "projectId": "project-1", "taskId": "task-a", "attemptId": "attempt-a",
            "runId": "run-1", "mode": "stage",
        },
        attempts=1,
        decision={
            "id": "decision-1",
            "source": {"type": "task", "id": "task-a", "projectId": "project-1", "label": "A"},
            "title": "Confirm rollout",
            "situation": "Choose rollout",
            "resolution": {"answer": "Staged rollout", "optionId": "B"},
        },
    )


def test_mark_attempt_waiting_preserves_active_attempt_and_sibling():
    repo = repository()

    result = mark_attempt_waiting(
        repo, project_id="project-1", task_id="task-a", attempt_id="attempt-a",
        decision_id="decision-1", agent_id="agent-1", now=lambda: "waiting-at",
    )

    saved = repo.get("project-1")
    assert result["ok"] is True
    assert saved["tasks"][0]["activeAttemptId"] == "attempt-a"
    assert saved["tasks"][0]["attempts"][0]["status"] == "awaiting_user_decision"
    assert saved["tasks"][0]["attempts"][0]["humanDecisionId"] == "decision-1"
    assert saved["tasks"][1]["attempts"][0]["status"] == "executing"


def test_stage_resume_submits_only_bound_task_and_keeps_sibling_running():
    repo = repository()
    mark_attempt_waiting(
        repo, project_id="project-1", task_id="task-a", attempt_id="attempt-a",
        decision_id="decision-1", agent_id="agent-1", now=lambda: "waiting-at",
    )
    submitted = []
    adapter = ProjectHumanDecisionContinuation(ports=ProjectContinuationPorts(
        repository=repo,
        now=lambda: "resume-at",
        new_id=lambda: "comment-1",
        launch_direct=lambda project_id, task_id, attempt_id: submitted.append({
            "mode": "direct", "projectId": project_id, "taskId": task_id, "attemptId": attempt_id,
        }) or True,
        submit_stage=lambda project_id, task_id, run_id, attempt_id: submitted.append({
            "mode": "stage", "projectId": project_id, "taskId": task_id,
            "runId": run_id, "attemptId": attempt_id,
        }) or True,
    ))

    result = adapter.dispatch(claim())

    assert result == ContinuationDispatchResult("dispatched")
    assert submitted == [{
        "mode": "stage", "projectId": "project-1", "taskId": "task-a",
        "runId": "run-1", "attemptId": "attempt-a",
    }]
    saved = repo.get("project-1")
    resumed = saved["tasks"][0]["attempts"][0]
    assert resumed["status"] == "executing"
    assert resumed["decisionResume"]["answer"] == "Staged rollout"
    assert "runnerClaimedAt" not in resumed
    assert saved["tasks"][0]["comments"] == [{
        "id": "comment-1",
        "kind": "human_decision",
        "author": "human_decision",
        "text": "Confirm rollout: Staged rollout",
        "createdAt": "resume-at",
        "decisionId": "decision-1",
        "decisionTitle": "Confirm rollout",
        "decisionAnswer": "Staged rollout",
        "customAnswer": "",
    }]
    assert saved["tasks"][1]["attempts"][0]["status"] == "executing"


def test_replaced_attempt_is_not_resumed():
    repo = repository()
    mark_attempt_waiting(
        repo, project_id="project-1", task_id="task-a", attempt_id="attempt-a",
        decision_id="decision-1", agent_id="agent-1", now=lambda: "waiting-at",
    )
    repo.update("project-1", lambda project: project["tasks"][0].update({"activeAttemptId": "replacement"}))
    adapter = ProjectHumanDecisionContinuation(ports=ProjectContinuationPorts(
        repository=repo, now=lambda: "resume-at", new_id=lambda: "comment-1",
        launch_direct=lambda *args: True, submit_stage=lambda *args: True,
    ))

    assert adapter.dispatch(claim()) == ContinuationDispatchResult("failed", "project_attempt_replaced")


def test_rejected_submission_restores_waiting_state_for_safe_retry():
    repo = repository()
    mark_attempt_waiting(
        repo, project_id="project-1", task_id="task-a", attempt_id="attempt-a",
        decision_id="decision-1", agent_id="agent-1", now=lambda: "waiting-at",
    )
    accepted = [False, True]
    adapter = ProjectHumanDecisionContinuation(ports=ProjectContinuationPorts(
        repository=repo, now=lambda: "resume-at", new_id=lambda: "comment-1", launch_direct=lambda *args: True,
        submit_stage=lambda *args: accepted.pop(0),
    ))

    first = adapter.dispatch(claim())
    waiting = repo.get("project-1")["tasks"][0]["attempts"][0]
    second = adapter.dispatch(claim())

    assert first == ContinuationDispatchResult("not_dispatched_retryable", "project_dispatch_rejected")
    assert waiting["status"] == "awaiting_user_decision"
    assert second == ContinuationDispatchResult("dispatched")
    saved_comments = repo.get("project-1")["tasks"][0]["comments"]
    assert len(saved_comments) == 1
    assert saved_comments[0]["decisionId"] == "decision-1"
