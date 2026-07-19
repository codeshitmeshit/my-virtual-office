"""Visible HR daily-report conversations and per-Agent failure isolation."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_reporting import (
    HRDailyReportCollector,
    HRReportingService,
    HRReportingValidationError,
    daily_report_request_message,
)
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 2, tzinfo=timezone.utc)
MESSAGE = "请说明你今天完成的工作、产出、阻塞和需要的帮助。"


class FakeConversation:
    def __init__(self, outcomes=None):
        self.outcomes = dict(outcomes or {})
        self.calls = []

    def ask_agent_as_hr(self, request):
        self.calls.append(request)
        outcome = self.outcomes.get(request.target_ai_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def setup(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    for ai_id in ("hr", "agent-1", "agent-2"):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability="available",
            source="test",
        )
    reporting = HRReportingService(
        repository,
        clock=lambda: NOW,
        claim_token_factory=lambda request_id: f"claim:{request_id}",
        claim_lease_seconds=120,
    )
    opened = reporting.open_cycle(
        local_date="2026-07-19",
        timezone_name="Asia/Shanghai",
        scheduled_at=datetime(2026, 7, 19, 10, tzinfo=timezone.utc),
        window_opens_at=datetime(2026, 7, 19, 9, 55, tzinfo=timezone.utc),
        window_closes_at=datetime(2026, 7, 19, 18, tzinfo=timezone.utc),
        eligible_ai_ids=("agent-1", "agent-2"),
    )
    return repository, reporting, opened


def collector(repository, reporting, conversation):
    return HRDailyReportCollector(
        repository,
        reporting,
        conversation,
        clock=lambda: NOW,
        timeout_seconds=12.5,
    )


def test_visible_request_preserves_context_idempotency_and_raw_response(setup):
    repository, reporting, opened = setup
    raw = "  完成了调度器设计。\n产出：方案文档。  "
    conversation = FakeConversation({"agent-1": raw})
    result = collector(repository, reporting, conversation).process_requests(
        (opened.requests[0].id,), message=MESSAGE, worker_id="worker-1"
    )

    assert result[0].status == "submitted"
    sent = conversation.calls[0]
    assert (sent.sender_ai_id, sent.target_ai_id) == ("hr", "agent-1")
    assert sent.message.startswith(MESSAGE)
    assert '"requestType":"vo.hr.daily_report"' in sent.message
    assert '"agentAiId":"agent-1"' in sent.message
    assert '"localDate":"2026-07-19"' in sent.message
    assert '"completedWork":[]' in sent.message
    assert "无法输出合法 JSON" in sent.message
    assert "```" not in sent.message
    assert sent.conversation_key == "hr:daily-report:2026-07-19:agent-1"
    assert sent.idempotency_key == "hr-daily-request:2026-07-19:agent-1"
    assert sent.timeout_seconds == 12.5
    stored = repository.get_daily_report("agent-1", "2026-07-19")
    assert stored.raw_response == raw
    assert stored.submission_state == "submitted"
    assert stored.normalized is None
    assert stored.normalizer_id == ""


def test_timeout_and_failure_are_sanitized_and_isolated(setup):
    repository, reporting, opened = setup
    conversation = FakeConversation(
        {
            "agent-1": TimeoutError("secret provider envelope"),
            "agent-2": "completed second Agent work",
        }
    )
    results = collector(repository, reporting, conversation).process_requests(
        [item.id for item in opened.requests], message=MESSAGE, worker_id="worker"
    )

    assert [item.status for item in results] == ["timeout", "submitted"]
    failed = repository.get_report_request(opened.requests[0].id)
    assert failed.status == "retry"
    assert failed.last_error == "conversation_timeout:TimeoutError"
    assert "secret" not in failed.last_error
    assert repository.get_daily_report("agent-1", "2026-07-19").raw_response is None
    assert repository.get_daily_report("agent-2", "2026-07-19").raw_response == (
        "completed second Agent work"
    )


@pytest.mark.parametrize("response", (None, "", "  \n"))
def test_no_response_does_not_invent_report_content(setup, response):
    repository, reporting, opened = setup
    result = collector(
        repository, reporting, FakeConversation({"agent-1": response})
    ).process_requests((opened.requests[0].id,), message=MESSAGE, worker_id="worker")
    assert result[0].status == "no_response"
    request = repository.get_report_request(opened.requests[0].id)
    report = repository.get_daily_report("agent-1", "2026-07-19")
    assert request.status == "no_response"
    assert report.submission_state == "waiting"
    assert report.raw_response is None
    assert report.normalized is None


def test_completed_request_is_restart_idempotent_and_not_resent(setup):
    repository, reporting, opened = setup
    first = FakeConversation({"agent-1": "done"})
    service = collector(repository, reporting, first)
    service.process_requests((opened.requests[0].id,), message=MESSAGE, worker_id="one")
    second = FakeConversation({"agent-1": "must not replace"})
    result = collector(repository, reporting, second).process_requests(
        (opened.requests[0].id,), message=MESSAGE, worker_id="two"
    )
    assert result[0].status == "already_complete"
    assert second.calls == []
    assert repository.get_daily_report("agent-1", "2026-07-19").raw_response == "done"


def test_invalid_message_fails_before_claim_or_conversation(setup):
    repository, reporting, opened = setup
    conversation = FakeConversation()
    with pytest.raises(HRReportingValidationError, match="message"):
        collector(repository, reporting, conversation).process_requests(
            (opened.requests[0].id,), message=" ", worker_id="worker"
        )
    assert repository.get_report_request(opened.requests[0].id).status == "pending"
    assert conversation.calls == []


def test_collection_module_has_no_server_or_transport_dependency():
    source = (APP_DIR / "services" / "hr_reporting.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source


def test_daily_report_contract_escapes_identity_and_keeps_text_fallback():
    message = daily_report_request_message(
        "日报", ai_id='agent-"quoted', local_date="2026-07-19"
    )
    assert 'agent-\\"quoted' in message
    assert "自然语言回答" in message


def test_structured_agent_json_is_preserved_as_raw_before_hr_normalization(setup):
    repository, reporting, opened = setup
    raw = '{"schemaVersion":1,"agentAiId":"agent-1","localDate":"2026-07-19","completedWork":["done"],"relatedProjectsOrTasks":[],"artifacts":[],"blockers":[],"requestedHelp":[]}'
    result = collector(
        repository, reporting, FakeConversation({"agent-1": raw})
    ).process_requests((opened.requests[0].id,), message=MESSAGE, worker_id="json-worker")
    assert result[0].status == "submitted"
    assert repository.get_daily_report("agent-1", "2026-07-19").raw_response == raw
