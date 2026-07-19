"""Transport-free management queries, pagination, body limits, and commands."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_api import HRAPIDisabledError, HRAPIValidationError, HRManagementAPI
from services.hr_config import HRConfig
from services.hr_observability import HRObservability
from services.hr_reporting import HRReportingProjection, HRReportingService
from services.hr_repository import HRRepository
from services.hr_scheduler import HRCommandReceipt, HRManualCommands


NOW = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)


class Lifecycle:
    def __init__(self):
        self.paused = False
        self.ensure_values = []

    def public_state(self, *, ensure=True):
        self.ensure_values.append(ensure)
        return {"role": "hr", "status": "paused" if self.paused else "ready"}

    def pause(self):
        self.paused = True
        return self.public_state(ensure=False)

    def resume(self):
        self.paused = False
        return self.public_state(ensure=False)


def manual_commands(accepted=True):
    commands = object.__new__(HRManualCommands)
    commands._loop = object()
    commands._submit = lambda _callback: accepted
    commands._new_id = lambda: "command-1"
    commands._on_error = lambda _command_id, _code: None
    return commands


@pytest.fixture
def setup(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    for ai_id, availability in (
        ("hr", "available"),
        ("agent-1", "available"),
        ("agent-2", "busy"),
    ):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id.title(),
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability=availability,
            source="test",
        )
    repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response="I build APIs",
        introduction="Builds APIs",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    reporting = HRReportingService(
        repository,
        clock=lambda: NOW,
        claim_token_factory=lambda request_id: f"claim:{request_id}",
    )
    opened = reporting.open_cycle(
        local_date="2026-07-19",
        timezone_name="UTC",
        scheduled_at=NOW,
        window_opens_at=NOW,
        window_closes_at=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
        eligible_ai_ids=("agent-1", "agent-2"),
    )
    reporting.submit_response(
        ai_id="agent-1",
        local_date="2026-07-19",
        raw_response="private daily report",
        submitted_at=NOW,
    )
    repository.record_successful_access(
        access_id="access-1",
        viewer_ai_id="agent-2",
        target_ai_id="agent-1",
        viewed_at=NOW.isoformat(),
        scope="public",
        request_source="skill",
        occurrence_key="view-1",
    )
    lifecycle = Lifecycle()
    config = HRConfig.from_env(
        {
            "VO_HR_ENABLED": "1",
            "VO_HR_SCHEDULER_ENABLED": "1",
            "VO_HR_TIMEZONE": "UTC",
        }
    )
    api = HRManagementAPI(
        repository,
        lifecycle,
        manual_commands(),
        HRReportingProjection(repository),
        HRObservability(clock=lambda: NOW),
        config,
        clock=lambda: NOW,
    )
    return repository, reporting, opened, lifecycle, api


def test_overview_has_lifecycle_counts_cycle_status_and_activity_without_raw_reports(setup):
    _repository, _reporting, _opened, lifecycle, api = setup
    result = api.overview()
    assert result.status == 200
    assert result.payload["hr"]["status"] == "ready"
    assert lifecycle.ensure_values == [False]
    assert result.payload["agentTotal"] == 3
    assert result.payload["availabilityCounts"] == {"available": 2, "busy": 1}
    assert result.payload["localDate"] == "2026-07-19"
    assert result.payload["reportSchedule"] == {
        "enabled": True,
        "state": "scheduled",
        "nextAt": "2026-07-20T18:00:00+00:00",
        "nextLocalAt": "2026-07-20T18:00:00+00:00",
        "timezone": "UTC",
        "dailyTime": "18:00",
    }
    assert result.payload["cycle"]["counts"]["submitted"] == 1
    assert "private daily report" not in str(result.payload["cycle"])


def test_report_schedule_exposes_due_time_before_catch_up_without_skipping_today(setup):
    _repository, _reporting, _opened, _lifecycle, api = setup
    schedule = api._report_schedule(
        local_date=date(2026, 7, 19),
        cycle_exists=False,
        now=datetime(2026, 7, 19, 20, tzinfo=timezone.utc),
    )
    assert schedule["state"] == "due"
    assert schedule["nextAt"] == "2026-07-19T18:00:00+00:00"


def test_agent_detail_is_full_human_projection_with_independent_cursors(setup):
    repository, _reporting, _opened, _lifecycle, api = setup
    access_count = len(repository.list_access_log().items)
    result = api.agent_detail("agent-1", report_limit=1, assessment_limit=1)
    assert result.status == 200
    agent = result.payload["agent"]
    assert agent["scope"] == "full"
    assert agent["aiId"] == "agent-1"
    assert agent["introduction"] == "Builds APIs"
    assert agent["reports"][0]["rawResponse"] == "private daily report"
    assert agent["identityHistory"][0]["aiId"] == "agent-1"
    assert agent["accessHistory"][0]["targetAiId"] == "agent-1"
    assert "accessNextCursor" in agent
    assert "skillReadiness" not in agent
    assert "grantReadiness" in agent
    assert "secret_digest" not in str(agent)
    assert len(repository.list_access_log().items) == access_count
    missing = api.agent_detail("missing")
    assert missing.status == 404
    assert missing.payload["code"] == "hr_agent_not_found"


def test_agent_detail_access_history_has_independent_pagination(setup):
    repository, _reporting, _opened, _lifecycle, api = setup
    repository.record_successful_access(
        access_id="access-2",
        viewer_ai_id="hr",
        target_ai_id="agent-1",
        viewed_at="2026-07-19T10:01:00Z",
        scope="public",
        request_source="test",
        occurrence_key="view-2",
    )
    first = api.agent_detail("agent-1", access_limit=1).payload["agent"]
    assert len(first["accessHistory"]) == 1
    assert first["accessNextCursor"]
    second = api.agent_detail(
        "agent-1",
        access_limit=1,
        access_cursor=first["accessNextCursor"],
    ).payload["agent"]
    assert len(second["accessHistory"]) == 1
    assert first["accessHistory"][0]["id"] != second["accessHistory"][0]["id"]
    assert second["accessNextCursor"] is None


def test_access_log_is_filtered_and_paginated(setup):
    _repository, _reporting, _opened, _lifecycle, api = setup
    result = api.access_log(target_ai_id="agent-1", limit=1)
    assert result.status == 200
    assert result.payload["items"][0]["viewerAiId"] == "agent-2"
    assert result.payload["items"][0]["targetName"] == "Agent-1"


def test_health_and_export_are_bounded_and_do_not_return_grant_digests(setup):
    repository, _reporting, _opened, _lifecycle, api = setup
    health = api.health()
    assert health.status == 200
    assert health.payload["health"]["status"] == "ok"
    assert health.payload["health"]["featureEnabled"] is True
    exported = api.export("agents", limit=2)
    assert exported.status == 200
    assert len(exported.payload["export"]["rows"]) == 2
    repository.rotate_access_grant(
        ai_id="agent-1",
        key_id="key-1",
        secret_digest="a" * 64,
        issued_at=NOW.isoformat(),
    )
    grants = api.export("access_grants")
    assert "secret_digest" not in str(grants.payload)
    assert "a" * 64 not in str(grants.payload)


def test_pause_resume_commands_use_lifecycle_port_and_reject_body_fields(setup):
    _repository, _reporting, _opened, lifecycle, api = setup
    paused = api.lifecycle_command("pause", {}, body_bytes=2)
    assert paused.status == 200
    assert lifecycle.paused is True
    resumed = api.lifecycle_command("resume", {}, body_bytes=2)
    assert resumed.status == 200
    assert lifecycle.paused is False
    with pytest.raises(HRAPIValidationError, match="empty"):
        api.lifecycle_command("pause", {"unexpected": True}, body_bytes=20)


def test_cycle_commands_return_async_receipts_and_exact_body_contract(setup):
    _repository, _reporting, opened, _lifecycle, api = setup
    run = api.cycle_command("run", {}, body_bytes=2)
    close = api.cycle_command(
        "close", {"cycleId": opened.cycle.id}, body_bytes=40
    )
    retry = api.cycle_command(
        "retry", {"cycleId": opened.cycle.id}, body_bytes=40
    )
    assert [item.status for item in (run, close, retry)] == [202, 202, 202]
    assert [item.payload["command"]["command"] for item in (run, close, retry)] == [
        "run",
        "close",
        "retry",
    ]
    with pytest.raises(HRAPIValidationError, match="only cycleId"):
        api.cycle_command(
            "close",
            {"cycleId": opened.cycle.id, "extra": True},
            body_bytes=60,
        )


def test_body_and_pagination_limits_fail_before_mutation(setup):
    _repository, _reporting, _opened, lifecycle, api = setup
    with pytest.raises(HRAPIValidationError, match="too large"):
        api.lifecycle_command(
            "pause",
            {},
            body_bytes=HRManagementAPI.MAX_BODY_BYTES + 1,
        )
    with pytest.raises(HRAPIValidationError, match="between"):
        api.access_log(limit=101)
    assert lifecycle.paused is False
    too_large = HRManagementAPI.safe_error(
        HRAPIValidationError("request body is too large")
    )
    assert too_large.status == 413
    assert too_large.payload["code"] == HRAPIValidationError.code


def test_rejected_command_queue_returns_service_unavailable(tmp_path, setup):
    repository, _reporting, _opened, lifecycle, _api = setup
    api = HRManagementAPI(
        repository,
        lifecycle,
        manual_commands(accepted=False),
        HRReportingProjection(repository),
        HRObservability(clock=lambda: NOW),
        HRConfig.from_env({"VO_HR_ENABLED": "1"}),
        clock=lambda: NOW,
    )
    result = api.cycle_command("run", {}, body_bytes=2)
    assert result.status == 503
    assert result.payload["ok"] is False


def test_disabled_feature_keeps_reads_available_and_blocks_all_mutation(setup):
    repository, _reporting, _opened, lifecycle, _api = setup
    api = HRManagementAPI(
        repository,
        lifecycle,
        manual_commands(),
        HRReportingProjection(repository),
        HRObservability(clock=lambda: NOW),
        HRConfig.from_env({"VO_HR_ENABLED": "0"}),
        clock=lambda: NOW,
    )
    assert api.overview().status == 200
    assert api.overview().payload["reportSchedule"]["state"] == "disabled"
    for callback in (
        lambda: api.lifecycle_command("pause", {}, body_bytes=2),
        lambda: api.cycle_command("run", {}, body_bytes=2),
        lambda: api.directory_sync_command({}, body_bytes=2),
    ):
        result = api.safe_error(pytest.raises(HRAPIDisabledError, callback).value)
        assert result.status == 503
        assert result.payload["code"] == "hr_disabled"
    assert lifecycle.paused is False


def test_management_api_has_no_transport_import_or_handler_dependency():
    source = (APP_DIR / "services" / "hr_api.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
