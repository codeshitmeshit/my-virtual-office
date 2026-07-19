"""Durable introduction claims and injected HR conversation orchestration."""

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import HRIntroductionWorkflow
from services.hr_repository import HRRepository, HRRepositoryConflictError


NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)
MESSAGE = "请介绍你的身份、职责和当前主要工作范围。"


class FakeConversation:
    def __init__(self, outcomes=None):
        self.outcomes = dict(outcomes or {})
        self.calls = []

    def ask_agent_as_hr(self, target_ai_id, message, conversation_key, timeout_seconds):
        self.calls.append((target_ai_id, message, conversation_key, timeout_seconds))
        outcome = self.outcomes.get(target_ai_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: NOW)
    result.initialize()
    for ai_id in ("hr", "agent-1", "agent-2"):
        result.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability="available",
            source="test",
        )
    return result


def workflow(repository, conversation, token_prefix="claim"):
    return HRIntroductionWorkflow(
        repository,
        conversation,
        clock=lambda: NOW,
        claim_token_factory=lambda ai_id: f"{token_prefix}-{ai_id}",
        timeout_seconds=12.5,
        claim_lease_seconds=60,
    )


def test_response_is_preserved_raw_with_deterministic_conversation_key(repository):
    raw = "  我负责可靠性研究。\n当前排查生产故障。  "
    conversation = FakeConversation({"agent-1": raw})
    result = workflow(repository, conversation).process(("agent-1",), message=MESSAGE)

    assert result[0].status == "response_received"
    assert result[0].conversation_key == "hr:introduction-conversation:agent-1:initial"
    assert conversation.calls == [
        (
            "agent-1",
            MESSAGE,
            "hr:introduction-conversation:agent-1:initial",
            12.5,
        )
    ]
    stored = repository.get_current_introduction("agent-1")
    assert stored.state == "response_received"
    assert stored.raw_response == raw
    assert stored.introduction == ""
    assert stored.request_occurrence_key == "hr:introduction-request:agent-1:initial"
    assert stored.attempt_count == 1
    assert stored.claim_token == ""


@pytest.mark.parametrize("response", (None, "", "   \n"))
def test_no_response_is_neutral_and_does_not_invent_introduction(repository, response):
    conversation = FakeConversation({"agent-1": response})
    result = workflow(repository, conversation).process(("agent-1",), message=MESSAGE)
    stored = repository.get_current_introduction("agent-1")
    assert result[0].status == "no_response"
    assert stored.state == "introduction_pending"
    assert stored.raw_response is None
    assert stored.introduction == ""
    assert stored.last_error == ""
    assert stored.responded_at is None


def test_conversation_failure_is_sanitized_and_isolated_per_agent(repository):
    secret_error = RuntimeError("provider envelope contains secret-token")
    conversation = FakeConversation(
        {"agent-1": secret_error, "agent-2": "I build the platform."}
    )
    results = workflow(repository, conversation).process(
        ("agent-1", "agent-2"),
        message=MESSAGE,
    )
    assert [item.status for item in results] == ["failed", "response_received"]
    failed = repository.get_current_introduction("agent-1")
    succeeded = repository.get_current_introduction("agent-2")
    assert failed.state == "failed"
    assert failed.last_error == "conversation_failed:RuntimeError"
    assert "secret-token" not in failed.last_error
    assert succeeded.raw_response == "I build the platform."


def test_retry_after_no_response_reuses_keys_and_increments_attempt(repository):
    first_conversation = FakeConversation({"agent-1": None})
    first = workflow(repository, first_conversation, "first").process(
        ("agent-1",), message=MESSAGE
    )
    second_conversation = FakeConversation({"agent-1": "Now I can answer."})
    second = workflow(repository, second_conversation, "second").process(
        ("agent-1",), message=MESSAGE
    )
    assert first[0].attempt_count == 1
    assert second[0].attempt_count == 2
    assert first[0].conversation_key == second[0].conversation_key
    assert repository.get_current_introduction("agent-1").raw_response == "Now I can answer."


def test_completed_response_is_restart_idempotent(repository):
    first_conversation = FakeConversation({"agent-1": "I own testing."})
    workflow(repository, first_conversation).process(("agent-1",), message=MESSAGE)

    restarted = HRRepository(repository.status_dir, clock=lambda: NOW)
    restarted.initialize()
    second_conversation = FakeConversation({"agent-1": "must not be called"})
    result = workflow(restarted, second_conversation, "restart").process(
        ("agent-1",), message=MESSAGE
    )
    assert result[0].status == "already_complete"
    assert second_conversation.calls == []
    assert restarted.get_current_introduction("agent-1").raw_response == "I own testing."


def test_existing_published_introduction_is_not_mutated_by_request_ensure(repository):
    published = repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response="I own testing.",
        introduction="Owns testing.",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    conversation = FakeConversation({"agent-1": "must not be called"})
    result = workflow(repository, conversation).process(("agent-1",), message=MESSAGE)
    assert result[0].status == "already_complete"
    assert conversation.calls == []
    assert repository.get_current_introduction("agent-1") == published


def test_hr_is_skipped_without_request_or_conversation(repository):
    conversation = FakeConversation({"hr": "self description"})
    result = workflow(repository, conversation).process(("hr",), message=MESSAGE)
    assert result[0].status == "skipped_hr"
    assert conversation.calls == []
    assert repository.get_current_introduction("hr") is None


def test_introduction_claim_fencing_rejects_stale_worker(repository):
    repository.ensure_introduction_request(
        ai_id="agent-1",
        occurrence_key="intro:agent-1",
        conversation_key="conversation:agent-1",
        actor_id="hr",
    )
    first = repository.claim_introduction_request(
        ai_id="agent-1",
        claimed_by="hr",
        claim_token="token-a",
        now="2026-07-19T09:00:00Z",
        claim_expires_at="2026-07-19T09:01:00Z",
    )
    assert first is not None
    assert repository.claim_introduction_request(
        ai_id="agent-1",
        claimed_by="hr",
        claim_token="token-b",
        now="2026-07-19T09:00:30Z",
        claim_expires_at="2026-07-19T09:01:30Z",
    ) is None
    second = repository.claim_introduction_request(
        ai_id="agent-1",
        claimed_by="hr",
        claim_token="token-b",
        now="2026-07-19T09:01:00Z",
        claim_expires_at="2026-07-19T09:02:00Z",
    )
    assert second is not None
    with pytest.raises(HRRepositoryConflictError, match="stale"):
        repository.finish_introduction_request(
            ai_id="agent-1",
            claim_token="token-a",
            finished_at="2026-07-19T09:01:10Z",
            raw_response="stale response",
        )
    repository.finish_introduction_request(
        ai_id="agent-1",
        claim_token="token-b",
        finished_at="2026-07-19T09:01:10Z",
        raw_response="winning response",
    )
    assert repository.get_current_introduction("agent-1").raw_response == "winning response"


def test_concurrent_workflows_make_one_effective_conversation(repository):
    entered = threading.Event()
    release = threading.Event()

    class BlockingConversation(FakeConversation):
        def ask_agent_as_hr(self, *args):
            self.calls.append(args)
            entered.set()
            assert release.wait(timeout=5)
            return "single response"

    conversation = BlockingConversation()
    first_workflow = workflow(repository, conversation, "first")
    second_workflow = workflow(repository, conversation, "second")
    first_results = []

    thread = threading.Thread(
        target=lambda: first_results.extend(
            first_workflow.process(("agent-1",), message=MESSAGE)
        )
    )
    thread.start()
    assert entered.wait(timeout=5)
    second_result = second_workflow.process(("agent-1",), message=MESSAGE)
    release.set()
    thread.join(timeout=5)

    assert second_result[0].status == "claimed_elsewhere"
    assert first_results[0].status == "response_received"
    assert len(conversation.calls) == 1


def test_workflow_validation_does_not_create_requests(repository):
    conversation = FakeConversation()
    with pytest.raises(ValueError, match="message"):
        workflow(repository, conversation).process(("agent-1",), message="  ")
    assert repository.get_current_introduction("agent-1") is None


def test_claim_lease_must_cover_conversation_timeout(repository):
    with pytest.raises(ValueError, match="longer"):
        HRIntroductionWorkflow(
            repository,
            FakeConversation(),
            claim_token_factory=lambda ai_id: f"token-{ai_id}",
            timeout_seconds=30,
            claim_lease_seconds=30,
        )


def test_cleanup_clock_failure_does_not_block_next_agent(repository):
    class FlakyClock:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("clock failure")
            return NOW

    conversation = FakeConversation(
        {"agent-1": RuntimeError("provider failed"), "agent-2": "second succeeds"}
    )
    service = HRIntroductionWorkflow(
        repository,
        conversation,
        clock=FlakyClock(),
        claim_token_factory=lambda ai_id: f"token-{ai_id}",
        timeout_seconds=10,
        claim_lease_seconds=60,
    )
    results = service.process(("agent-1", "agent-2"), message=MESSAGE)
    assert [item.status for item in results] == ["failed", "response_received"]
