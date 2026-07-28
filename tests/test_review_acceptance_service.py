import copy
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import review_acceptance
from services.project_orchestration import EXECUTION_MODEL_STAGE_PIPELINE_V1, default_orchestration_state


def test_normalize_review_fails_closed_and_redacts_all_text_fields():
    redact = lambda value: str(value or "").replace("secret", "[redacted]")
    malformed = review_acceptance.normalize_review(
        {"ok": True, "status": "completed", "reply": '{"status":"pass"}'},
        {"id": "r", "providerKind": "codex"}, "a", "r1",
        redact=redact, now=lambda: "now",
    )
    assert malformed["status"] == "blocked"

    valid = review_acceptance.normalize_review(
        {"ok": True, "status": "completed", "review": {
            "status": "needs_more_work", "summary": "secret summary",
            "rationale": "secret reason", "items": [
                {"text": "secret item", "detail": {"api_key": "canary"}},
                {"text": "x" * 5000},
            ],
        }},
        {"id": "r", "providerKind": "codex"}, "a", "r2",
        redact=redact, now=lambda: "now",
    )
    assert valid["status"] == "needs_more_work"
    assert "secret" not in str(valid)
    assert "canary" not in str(valid)
    assert "detail" not in valid["items"][0]
    assert len(valid["items"][1]["text"]) < 1100


def test_entry_context_does_not_derive_actor_from_request_payload():
    context = review_acceptance.EntryContext.http()
    forged_body = {"actor": "admin", "by": "system"}
    assert context.actor == "user"
    assert context.actor not in forged_body.values()
    assert context.source == "http"


def test_stable_notification_intent_is_staged_once_and_sanitized():
    project = {"id": "p", "title": "secret project"}
    task = {
        "id": "t", "title": "secret task",
        "reviewResult": {"summary": "secret review"},
        "attempts": [{"id": "a"}],
    }
    redact = lambda value: str(value or "").replace("secret", "[redacted]")
    intent = review_acceptance.build_acceptance_intent(
        project, task, "a", "secret reason", redact=redact,
        open_url=lambda project_id, task_id: f"https://example.test/{project_id}/{task_id}",
    )
    assert "secret" not in str(intent)
    assert review_acceptance.stage_notification_intent(task, "a", intent, lambda: "t1") is True
    assert review_acceptance.stage_notification_intent(task, "a", intent, lambda: "t2") is True
    local = review_acceptance.notification_intent(task, "a", intent["id"])
    assert local["createdAt"] == "t1"
    assert len(task["attempts"][0]["notificationIntents"]) == 1


def test_marked_project_acceptance_reconciles_stage_without_legacy_continue():
    project = {
        "id": "p1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
        },
        "projectExecutionEnabled": True,
        "projectExecutionStartMode": "continuous",
        "tasks": [{
            "id": "t1",
            "title": "Task",
            "executionStage": 1,
            "stageRunId": "run-1",
            "executionState": "awaiting_user_acceptance",
            "reviewResult": {"status": "pass", "attemptId": "attempt-1"},
            "attempts": [{"id": "attempt-1", "stageRunId": "run-1"}],
            "checklist": [{"id": "done", "text": "Done", "done": True}],
        }],
    }

    class Repo:
        def get(self, project_id):
            return copy.deepcopy(project)

        def update(self, project_id, mutator):
            working = copy.deepcopy(project)
            result = mutator(working)
            project.clear()
            project.update(working)
            return result

    scheduled = []
    reconciled = []
    result = review_acceptance.acceptance(
        "p1",
        "t1",
        {"action": "accept", "attemptId": "attempt-1"},
        context=review_acceptance.EntryContext.http(),
        repository=Repo(),
        ports=review_acceptance.AcceptancePorts(
            enabled=lambda project: True,
            validate_workspace=lambda path: {"ok": True, "path": path},
            active_task=lambda project: None,
            resolve_roles=lambda project, task, allow_skip: {"ok": True},
            automatic_snapshot=lambda project, path: {"ok": True, "snapshot": {}},
            requires_acceptance=lambda task: True,
            mark_done=lambda project, task, actor, reason, attempt_id, **kwargs: task.update({"executionState": "done", "completedAt": "now"}) or {"ok": True},
            transition=lambda *args, **kwargs: None,
            log_activity=lambda *args, **kwargs: None,
            redact=lambda value: str(value or ""),
            now=lambda: "now",
            new_id=lambda: "unused",
            create_cancel_flag=lambda attempt_id: object(),
            launcher=lambda callback: callback(),
            runner=lambda *args, **kwargs: None,
            schedule_continue=lambda project_id, reason: scheduled.append((project_id, reason)),
            notify_intervention=lambda *args, **kwargs: None,
            is_stage_pipeline=lambda project: True,
            reconcile_terminal=lambda project_id, task_id, attempt_id, reason: reconciled.append((project_id, task_id, attempt_id, reason)),
        ),
    )

    assert result["ok"] is True
    assert result["flowContinues"] is False
    assert scheduled == []
    assert reconciled == [("p1", "t1", "attempt-1", "user_accepted")]
    assert project["tasks"][0]["executionState"] == "done"
    assert project.get("projectExecutionFlowActive") is None
