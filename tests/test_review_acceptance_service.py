import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import review_acceptance


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
