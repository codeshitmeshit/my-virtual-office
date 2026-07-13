import threading
import time

import pytest

from app.services.provider_approvals import ProviderApprovalService, TrustedApprovalContext


def context(**values):
    data = {"provider_kind": "hermes", "agent_id": "hermes-default", "profile": "default", "session_id": "session-1", "run_id": "run-1", "conversation_id": "conv-1"}
    data.update(values)
    return TrustedApprovalContext(**data)


def approval(approval_id="approval-1", **values):
    data = {"id": approval_id, "command": "write file", "choices": ["once", "session", "always", "deny"]}
    data.update(values)
    return data


def test_registration_is_idempotent_and_notification_intent_is_single_shot():
    service = ProviderApprovalService()
    first = service.register(context(), approval(), notification_intent={"target": "feishu", "credential": "must-not-store"})
    duplicate = service.register(context(), approval(command="changed"), notification_intent={"target": "other"})
    assert first.created is True
    assert duplicate.created is False
    assert duplicate.record["command"] == "write file"
    assert first.notification_intent == {"target": "feishu"}


def test_queue_is_ordered_and_bounded_per_scope_and_globally():
    service = ProviderApprovalService(max_pending=3, max_per_scope=2)
    for index in range(4):
        service.register(context(session_id=f"session-{index // 2}", run_id=f"run-{index}"), approval(f"approval-{index}"))
    assert service.stats()["pending"] == 3
    pending = service.pending(context(session_id="session-0", run_id=""))
    assert pending["pending_count"] == 1
    assert pending["pending"]["id"] == "approval-1"


def test_cross_run_and_forged_linkage_fail_closed():
    service = ProviderApprovalService()
    service.register(context(), approval())
    assert service.claim(context(run_id="other-run"), "approval-1", "once").claimed is False
    assert service.claim(context(run_id=""), "approval-1", "once").claimed is False
    assert service.claim(context(session_id="", run_id="run-1"), "approval-1", "once").claimed is False
    assert service.claim(context(agent_id="other-agent"), "approval-1", "once").claimed is False
    with pytest.raises(ValueError):
        service.register(context(run_id="other-run"), approval())


def test_supported_decisions_resolve_and_repeated_delivery_replays_outcome():
    for decision in ("once", "session", "always", "deny"):
        service = ProviderApprovalService()
        service.register(context(), approval())
        calls = []
        resolved = service.resolve(context(), "approval-1", decision, lambda record, choice: calls.append(choice) or {"ok": True, "choice": choice})
        replay = service.resolve(context(), "approval-1", decision, lambda record, choice: calls.append("duplicate") or {"ok": False})
        assert resolved.outcome == {"ok": True, "choice": decision}
        assert replay.replay is True
        assert replay.outcome == resolved.outcome
        assert calls == [decision]


def test_concurrent_delivery_runs_provider_continuation_once():
    service = ProviderApprovalService()
    service.register(context(), approval())
    barrier = threading.Barrier(9)
    release = threading.Event()
    calls = []
    results = []

    def continuation(record, choice):
        calls.append(choice)
        release.wait(1)
        return {"ok": True, "choice": choice}

    def resolve():
        barrier.wait()
        results.append(service.resolve(context(), "approval-1", "once", continuation))

    threads = [threading.Thread(target=resolve) for _ in range(8)]
    for thread in threads:
        thread.start()
    barrier.wait()
    deadline = time.time() + 0.5
    while not calls and time.time() < deadline:
        time.sleep(0.005)
    release.set()
    for thread in threads:
        thread.join()
    assert calls == ["once"]
    assert sum(item.claimed for item in results) == 1
    assert sum(item.busy for item in results) == 7


def test_failed_continuation_is_bounded_and_replayed():
    service = ProviderApprovalService()
    service.register(context(), approval())

    def crash(record, choice):
        raise RuntimeError("provider crashed")

    failed = service.resolve(context(), "approval-1", "once", crash)
    replay = service.resolve(context(), "approval-1", "once", crash)
    assert failed.outcome["status"] == "continuation_failed"
    assert failed.outcome["errorCategory"] == "RuntimeError"
    assert replay.replay is True


def test_expired_claim_can_be_retried_with_new_fencing_token():
    now = [1000]
    service = ProviderApprovalService(clock_ms=lambda: now[0], claim_lease_ms=10, token_factory=iter(("one", "two")).__next__)
    service.register(context(), approval())
    first = service.claim(context(), "approval-1", "once")
    now[0] += 11
    second = service.claim(context(), "approval-1", "once")
    stale = service.commit("approval-1", first.decision_token, {"ok": True})
    applied = service.commit("approval-1", second.decision_token, {"ok": True, "choice": "once"})
    assert first.decision_token == "one"
    assert second.decision_token == "two"
    assert stale.claimed is False
    assert applied.claimed is True


def test_sensitive_values_and_paths_are_redacted_before_storage():
    service = ProviderApprovalService()
    registered = service.register(context(), approval(command="use sk-abcdefghijklmnop at /Users/private/file", apiKey="secret"))
    assert "sk-" not in str(registered.record)
    assert "/Users/" not in str(registered.record)
    assert "apiKey" not in registered.record


def test_metadata_update_cannot_relink_or_resolve_pending_record():
    service = ProviderApprovalService()
    service.register(context(), approval())
    updated = service.update("approval-1", {"runId": "forged", "agentId": "other", "status": "resolved", "feishuNotification": {"ok": True}})
    assert updated["runId"] == "run-1"
    assert updated["agentId"] == "hermes-default"
    assert updated["status"] == "pending"
    assert updated["feishuNotification"]["ok"] is True


def test_run_cancellation_fences_pending_decision_and_replays_cancel_outcome():
    service = ProviderApprovalService()
    service.register(context(), approval())
    assert service.cancel_run(context(), {"ok": True, "status": "cancelled", "runId": "run-1"}) == 1
    replay = service.claim(context(), "approval-1", "once")
    assert replay.replay is True
    assert replay.record["decision"] == "deny"
    assert replay.outcome["status"] == "cancelled"
    assert service.pending(context())["pending"] is None


def test_legacy_pending_record_without_native_linkage_remains_resolvable():
    service = ProviderApprovalService()
    legacy_context = context(session_id="", run_id="", conversation_id="")
    registered = service.register(legacy_context, {"id": "legacy-approval", "provider": "hermes", "message": "retry me"})
    assert registered.record["status"] == "pending"
    resolved = service.resolve(legacy_context, "legacy-approval", "deny", lambda record, choice: {"ok": True, "choice": choice})
    assert resolved.outcome == {"ok": True, "choice": "deny"}
