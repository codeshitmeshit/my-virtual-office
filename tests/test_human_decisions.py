from __future__ import annotations

import json

import pytest

from app.services.human_decisions import HumanDecisionError, HumanDecisionStore


def request_payload(**overrides):
    payload = {
        "idempotencyKey": "task:release:gate-1",
        "source": {"type": "task", "id": "task-release", "label": "发布任务"},
        "title": "选择上线节奏",
        "situation": "自测完成，需要决定上线范围。",
        "reason": "风险偏好只能由用户决定。",
        "risk": "medium",
        "urgency": "urgent",
        "deadlineAt": "2026-08-04T10:00:00+08:00",
        "timeoutConsequence": "三次提醒后采用推荐方案。",
        "options": [
            {"id": "A", "label": "全量", "impact": "最快但风险最高"},
            {"id": "B", "label": "灰度", "impact": "先验证再扩大"},
            {"id": "C", "label": "内部", "impact": "风险最低"},
            {"id": "D", "label": "暂缓", "impact": "继续等待"},
        ],
        "recommendation": {"optionId": "B", "reason": "兼顾速度和回滚能力。"},
        "taskDetail": {"summary": "发布控制面板", "nextStep": "创建发布批次"},
    }
    payload.update(overrides)
    return payload


def test_create_is_durable_and_idempotent(tmp_path):
    path = tmp_path / "human-decisions.json"
    store = HumanDecisionStore(path)

    first = store.create(request_payload())
    second = store.create(request_payload())

    assert first["created"] is True
    assert second["created"] is False
    assert second["decision"]["id"] == first["decision"]["id"]
    assert store.snapshot()["revision"] == 1
    assert HumanDecisionStore(path).snapshot()["decisions"][0]["source"]["type"] == "task"
    assert json.loads(path.read_text())["revision"] == 1


@pytest.mark.parametrize("source_type", ["task", "meeting", "chat"])
def test_all_supported_sources_are_projected(source_type, tmp_path):
    store = HumanDecisionStore(tmp_path / f"{source_type}.json")
    created = store.create(request_payload(
        idempotencyKey=f"{source_type}:1",
        source={"type": source_type, "id": "source-1", "label": "来源"},
    ))
    assert created["decision"]["source"]["type"] == source_type


def test_custom_answer_wins_and_competing_resolution_conflicts(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload())["decision"]["id"]

    resolved = store.resolve(
        decision_id,
        option_id="A",
        custom_answer="  请先灰度给设计团队  ",
        channel="feishu",
        actor={"id": "ou_user"},
    )
    assert resolved["decision"]["resolution"] == {
        "answer": "请先灰度给设计团队",
        "optionId": None,
        "channel": "feishu",
        "resolvedAt": resolved["decision"]["resolution"]["resolvedAt"],
        "nextAction": "创建发布批次",
        "actor": {"id": "ou_user"},
    }
    assert store.resolve(
        decision_id,
        option_id="A",
        custom_answer="请先灰度给设计团队",
        channel="feishu",
        actor={"id": "ou_user"},
    )["idempotent"] is True
    with pytest.raises(HumanDecisionError) as exc:
        store.resolve(decision_id, option_id="B", channel="local")
    assert exc.value.status == 409
    assert exc.value.code == "decision_conflict"


def test_resolve_validates_answer_and_reopen_respects_execution_lock(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload())["decision"]["id"]
    with pytest.raises(HumanDecisionError) as exc:
        store.resolve(decision_id, option_id="Z", channel="local")
    assert exc.value.code == "invalid_option"

    store.resolve(decision_id, option_id="B", channel="local")
    assert store.reopen(decision_id)["decision"]["status"] == "pending"
    store.resolve(decision_id, option_id="B", channel="local")
    store.mark_execution_started(decision_id, impact="发布批次已创建")
    with pytest.raises(HumanDecisionError) as exc:
        store.reopen(decision_id)
    assert exc.value.status == 409
    assert exc.value.code == "execution_started"


def test_delivery_metadata_is_not_exposed_in_safe_snapshot(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload())["decision"]["id"]
    store.record_delivery(decision_id, application="notification", result={
        "ok": True, "status": "sent", "messageId": "om_secret", "appFingerprint": "private",
    })

    projected = store.snapshot()["decisions"][0]
    assert projected["sync"]["feishuStatus"] == "sent"
    assert projected["sync"]["application"] == "notification"
    assert "messageId" not in projected["sync"]
    assert "deliveries" not in projected
    assert store.delivery_records(decision_id)[0]["messageId"] == "om_secret"


def test_invalid_shape_is_rejected(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    with pytest.raises(HumanDecisionError) as exc:
        store.create(request_payload(options=request_payload()["options"][:3]))
    assert exc.value.status == 400
    assert exc.value.code == "invalid_options"


def test_three_due_reminders_auto_resolve_low_risk_with_recommendation(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        risk="low",
        nextReminderAt="2026-08-03T08:00:00+00:00",
    ))["decision"]["id"]

    assert store.process_due("2026-08-03T08:00:00+00:00")[0]["kind"] == "reminder"
    assert store.process_due("2026-08-04T08:00:00+00:00")[0]["kind"] == "reminder"
    third = store.process_due("2026-08-05T08:00:00+00:00")[0]
    assert third["kind"] == "reminder"
    assert third["decision"]["reminder"]["count"] == 3
    assert store.snapshot()["decisions"][0]["status"] == "pending"
    final = store.process_due("2026-08-06T08:00:00+00:00")[0]

    assert final["kind"] == "timeout_resolved"
    decision = store.snapshot()["decisions"][0]
    assert decision["status"] == "resolved"
    assert decision["resolution"]["optionId"] == "B"
    assert decision["resolution"]["channel"] == "timeout"
    assert decision["reminder"]["count"] == 3


def test_three_due_reminders_keep_high_risk_branch_waiting(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    store.create(request_payload(
        risk="high",
        nextReminderAt="2026-08-03T08:00:00+00:00",
    ))
    for day in (3, 4, 5):
        store.process_due(f"2026-08-{day:02d}T08:00:00+00:00")
    final = store.process_due("2026-08-06T08:00:00+00:00")[0]
    decision = store.snapshot()["decisions"][0]
    assert final["kind"] == "timeout_waiting"
    assert decision["status"] == "pending"
    assert decision["nearTimeout"] is True
    assert decision["reminder"] == {"count": 3, "limit": 3, "nextAt": ""}


def test_chat_continuation_binding_is_private_and_projects_safe_summary(tmp_path):
    path = tmp_path / "state.json"
    store = HumanDecisionStore(path)
    decision_id = store.create(request_payload(
        idempotencyKey="chat:1",
        source={"type": "chat", "id": "conversation-1", "label": "聊天"},
    ))["decision"]["id"]

    bound = store.bind_chat_continuation(
        decision_id,
        agent_id="agent-secret",
        conversation_id="conversation-1",
    )

    assert bound["continuation"] == {
        "status": "waiting",
        "attempts": 0,
        "updatedAt": bound["continuation"]["updatedAt"],
        "errorCategory": "",
    }
    projected = store.snapshot()["decisions"][0]
    assert "_continuation" not in projected
    assert "agent-secret" not in json.dumps(projected)
    persisted = json.loads(path.read_text())["decisions"][0]["_continuation"]
    assert persisted["agentId"] == "agent-secret"
    assert persisted["conversationId"] == "conversation-1"
    assert persisted["status"] == "waiting"


def test_task_continuation_preserves_project_source_and_claims_private_binding(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        idempotencyKey="task:project-1:task-1:decision",
        source={
            "type": "task",
            "id": "task-1",
            "projectId": "project-1",
            "label": "Task 1",
        },
    ))["decision"]["id"]

    store.bind_continuation(
        decision_id,
        kind="task",
        agent_id="agent-1",
        binding={
            "projectId": "project-1",
            "taskId": "task-1",
            "attemptId": "attempt-1",
            "runId": "run-1",
            "mode": "stage",
        },
    )
    store.resolve(decision_id, option_id="A", channel="local")
    store.queue_continuation(decision_id)
    claim = store.claim_due_continuations(
        now="2026-08-03T08:00:00+00:00",
        limit=1,
    )[0]

    assert claim.kind == "task"
    assert claim.agent_id == "agent-1"
    assert claim.binding == {
        "projectId": "project-1",
        "taskId": "task-1",
        "attemptId": "attempt-1",
        "runId": "run-1",
        "mode": "stage",
    }
    projected = store.snapshot()["decisions"][0]
    assert projected["source"]["projectId"] == "project-1"
    assert "binding" not in projected["continuation"]


def test_meeting_continuation_binding_must_match_source(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        idempotencyKey="meeting:1",
        source={"type": "meeting", "id": "meeting-1", "label": "Meeting"},
    ))["decision"]["id"]

    with pytest.raises(HumanDecisionError) as exc:
        store.bind_continuation(
            decision_id,
            kind="meeting",
            agent_id="agent-1",
            binding={"meetingId": "meeting-2"},
        )

    assert exc.value.code == "continuation_binding_invalid"


def test_chat_continuation_claim_is_atomic_and_survives_restart(tmp_path):
    path = tmp_path / "state.json"
    store = HumanDecisionStore(path)
    decision_id = store.create(request_payload(
        idempotencyKey="chat:claim",
        source={"type": "chat", "id": "conversation-1", "label": "聊天"},
    ))["decision"]["id"]
    store.bind_chat_continuation(decision_id, agent_id="agent-1", conversation_id="conversation-1")
    store.resolve(decision_id, option_id="B", channel="local")
    assert store.queue_chat_continuation(decision_id)["queued"] is True

    restarted = HumanDecisionStore(path)
    first = restarted.claim_due_chat_continuations(
        now="2026-08-03T08:00:00+00:00",
        limit=10,
        lease_seconds=30,
    )
    second = restarted.claim_due_chat_continuations(
        now="2026-08-03T08:00:01+00:00",
        limit=10,
        lease_seconds=30,
    )

    assert [claim.decision_id for claim in first] == [decision_id]
    assert first[0].agent_id == "agent-1"
    assert first[0].conversation_id == "conversation-1"
    assert first[0].decision["resolution"]["answer"] == "灰度"
    assert second == []


def test_expired_running_continuation_becomes_uncertain_without_redispatch(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        idempotencyKey="chat:lease",
        source={"type": "chat", "id": "conversation-1", "label": "聊天"},
    ))["decision"]["id"]
    store.bind_chat_continuation(decision_id, agent_id="agent-1", conversation_id="conversation-1")
    store.resolve(decision_id, option_id="B", channel="local")
    store.queue_chat_continuation(decision_id)
    store.claim_due_chat_continuations(
        now="2026-08-03T08:00:00+00:00",
        limit=1,
        lease_seconds=30,
    )

    claims = store.claim_due_chat_continuations(
        now="2026-08-03T08:00:31+00:00",
        limit=1,
        lease_seconds=30,
    )

    assert claims == []
    summary = store.snapshot()["decisions"][0]["continuation"]
    assert summary["status"] == "uncertain"
    assert summary["errorCategory"] == "lease_expired"


def test_claim_token_fences_completion_and_retry_transitions(tmp_path):
    store = HumanDecisionStore(tmp_path / "state.json")
    decision_id = store.create(request_payload(
        idempotencyKey="chat:transitions",
        source={"type": "chat", "id": "conversation-1", "label": "聊天"},
    ))["decision"]["id"]
    store.bind_chat_continuation(decision_id, agent_id="agent-1", conversation_id="conversation-1")
    store.resolve(decision_id, option_id="B", channel="local")
    store.queue_chat_continuation(decision_id)
    first = store.claim_due_chat_continuations(
        now="2026-08-03T08:00:00+00:00",
        limit=1,
    )[0]

    assert store.retry_chat_continuation(
        decision_id,
        claim_token="wrong-token",
        error_category="busy",
        next_attempt_at="2026-08-03T08:01:00+00:00",
    )["updated"] is False
    assert store.retry_chat_continuation(
        decision_id,
        claim_token=first.claim_token,
        error_category="busy",
        next_attempt_at="2026-08-03T08:01:00+00:00",
    )["updated"] is True
    assert store.claim_due_chat_continuations(
        now="2026-08-03T08:00:59+00:00",
        limit=1,
    ) == []
    second = store.claim_due_chat_continuations(
        now="2026-08-03T08:01:00+00:00",
        limit=1,
    )[0]
    assert second.attempts == 2
    assert store.complete_chat_continuation(
        decision_id,
        claim_token=second.claim_token,
    )["updated"] is True
    assert store.snapshot()["decisions"][0]["continuation"]["status"] == "completed"
    assert store.claim_due_chat_continuations(
        now="2026-08-03T09:00:00+00:00",
        limit=1,
    ) == []


def test_running_continuation_can_be_fenced_as_failed_or_uncertain(tmp_path):
    for terminal_method, expected in (
        ("fail_chat_continuation", "failed"),
        ("mark_chat_continuation_uncertain", "uncertain"),
    ):
        store = HumanDecisionStore(tmp_path / f"{expected}.json")
        decision_id = store.create(request_payload(
            idempotencyKey=f"chat:{expected}",
            source={"type": "chat", "id": f"conversation-{expected}", "label": "聊天"},
        ))["decision"]["id"]
        store.bind_chat_continuation(
            decision_id,
            agent_id="agent-1",
            conversation_id=f"conversation-{expected}",
        )
        store.resolve(decision_id, option_id="B", channel="local")
        store.queue_chat_continuation(decision_id)
        claim = store.claim_due_chat_continuations(limit=1)[0]

        result = getattr(store, terminal_method)(
            decision_id,
            claim_token=claim.claim_token,
            error_category="provider_unknown",
        )

        assert result["updated"] is True
        summary = store.snapshot()["decisions"][0]["continuation"]
        assert summary["status"] == expected
        assert summary["errorCategory"] == "provider_unknown"


def test_resolved_waiting_continuation_recovers_after_crash_before_queue(tmp_path):
    path = tmp_path / "state.json"
    store = HumanDecisionStore(path)
    decision_id = store.create(request_payload(
        idempotencyKey="chat:crash-before-queue",
        source={"type": "chat", "id": "conversation-crash", "label": "聊天"},
    ))["decision"]["id"]
    store.bind_chat_continuation(
        decision_id,
        agent_id="agent-1",
        conversation_id="conversation-crash",
    )
    store.resolve(decision_id, option_id="B", channel="local")

    claims = HumanDecisionStore(path).claim_due_chat_continuations(
        now="2026-08-03T08:00:00+00:00",
        limit=1,
    )

    assert [claim.decision_id for claim in claims] == [decision_id]
    assert claims[0].attempts == 1
