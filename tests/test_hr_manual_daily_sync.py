import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_assessments import HRAssessmentOrchestrator
from services.hr_evidence import HREvidenceCollector, HREvidencePorts
from services.hr_manual_daily_sync import (
    CallableHRManualDailyConversation,
    EmptyHREvidencePort,
    HRManualDailySyncCommands,
    HRManualDailySyncService,
    HRManualDailySyncValidationError,
)
from services.hr_reporting import HRDailyReportNormalizer, HRReportingService
from services.hr_repository import HRRepository
from services.hr_command_status import HRCommandStatusTracker


NOW = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)


class FakeConversation:
    def __init__(self):
        self.responses = {"agent-1": "first corrected report", "agent-2": None}
        self.agent_calls = []

    def ask_agent(self, ai_id, message, _key, _timeout):
        self.agent_calls.append((ai_id, message))
        return self.responses[ai_id]

    def ask_hr(self, prompt, _key, _timeout):
        if "Normalize the Agent's daily report" in prompt:
            ai_id = prompt.split("Agent AI ID: ", 1)[1].splitlines()[0]
            submission = json.loads(prompt.split("submission: ", 1)[1].splitlines()[0])
            return json.dumps({
                "schemaVersion": 1, "localDate": "2026-07-20", "agentAiId": ai_id,
                "completedWork": ["corrected work"], "relatedProjectsOrTasks": [],
                "artifacts": [], "blockers": [], "requestedHelp": [],
                "submission": submission,
            })
        ai_id = prompt.split("Agent AI ID: ", 1)[1].splitlines()[0]
        return json.dumps({
            "schemaVersion": 1, "agentAiId": ai_id, "localDate": "2026-07-20",
            "principalContributions": [], "workload": "insufficient_information",
            "rationale": "Only the refreshed self-report is available.",
            "evidenceReferences": [], "blockers": [], "strengths": [],
            "improvements": ["Add independently verifiable delivery evidence."],
            "runtimeDiagnosis": "No runtime evidence is available.",
            "informationSufficiency": {"status": "insufficient", "explanation": "One source only."},
            "hrAiId": "hr", "assessedAt": NOW.isoformat(),
        })


def build(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    for ai_id, availability in (("hr", "available"), ("agent-1", "available"), ("agent-2", "available"), ("agent-3", "offline")):
        repository.upsert_agent(
            ai_id=ai_id, name=ai_id.upper(), agent_kind="system" if ai_id == "hr" else "project",
            status="active", availability=availability, source="test",
        )
    fake = FakeConversation()
    conversation = CallableHRManualDailyConversation(fake.ask_agent, fake.ask_hr)
    reporting = HRReportingService(
        repository, clock=lambda: NOW, claim_token_factory=lambda request_id: f"claim:{request_id}"
    )
    normalizer = HRDailyReportNormalizer(repository, conversation, clock=lambda: NOW)
    empty = EmptyHREvidencePort()
    evidence = HREvidenceCollector(HREvidencePorts(empty, empty, empty, empty, empty, empty))
    assessments = HRAssessmentOrchestrator(
        repository, evidence, conversation, clock=lambda: NOW,
        claim_token_factory=lambda job_id: f"claim:{job_id}", claim_lease_seconds=90,
    )
    service = HRManualDailySyncService(
        repository, reporting, normalizer, assessments, conversation,
        timezone_name="UTC", submission_window_minutes=120, max_workers=2,
        timeout_seconds=30, clock=lambda: NOW,
    )
    return repository, fake, service


def test_manual_sync_replaces_report_and_versions_assessment(tmp_path):
    repository, fake, service = build(tmp_path)
    first = service.synchronize(("agent-1",), command_id="command-1")
    assert first.updated == 1
    assert first.assessed == 1
    assert '"requestType":"vo.hr.daily_report"' in fake.agent_calls[0][1]
    assert '"agentAiId":"agent-1"' in fake.agent_calls[0][1]
    report = repository.get_daily_report("agent-1", "2026-07-20")
    assessment = repository.get_current_assessment("agent-1", "2026-07-20")
    assert report.raw_response == "first corrected report"
    assert report.normalized["completedWork"] == ["corrected work"]
    assert assessment.version == 1

    fake.responses["agent-1"] = "second corrected report"
    second = service.synchronize(("agent-1",), command_id="command-2")
    updated_report = repository.get_daily_report("agent-1", "2026-07-20")
    updated_assessment = repository.get_current_assessment("agent-1", "2026-07-20")
    assert second.assessed == 1
    assert updated_report.raw_response == "second corrected report"
    assert updated_report.revision > report.revision
    assert updated_assessment.version == 2
    assert updated_assessment.revision_reason == "manual_daily_sync"


def test_no_response_preserves_existing_report_and_assessment(tmp_path):
    repository, fake, service = build(tmp_path)
    service.synchronize(("agent-1",), command_id="command-1")
    before_report = repository.get_daily_report("agent-1", "2026-07-20")
    before_assessment = repository.get_current_assessment("agent-1", "2026-07-20")
    fake.responses["agent-1"] = None
    result = service.synchronize(("agent-1",), command_id="command-2")
    assert result.no_response == 1
    assert repository.get_daily_report("agent-1", "2026-07-20") == before_report
    assert repository.get_current_assessment("agent-1", "2026-07-20") == before_assessment


def test_selection_rejects_empty_duplicate_hr_and_unavailable(tmp_path):
    _repository, _fake, service = build(tmp_path)
    for selection in ((), ("agent-1", "agent-1"), ("hr",), ("agent-3",), ("missing",)):
        with pytest.raises(HRManualDailySyncValidationError):
            service.synchronize(selection, command_id="bad")


def test_only_selected_agents_are_contacted(tmp_path):
    repository, _fake, service = build(tmp_path)
    result = service.synchronize(("agent-1",), command_id="selected")
    assert result.requested == 1
    assert repository.get_daily_report("agent-2", "2026-07-20").raw_response is None


def test_agent_discovered_after_cycle_open_gets_manual_report_placeholder(tmp_path):
    repository, fake, service = build(tmp_path)
    service.synchronize(("agent-1",), command_id="opens-cycle")
    repository.upsert_agent(
        ai_id="agent-late", name="Late", agent_kind="project", status="active",
        availability="available", source="test",
    )
    fake.responses["agent-late"] = "late discovered Agent report"
    result = service.synchronize(("agent-late",), command_id="late-agent")
    assert result.assessed == 1
    assert repository.get_daily_report("agent-late", "2026-07-20").raw_response == "late discovered Agent report"


def test_command_is_single_flight_and_releases_after_background_run(tmp_path):
    repository, _fake, service = build(tmp_path)
    callbacks = []
    commands = HRManualDailySyncCommands(
        service, tracker=HRCommandStatusTracker(repository),
        submit=lambda callback: callbacks.append(callback) or True,
        new_id=iter(("command-1", "command-2", "command-3")).__next__,
    )
    assert commands.run(("agent-1",)).accepted is True
    assert commands.run(("agent-1",)).accepted is False
    assert repository.list_active_hr_commands()[0].status == "accepted"
    callbacks.pop()()
    assert repository.list_active_hr_commands() == ()
    assert commands.run(("agent-1",)).accepted is True
