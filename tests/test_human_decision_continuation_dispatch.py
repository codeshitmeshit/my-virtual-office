from app.services.human_decision_chat_continuation import ContinuationDispatchResult
from app.services.human_decision_continuation_dispatch import HumanDecisionContinuationDispatcher
from app.services.human_decisions import HumanDecisionStore
from tests.test_human_decisions import request_payload


class Adapter:
    def __init__(self, outcome="dispatched"):
        self.outcome = outcome
        self.claims = []

    def dispatch(self, claim):
        self.claims.append(claim)
        return ContinuationDispatchResult(self.outcome)


class Receipt:
    def __init__(self, events):
        self.events = events

    def send(self, claim):
        self.events.append(("receipt", claim.decision_id, claim.decision["resolution"]["answer"]))
        return {"ok": True, "status": "sent", "application": "notification"}


def test_dispatcher_routes_each_claim_to_its_native_adapter(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    chat = Adapter()
    meeting = Adapter()
    task = Adapter()
    bindings = [
        ("chat", {"type": "chat", "id": "conversation-1", "label": "Chat"}, {"conversationId": "conversation-1"}),
        ("meeting", {"type": "meeting", "id": "meeting-1", "label": "Meeting"}, {"meetingId": "meeting-1"}),
        ("task", {"type": "task", "id": "task-1", "projectId": "project-1", "label": "Task"}, {
            "projectId": "project-1", "taskId": "task-1", "attemptId": "attempt-1", "mode": "direct",
        }),
    ]
    for kind, source, binding in bindings:
        decision_id = store.create(request_payload(
            idempotencyKey=f"{kind}:dispatch",
            source=source,
        ))["decision"]["id"]
        store.bind_continuation(decision_id, kind=kind, agent_id="agent-1", binding=binding)
        store.resolve(decision_id, option_id="A", channel="local")
        store.queue_continuation(decision_id)

    dispatcher = HumanDecisionContinuationDispatcher(
        store=store,
        adapters={"chat": chat, "meeting": meeting, "task": task},
    )
    events = dispatcher.process_due(now="2026-08-03T08:00:00+00:00")

    assert [event["status"] for event in events] == ["completed", "completed", "completed"]
    assert [claim.kind for claim in chat.claims] == ["chat"]
    assert [claim.kind for claim in meeting.claims] == ["meeting"]
    assert [claim.kind for claim in task.claims] == ["task"]


def test_successful_resume_sends_decision_result_receipt_after_dispatch(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        idempotencyKey="chat:receipt",
        source={"type": "chat", "id": "conversation-1", "label": "Chat"},
    ))["decision"]["id"]
    store.bind_continuation(
        decision_id,
        kind="chat",
        agent_id="agent-1",
        binding={"conversationId": "conversation-1"},
    )
    store.resolve(decision_id, custom_answer="先灰度一周", channel="feishu")
    store.queue_continuation(decision_id)
    sequence = []

    class OrderedAdapter:
        def dispatch(self, claim):
            sequence.append(("resume", claim.decision_id))
            return ContinuationDispatchResult("dispatched")

    dispatcher = HumanDecisionContinuationDispatcher(store=store, adapters={"chat": OrderedAdapter()})
    dispatcher._receipt = Receipt(sequence)

    events = dispatcher.process_due(now="2026-08-03T08:00:00+00:00")

    assert sequence == [
        ("resume", decision_id),
        ("receipt", decision_id, "先灰度一周"),
    ]
    assert events == [{
        "decisionId": decision_id,
        "status": "completed",
        "attempts": 1,
        "receipt": {"ok": True, "status": "sent", "application": "notification"},
    }]


def test_failed_resume_does_not_claim_conversation_is_running(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        idempotencyKey="chat:no-false-receipt",
        source={"type": "chat", "id": "conversation-1", "label": "Chat"},
    ))["decision"]["id"]
    store.bind_continuation(
        decision_id,
        kind="chat",
        agent_id="agent-1",
        binding={"conversationId": "conversation-1"},
    )
    store.resolve(decision_id, option_id="A", channel="local")
    store.queue_continuation(decision_id)
    receipts = []
    dispatcher = HumanDecisionContinuationDispatcher(
        store=store,
        adapters={"chat": Adapter("failed")},
    )
    dispatcher._receipt = Receipt(receipts)

    events = dispatcher.process_due(now="2026-08-03T08:00:00+00:00")

    assert events[0]["status"] == "failed"
    assert receipts == []
