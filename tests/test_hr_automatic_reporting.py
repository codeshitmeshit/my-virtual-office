"""Automatic HR pipeline wiring and collection-to-assessment ordering."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_automatic_reporting import build_hr_automatic_reporting
from services.hr_config import HRConfig
from services.hr_manual_daily_sync import CallableHRManualDailyConversation
from services.hr_repository import HRRepository
from services.hr_runtime import HRCommandRouter, build_hr_application_runtime
from services.hr_schedule_settings import HRScheduleSettingsService


NOW = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)
LOCAL_DATE = "2026-07-19"


class Lifecycle:
    def public_state(self, *, ensure=True):
        return {"agentId": "hr", "status": "idle"}

    def pause(self):
        return {"agentId": "hr", "status": "paused"}

    def resume(self):
        return {"agentId": "hr", "status": "idle"}


class Conversation:
    def __init__(self, *, fail_normalization_for=()):
        self.fail_normalization_for = set(fail_normalization_for)
        self.agent_calls = []
        self.hr_calls = []

    def ask_agent(self, ai_id, _message, conversation_key, _timeout):
        self.agent_calls.append((ai_id, conversation_key))
        return f"{ai_id} completed tracked work"

    def ask_hr(self, prompt, conversation_key, _timeout):
        self.hr_calls.append(conversation_key)
        ai_id = conversation_key.rsplit(":", 1)[-1]
        if ":daily-report-normalize:" in conversation_key:
            if ai_id in self.fail_normalization_for:
                raise RuntimeError("normalization provider failed")
            submission = json.loads(prompt.split("submission: ", 1)[1].split("\n", 1)[0])
            return json.dumps(
                {
                    "schemaVersion": 1,
                    "localDate": LOCAL_DATE,
                    "agentAiId": ai_id,
                    "completedWork": [f"{ai_id} completed tracked work"],
                    "relatedProjectsOrTasks": [],
                    "artifacts": [],
                    "blockers": [],
                    "requestedHelp": [],
                    "submission": submission,
                }
            )
        return json.dumps(
            {
                "schemaVersion": 1,
                "agentAiId": ai_id,
                "localDate": LOCAL_DATE,
                "principalContributions": [],
                "workload": "insufficient_information",
                "rationale": "Evidence is insufficient for a workload conclusion.",
                "evidenceReferences": [],
                "blockers": [],
                "strengths": [],
                "improvements": ["Add more traceable delivery evidence."],
                "runtimeDiagnosis": "Insufficient evidence.",
                "informationSufficiency": {
                    "status": "insufficient",
                    "explanation": "Only the Agent report is available.",
                },
                "hrAiId": "hr",
                "assessedAt": NOW.isoformat(),
            }
        )

    def adapter(self):
        return CallableHRManualDailyConversation(self.ask_agent, self.ask_hr)


def config(*, scheduler=True):
    return HRConfig.from_env(
        {
            "VO_HR_ENABLED": "1",
            "VO_HR_SCHEDULER_ENABLED": "1" if scheduler else "0",
            "VO_HR_TIMEZONE": "UTC",
            "VO_HR_DAILY_TIME": "18:00",
            "VO_HR_MAX_WORKERS": "2",
        }
    )


def roster(_force):
    return [
        {
            "id": "agent-1",
            "name": "Agent One",
            "providerKind": "codex",
            "availability": "available",
        },
        {
            "id": "agent-2",
            "name": "Agent Two",
            "providerKind": "hermes",
            "availability": "available",
        },
    ]


def build(tmp_path, conversation):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    runtime = build_hr_automatic_reporting(
        repository,
        config=config(),
        lifecycle=Lifecycle(),
        schedule_settings=HRScheduleSettingsService(repository),
        roster_provider=roster,
        conversation=conversation.adapter(),
        clock=lambda: NOW,
        interval_seconds=60,
    )
    return repository, runtime


def test_tick_syncs_roster_collects_and_normalizes_before_close_assessment(tmp_path):
    conversation = Conversation()
    repository, runtime = build(tmp_path, conversation)

    opened = runtime.loop.tick()
    assert opened.schedule.action == "opened"
    assert opened.reports.accepted == 2
    assert opened.normalizations.accepted == 2
    assert opened.assessments is None
    assert all(
        repository.get_daily_report(ai_id, LOCAL_DATE).normalized is not None
        for ai_id in ("agent-1", "agent-2")
    )

    closed = runtime.loop.close_and_assess("hr-cycle:2026-07-19")
    assert closed.normalizations.status == "idle"
    assert closed.assessments.accepted == 2
    assert all(
        repository.get_current_assessment(ai_id, LOCAL_DATE) is not None
        for ai_id in ("agent-1", "agent-2")
    )


def test_normalization_failure_is_isolated_and_retryable_before_assessment(tmp_path):
    conversation = Conversation(fail_normalization_for=("agent-1",))
    repository, runtime = build(tmp_path, conversation)

    first = runtime.loop.tick()
    statuses = {item.ai_id: item.status for item in first.normalizations.results}
    assert statuses == {"agent-1": "failed", "agent-2": "normalized"}
    assert repository.get_daily_report("agent-1", LOCAL_DATE).raw_response is not None
    assert repository.get_daily_report("agent-1", LOCAL_DATE).normalized is None

    closed = runtime.loop.close_and_assess("hr-cycle:2026-07-19")
    assert repository.get_current_assessment("agent-1", LOCAL_DATE) is None
    assert repository.get_current_assessment("agent-2", LOCAL_DATE) is not None

    conversation.fail_normalization_for.clear()
    retried = runtime.loop.retry("hr-cycle:2026-07-19")
    assert retried.normalizations.results[0].status == "normalized"
    assert repository.get_current_assessment("agent-1", LOCAL_DATE) is not None


def test_application_runtime_ignores_legacy_env_schedule_switch_for_page_timer(tmp_path):
    commands = HRCommandRouter()
    conversation = Conversation()
    runtime = build_hr_application_runtime(
        status_dir=tmp_path / "status",
        lifecycle=Lifecycle(),
        config=config(scheduler=False),
        commands=commands,
        roster_provider=roster,
        daily_conversation=conversation.adapter(),
    )

    assert runtime.scheduler_loop is not None
    assert commands._commands is not None


def test_running_loop_reads_page_schedule_changes_without_restart(tmp_path):
    conversation = Conversation()
    repository, runtime = build(tmp_path, conversation)
    settings = HRScheduleSettingsService(repository)

    settings.update({"enabled": False, "dailyTime": "18:00"})
    disabled = runtime.loop.tick()
    assert disabled.schedule.action == "scheduler_disabled"
    assert conversation.agent_calls == []

    settings.update({"enabled": True, "dailyTime": "19:00"})
    waiting = runtime.loop.tick()
    assert waiting.schedule.action == "not_due"
    assert waiting.schedule.window.scheduled_at.isoformat() == "2026-07-19T19:00:00+00:00"
