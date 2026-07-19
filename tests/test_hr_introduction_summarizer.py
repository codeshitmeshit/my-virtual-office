"""Structured HR introduction validation, provenance, and conflict replacement."""

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import HRIntroductionSummarizer
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)


class FakeHR:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def ask_hr(self, prompt, conversation_key, timeout_seconds):
        self.calls.append((prompt, conversation_key, timeout_seconds))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if callable(self.outcome):
            return self.outcome()
        return self.outcome


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: NOW)
    result.initialize()
    result.upsert_agent(
        ai_id="agent-1",
        name="Researcher",
        agent_kind="project",
        status="active",
        availability="available",
        source="test",
    )
    return result


def response_received(repository, raw="I investigate production incidents and write reliability reports."):
    return repository.save_introduction(
        ai_id="agent-1",
        state="response_received",
        raw_response=raw,
        introduction="",
        source="agent-response",
        actor_id="hr",
        expected_version=0,
    )


def output(
    raw,
    introduction="Investigates production incidents and reports reliability findings.",
    **overrides,
):
    value = {
        "schemaVersion": 1,
        "introduction": introduction,
        "supportingEvidence": [raw],
        "materialConflict": False,
        "clarificationQuestion": "",
    }
    value.update(overrides)
    return json.dumps(value, ensure_ascii=False)


def test_valid_structured_summary_publishes_version_with_provenance(repository):
    raw = "I investigate production incidents and write reliability reports."
    current = response_received(repository, raw)
    hr = FakeHR(output(raw))
    result = HRIntroductionSummarizer(repository, hr, timeout_seconds=15).summarize(
        "agent-1",
        expected_version=current.version,
    )
    assert result.status == "published"
    assert result.version == 2
    assert result.conversation_key.startswith("hr:introduction-summary:agent-1:v1:")
    assert hr.calls[0][1] == result.conversation_key
    assert hr.calls[0][2] == 15
    published = repository.get_current_introduction("agent-1")
    assert published.state == "published"
    assert published.raw_response == raw
    assert published.introduction == "Investigates production incidents and reports reliability findings."
    assert published.source == "hr-structured-summary"
    assert published.actor_id == "hr"
    history = repository.list_introductions("agent-1").items
    assert [item.version for item in history] == [2, 1]


@pytest.mark.parametrize(
    "payload",
    (
        None,
        "",
        "{broken",
        json.dumps({"schemaVersion": 1}),
        json.dumps(
            {
                "schemaVersion": 2,
                "introduction": "summary",
                "supportingEvidence": ["raw"],
                "materialConflict": False,
                "clarificationQuestion": "",
            }
        ),
        json.dumps(
            {
                "schemaVersion": 1,
                "introduction": "unsupported summary",
                "supportingEvidence": ["not present in the response"],
                "materialConflict": False,
                "clarificationQuestion": "",
            }
        ),
    ),
)
def test_malformed_or_unsupported_hr_output_does_not_mutate_current(repository, payload):
    current = response_received(repository, "raw response")
    result = HRIntroductionSummarizer(repository, FakeHR(payload)).summarize(
        "agent-1",
        expected_version=current.version,
    )
    assert result.status == "failed"
    assert result.error_code == "hr_introduction_summary_invalid"
    assert repository.get_current_introduction("agent-1") == current
    assert len(repository.list_introductions("agent-1").items) == 1


def test_missing_agent_response_does_not_invoke_hr(repository):
    hr = FakeHR("must not be used")
    missing = HRIntroductionSummarizer(repository, hr).summarize(
        "agent-1",
        expected_version=0,
    )
    assert missing.status == "missing_response"
    assert hr.calls == []

    pending = repository.save_introduction(
        ai_id="agent-1",
        state="introduction_pending",
        raw_response=None,
        introduction="",
        source="request",
        actor_id="hr",
        expected_version=0,
    )
    missing = HRIntroductionSummarizer(repository, hr).summarize(
        "agent-1",
        expected_version=pending.version,
    )
    assert missing.status == "missing_response"
    assert hr.calls == []


def test_stale_role_conflict_preserves_previous_introduction_until_clarified(repository):
    first_raw = "I investigate production incidents."
    response_received(repository, first_raw)
    first = HRIntroductionSummarizer(repository, FakeHR(output(first_raw))).summarize(
        "agent-1", expected_version=1
    )
    published = repository.get_current_introduction("agent-1")
    assert first.status == "published"

    changed_raw = "I now design user interfaces."
    conflict_output = output(
        changed_raw,
        introduction="",
        materialConflict=True,
        clarificationQuestion="Has your primary responsibility changed from reliability to UI design?",
    )
    conflict = HRIntroductionSummarizer(repository, FakeHR(conflict_output)).summarize(
        "agent-1",
        expected_version=published.version,
        raw_response=changed_raw,
    )
    assert conflict.status == "clarification_pending"
    pending = repository.get_current_introduction("agent-1")
    assert pending.version == 3
    assert pending.introduction == published.introduction
    assert pending.raw_response == changed_raw
    assert pending.clarification_question.startswith("Has your primary")

    clarified_raw = "Yes. I now primarily design user interfaces and no longer own reliability."
    replacement_output = output(
        clarified_raw,
        introduction="Designs user interfaces.",
    )
    replacement = HRIntroductionSummarizer(repository, FakeHR(replacement_output)).summarize(
        "agent-1",
        expected_version=pending.version,
        raw_response=clarified_raw,
    )
    assert replacement.status == "published"
    final = repository.get_current_introduction("agent-1")
    assert final.version == 4
    assert final.introduction == "Designs user interfaces."
    assert final.raw_response == clarified_raw
    assert len(repository.list_introductions("agent-1").items) == 4


def test_clarification_pending_without_new_answer_does_not_reask_hr(repository):
    repository.save_introduction(
        ai_id="agent-1",
        state="clarification_pending",
        raw_response="I may have changed roles.",
        introduction="Existing introduction.",
        source="hr-structured-summary",
        actor_id="hr",
        clarification_question="Did your role change?",
        expected_version=0,
    )
    hr = FakeHR("must not be used")
    result = HRIntroductionSummarizer(repository, hr).summarize(
        "agent-1", expected_version=1
    )
    assert result.status == "awaiting_clarification"
    assert hr.calls == []


def test_published_same_response_is_idempotent(repository):
    raw = "I investigate production incidents."
    repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response=raw,
        introduction="Investigates incidents.",
        source="hr-structured-summary",
        actor_id="hr",
        expected_version=0,
    )
    hr = FakeHR("must not be used")
    result = HRIntroductionSummarizer(repository, hr).summarize(
        "agent-1", expected_version=1, raw_response=raw
    )
    assert result.status == "already_published"
    assert hr.calls == []
    assert len(repository.list_introductions("agent-1").items) == 1


def test_version_conflict_fails_before_hr_invocation(repository):
    response_received(repository)
    hr = FakeHR("must not be used")
    result = HRIntroductionSummarizer(repository, hr).summarize(
        "agent-1", expected_version=99
    )
    assert result.status == "failed"
    assert result.error_code == "hr_introduction_version_conflict"
    assert hr.calls == []


def test_concurrent_summary_replacement_has_one_current_winner(repository):
    raw = "I investigate production incidents."
    response_received(repository, raw)
    barrier = threading.Barrier(3)

    def delayed_output():
        barrier.wait()
        return output(raw)

    results = []

    def summarize(label):
        results.append(
            HRIntroductionSummarizer(repository, FakeHR(delayed_output)).summarize(
                "agent-1", expected_version=1
            )
        )

    threads = [threading.Thread(target=summarize, args=(label,)) for label in ("a", "b")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert sorted(item.status for item in results) == ["failed", "published"]
    assert len(repository.list_introductions("agent-1").items) == 2
    assert repository.get_current_introduction("agent-1").version == 2


def test_hr_exception_is_sanitized_and_previous_record_remains(repository):
    current = response_received(repository)
    result = HRIntroductionSummarizer(
        repository,
        FakeHR(RuntimeError("secret provider envelope")),
    ).summarize("agent-1", expected_version=1)
    assert result.status == "failed"
    assert result.error_code == "hr_introduction_summary_invalid"
    assert "secret" not in result.error_code
    assert repository.get_current_introduction("agent-1") == current
