import threading

from app.services.meeting_callbacks import TrustedCallbackContext, begin, complete
from app.services.meeting_notifications import failure_intent, mark, request_intent, sanitize, stage
from app.services.meeting_repository import MeetingDomainRepository


def unified():
    return {
        "requests": {"r1": {"id": "r1", "source": {"projectId": "p1", "taskId": "t1"}, "conversion": {"meetingId": "m1"}}},
        "meetings": {"m1": {"id": "m1", "topic": "Meeting"}},
        "idempotency": {"callbacks": {}},
    }


def context(event="e1", actor="u1"):
    return TrustedCallbackContext(event_id=event, message_id="msg", chat_id="chat", actor_id=actor)


def test_callback_claim_completion_and_replay_are_persistent_and_bounded():
    data = unified()
    claimed = begin(data, "confirm_meeting_request", "r1", context(), "now")
    assert claimed["claimed"] is True
    response = {"ok": True, "toast": {"type": "success", "content": "done"}, "outcome": {"handled": True, "businessStatus": "confirmed", "meetingId": "m1"}}
    complete(data, claimed["key"], response, "later")
    replay = begin(data, "confirm_meeting_request", "r1", context(), "again")
    assert replay["replay"] is True and replay["response"]["outcome"]["meetingId"] == "m1"


def test_callback_rejects_forged_linkage_and_never_trusts_card_actor_fields():
    data = unified()
    forged = begin(data, "confirm_meeting_request", "r1", context(actor="verified-user"), "now", {"project_id": "other", "actor": "forged"})
    assert forged["businessStatus"] == "callback_linkage_invalid" and data["idempotency"]["callbacks"] == {}
    valid = begin(data, "confirm_meeting_request", "r1", context(actor="verified-user"), "now", {"project_id": "p1"})
    record = data["idempotency"]["callbacks"][valid["key"]]
    assert record["actorId"] == "verified-user"


def test_repository_serializes_concurrent_callback_claims(tmp_path):
    repository = MeetingDomainRepository(tmp_path)
    def seed(data):
        data["meetings"]["m1"] = {"id": "m1", "stage": "completed", "participants": []}
        data["requests"]["r1"] = {"id": "r1", "status": "confirmed", "source": {"projectId": "p1", "taskId": "t1"}, "conversion": {"meetingId": "m1"}}
    repository.update(seed)
    barrier = threading.Barrier(3); results = []
    def worker():
        barrier.wait()
        results.append(repository.update(lambda data: begin(data, "confirm_meeting_request", "r1", context(), "now"))[1])
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join(timeout=3)
    assert sum(bool(result.get("claimed")) for result in results) == 1
    assert sum(bool(result.get("inProgress")) for result in results) == 1


def test_callback_processing_claim_can_be_recovered_after_lease_expires():
    data = unified()
    first = begin(data, "confirm_meeting_request", "r1", context(), "2026-07-13T00:00:00Z")
    active = begin(data, "confirm_meeting_request", "r1", context(), "2026-07-13T00:04:59Z")
    reclaimed = begin(data, "confirm_meeting_request", "r1", context(), "2026-07-13T00:05:00Z")
    assert first["claimed"] is True and active["inProgress"] is True
    assert reclaimed["claimed"] is True
    assert data["idempotency"]["callbacks"][reclaimed["key"]]["startedAt"] == "2026-07-13T00:05:00Z"


def test_notification_dto_redacts_secrets_paths_raw_and_transcripts():
    value = sanitize({"summary": "password=hunter2 failed at /tmp/private/file", "path": "/Users/private/secret", "appSecret": "plain-secret", "raw": "token=abc", "transcript": "private", "nested": ["api_key=xyz"]})
    text = str(value)
    assert "hunter2" not in text and "abc" not in text and "xyz" not in text and "plain-secret" not in text and "/Users/private" not in text and "/tmp/private" not in text
    assert "transcript" not in value and "raw" not in value


def test_notification_stage_failure_retry_and_sent_dedupe_do_not_change_business_state():
    data = unified(); request = data["requests"]["r1"]; request["status"] = "pending"
    intent = request_intent(request, "pending", summary="hello", actions=[], details=[])
    first = stage(data, "request", "r1", intent, "now")
    mark(data, "request", "r1", first["dedupeKey"], {"ok": False, "error": "token=secret"}, "later")
    assert request["status"] == "pending"
    retry = stage(data, "request", "r1", intent, "retry")
    assert retry["status"] == "staged"
    mark(data, "request", "r1", retry["dedupeKey"], {"ok": True, "record": {"id": "n1"}}, "sent")
    duplicate = stage(data, "request", "r1", intent, "again")
    assert duplicate["status"] == "skipped_duplicate"
    marker = request["notificationIntents"][intent["id"]]
    assert marker["attempts"] == 2 and marker["deliveryStatus"] == "sent"


def test_failure_intent_has_stable_key_and_bounded_redacted_summary():
    intent = failure_intent(
        {"id": "m1", "topic": "T", "stage": "failed", "lastEventSequence": 8},
        {"error": "secret=abc " + "x" * 3000, "reason": "moderator_failed"},
        "http://localhost/#meeting=m1",
    )
    assert intent["id"] == "meeting-failure:m1:8"
    assert "abc" not in intent["summary"] and len(intent["summary"]) <= 2000
