from __future__ import annotations

from app.services.human_decision_workflow import HumanDecisionWorkflow
from app.services.human_decisions import HumanDecisionStore
from tests.test_human_decisions import request_payload


class DeliveryStub:
    def __init__(self):
        self.sent = []
        self.updated = []

    def deliver(self, decision, **configs):
        self.sent.append((decision, configs))
        return {"ok": True, "status": "sent", "messageId": "om_decision", "application": "notification"}

    def update_terminal(self, decision, records, **configs):
        self.updated.append((decision, records, configs))
        return [{"ok": True, "status": "updated", "messageId": "om_decision"}]


class FailingTerminalDelivery(DeliveryStub):
    def update_terminal(self, decision, records, **configs):
        super().update_terminal(decision, records, **configs)
        raise RuntimeError("card update failed")


class ContinuationStub:
    def __init__(self):
        self.queued = []
        self.processed = []
        self.kicks = 0

    def queue(self, decision_id):
        self.queued.append(decision_id)
        return {"queued": True}

    def process_due(self, *, now=None):
        self.processed.append(now)
        return []


def workflow(tmp_path, continuation=None, continuation_binding=None):
    delivery = DeliveryStub()
    continuation = continuation or None
    service = HumanDecisionWorkflow(
        store=HumanDecisionStore(tmp_path / "state.json"),
        delivery=delivery,
        notification_config=lambda: {"appId": "notification", "appSecret": "secret", "receiveId": "oc_n"},
        chat_config=lambda: {"appId": "chat", "appSecret": "secret"},
        fallback_chat_id=lambda: "oc_chat",
        chat_continuation=continuation,
        continuation=continuation,
        continuation_binding=continuation_binding,
        continuation_kick=(
            (lambda: setattr(continuation, "kicks", continuation.kicks + 1))
            if continuation is not None
            else None
        ),
    )
    return service, delivery


def test_native_source_binding_is_queued_by_generic_continuation(tmp_path):
    continuation = ContinuationStub()
    service, _ = workflow(
        tmp_path,
        continuation,
        continuation_binding=lambda decision, agent_id: {
            "kind": "meeting",
            "binding": {"meetingId": decision["source"]["id"]},
        },
    )
    decision_id = service.create(
        request_payload(
            idempotencyKey="meeting:native",
            source={"type": "meeting", "id": "meeting-1", "label": "Meeting"},
        ),
        agent_id="agent-1",
    )["decision"]["id"]

    service.resolve(decision_id, {"optionId": "A"}, channel="local")

    assert continuation.queued == [decision_id]


def test_create_delivers_once_and_returns_latest_snapshot(tmp_path):
    service, delivery = workflow(tmp_path)
    first = service.create(request_payload())
    second = service.create(request_payload())
    assert first["created"] is True
    assert second["created"] is False
    assert len(delivery.sent) == 1
    assert first["snapshot"]["decisions"][0]["sync"]["feishuStatus"] == "sent"


def test_local_resolve_updates_original_feishu_card(tmp_path):
    service, delivery = workflow(tmp_path)
    decision_id = service.create(request_payload())["decision"]["id"]
    result = service.resolve(decision_id, {"optionId": "B"}, channel="local", actor={"id": "local-user"})
    assert result["decision"]["resolution"]["channel"] == "local"
    assert delivery.updated[0][1][0]["messageId"] == "om_decision"


def test_feishu_callback_custom_answer_wins_and_is_idempotent(tmp_path):
    service, delivery = workflow(tmp_path)
    decision_id = service.create(request_payload())["decision"]["id"]
    value = {"action": "human_decision_submit", "decision_id": decision_id, "option_id": "A"}
    first = service.handle_feishu_action(value, {"custom_answer": "只给设计团队灰度"}, {"id": "ou_user"})
    second = service.handle_feishu_action(value, {"custom_answer": "只给设计团队灰度"}, {"id": "ou_user"})
    assert first["handled"] is True
    assert first["decision"]["resolution"]["answer"] == "只给设计团队灰度"
    assert first["decision"]["resolution"]["optionId"] is None
    assert second["idempotent"] is True
    assert len(delivery.updated) == 1


def test_unrelated_feishu_action_is_not_handled(tmp_path):
    service, _ = workflow(tmp_path)
    assert service.handle_feishu_action({"action": "other"}, {}, {}) == {"handled": False}


def test_due_reminder_is_delivered_and_terminal_card_is_updated(tmp_path):
    service, delivery = workflow(tmp_path)
    service.create(request_payload(risk="low", nextReminderAt="2026-08-03T08:00:00+00:00"))
    service.process_due("2026-08-03T08:00:00+00:00")
    service.process_due("2026-08-04T08:00:00+00:00")
    third = service.process_due("2026-08-05T08:00:00+00:00")
    events = service.process_due("2026-08-06T08:00:00+00:00")
    assert third[0]["kind"] == "reminder"
    assert events[0]["kind"] == "timeout_resolved"
    assert len(delivery.sent) == 4  # initial request + three reminder cards
    assert len(delivery.updated) == 1


def test_execution_start_locks_the_resolved_decision(tmp_path):
    service, delivery = workflow(tmp_path)
    decision_id = service.create(request_payload())["decision"]["id"]
    service.resolve(decision_id, {"optionId": "B"}, channel="local")
    locked = service.mark_execution_started(decision_id, {"impact": "灰度批次已经创建"})
    assert locked["decision"]["status"] == "locked"
    assert locked["decision"]["execution"] == {"started": True, "impact": "灰度批次已经创建"}


def test_chat_create_binds_trusted_agent_and_task_create_does_not(tmp_path):
    continuation = ContinuationStub()
    service, _ = workflow(tmp_path, continuation)
    chat = service.create(
        request_payload(
            idempotencyKey="chat:workflow",
            source={"type": "chat", "id": "conversation-1", "label": "聊天"},
        ),
        agent_id="agent-1",
    )
    task = service.create(request_payload(idempotencyKey="task:workflow"), agent_id="agent-1")

    assert chat["decision"]["continuation"]["status"] == "waiting"
    assert "continuation" not in task["decision"]


def test_first_local_or_feishu_resolution_queues_and_kicks_once(tmp_path):
    continuation = ContinuationStub()
    service, _ = workflow(tmp_path, continuation)
    local_id = service.create(
        request_payload(
            idempotencyKey="chat:local",
            source={"type": "chat", "id": "conversation-local", "label": "聊天"},
        ),
        agent_id="agent-1",
    )["decision"]["id"]
    feishu_id = service.create(
        request_payload(
            idempotencyKey="chat:feishu",
            source={"type": "chat", "id": "conversation-feishu", "label": "聊天"},
        ),
        agent_id="agent-1",
    )["decision"]["id"]

    service.resolve(local_id, {"optionId": "B"}, channel="local")
    value = {"action": "human_decision_submit", "decision_id": feishu_id, "option_id": "B"}
    service.handle_feishu_action(value, {}, {"id": "ou_user"})
    service.handle_feishu_action(value, {}, {"id": "ou_user"})

    assert continuation.queued == [local_id, feishu_id]
    assert continuation.kicks == 2


def test_timeout_resolution_queues_chat_and_periodic_processor_recovers_due_work(tmp_path):
    continuation = ContinuationStub()
    service, _ = workflow(tmp_path, continuation)
    decision_id = service.create(
        request_payload(
            idempotencyKey="chat:timeout",
            source={"type": "chat", "id": "conversation-timeout", "label": "聊天"},
            risk="low",
            nextReminderAt="2026-08-03T08:00:00+00:00",
        ),
        agent_id="agent-1",
    )["decision"]["id"]
    for day in (3, 4, 5, 6):
        service.process_due(f"2026-08-{day:02d}T08:00:00+00:00")

    assert continuation.queued == [decision_id]
    assert continuation.processed == [
        "2026-08-03T08:00:00+00:00",
        "2026-08-04T08:00:00+00:00",
        "2026-08-05T08:00:00+00:00",
        "2026-08-06T08:00:00+00:00",
    ]


def test_terminal_card_update_failure_does_not_lose_chat_continuation(tmp_path):
    continuation = ContinuationStub()
    service, _ = workflow(tmp_path, continuation)
    service.delivery = FailingTerminalDelivery()
    decision_id = service.create(
        request_payload(
            idempotencyKey="chat:card-failure",
            source={"type": "chat", "id": "conversation-card-failure", "label": "聊天"},
        ),
        agent_id="agent-1",
    )["decision"]["id"]

    try:
        service.resolve(decision_id, {"optionId": "B"}, channel="local")
    except RuntimeError:
        pass

    assert continuation.queued == [decision_id]
    assert continuation.kicks == 1
