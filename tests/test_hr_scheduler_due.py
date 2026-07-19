"""VO-local due time, DST, startup catch-up, and open-cycle recovery."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_config import HRConfig
from services.hr_reporting import HRReportingService
from services.hr_repository import HRRepository
from services.hr_scheduler import HRDueTimeCalculator, HRScheduler


def config(**overrides):
    environment = {
        "VO_HR_ENABLED": "1",
        "VO_HR_SCHEDULER_ENABLED": "1",
        "VO_HR_TIMEZONE": "Asia/Shanghai",
        "VO_HR_DAILY_TIME": "18:00",
        "VO_HR_SUBMISSION_WINDOW_MINUTES": "120",
    }
    environment.update(overrides)
    return HRConfig.from_env(environment)


def services(tmp_path, now, scheduler_config=None):
    repository = HRRepository(tmp_path / "status", clock=lambda: now)
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
        clock=lambda: now,
        claim_token_factory=lambda request_id: f"claim:{request_id}",
    )
    scheduler = HRScheduler(
        scheduler_config or config(),
        repository,
        reporting,
        clock=lambda: now,
    )
    return repository, reporting, scheduler


def test_before_due_does_not_create_cycle(tmp_path):
    now = datetime(2026, 7, 19, 9, 59, tzinfo=timezone.utc)
    repository, _reporting, scheduler = services(tmp_path, now)
    result = scheduler.reconcile(("agent-1", "agent-2"))
    assert result.action == "not_due"
    assert result.window.local_date == "2026-07-19"
    assert result.window.scheduled_at == datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
    assert repository.get_daily_cycle("hr-cycle:2026-07-19") is None


def test_due_cycle_opens_once_and_restart_recovers_it(tmp_path):
    now = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
    repository, _reporting, scheduler = services(tmp_path, now)
    first = scheduler.reconcile(("hr", "agent-2", "agent-1"))
    assert first.action == "opened"
    assert first.cycle.roster_snapshot == ("agent-1", "agent-2")
    assert first.window.window_closes_at == datetime(
        2026, 7, 19, 12, tzinfo=timezone.utc
    )

    restarted_repository = HRRepository(repository.status_dir, clock=lambda: now)
    restarted_repository.initialize()
    restarted_reporting = HRReportingService(
        restarted_repository,
        clock=lambda: now,
        claim_token_factory=lambda request_id: f"restart:{request_id}",
    )
    restarted = HRScheduler(
        config(),
        restarted_repository,
        restarted_reporting,
        clock=lambda: now,
    ).reconcile(("agent-1",))
    assert restarted.action == "recover_open"
    assert restarted.cycle == first.cycle
    assert restarted.opened is None


def test_startup_after_window_creates_only_todays_missed_cycle(tmp_path):
    now = datetime(2026, 7, 19, 14, 30, tzinfo=timezone.utc)
    repository, reporting, scheduler = services(tmp_path, now)
    reporting.open_cycle(
        local_date="2026-07-18",
        timezone_name="Asia/Shanghai",
        scheduled_at=datetime(2026, 7, 18, 10, tzinfo=timezone.utc),
        window_opens_at=datetime(2026, 7, 18, 10, tzinfo=timezone.utc),
        window_closes_at=datetime(2026, 7, 18, 12, tzinfo=timezone.utc),
        eligible_ai_ids=("agent-1",),
    )
    result = scheduler.reconcile(("agent-2",))
    assert result.action == "opened_late"
    assert result.cycle.local_date == "2026-07-19"
    assert result.cycle.roster_snapshot == ("agent-2",)
    assert repository.get_daily_cycle("hr-cycle:2026-07-17") is None


def test_closed_today_is_not_reopened(tmp_path):
    now = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
    _repository, reporting, scheduler = services(tmp_path, now)
    opened = scheduler.reconcile(("agent-1",))
    reporting.close_cycle(opened.cycle.id, closed_at=now)
    result = scheduler.reconcile(("agent-2",))
    assert result.action == "already_closed"
    assert result.opened is None


def test_hr_unavailable_retries_later_without_empty_cycle(tmp_path):
    now = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
    repository, _reporting, scheduler = services(tmp_path, now)
    unavailable = scheduler.reconcile(("agent-1",), hr_available=False)
    assert unavailable.action == "hr_unavailable"
    assert repository.get_daily_cycle("hr-cycle:2026-07-19") is None
    available = scheduler.reconcile(("agent-1",), hr_available=True)
    assert available.action == "opened"


def test_master_and_scheduler_switches_have_no_reconcile_side_effect(tmp_path):
    now = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
    repository, reporting, _scheduler = services(tmp_path, now)
    consumed = []

    def eligible():
        consumed.append(True)
        yield "agent-1"

    disabled = HRScheduler(
        config(VO_HR_ENABLED="0"),
        repository,
        reporting,
        clock=lambda: (_ for _ in ()).throw(AssertionError("clock called")),
    ).reconcile(eligible())
    assert disabled.action == "disabled"
    scheduler_off = HRScheduler(
        config(VO_HR_SCHEDULER_ENABLED="0"),
        repository,
        reporting,
        clock=lambda: (_ for _ in ()).throw(AssertionError("clock called")),
    ).reconcile(eligible())
    assert scheduler_off.action == "scheduler_disabled"
    assert consumed == []


def test_local_date_is_derived_from_vo_timezone_not_utc_date(tmp_path):
    now = datetime(2026, 7, 19, 17, tzinfo=timezone.utc)
    _repository, _reporting, scheduler = services(tmp_path, now)
    result = scheduler.reconcile(("agent-1",))
    assert result.window.local_date == "2026-07-20"
    assert result.action == "not_due"


def test_nonexistent_dst_time_moves_to_first_valid_minute():
    calculator = HRDueTimeCalculator(
        config(
            VO_HR_TIMEZONE="America/New_York",
            VO_HR_DAILY_TIME="02:30",
            VO_HR_SUBMISSION_WINDOW_MINUTES="60",
        )
    )
    window = calculator.window_for_date(date(2026, 3, 8))
    assert window.dst_adjusted is True
    assert window.scheduled_at == datetime(2026, 3, 8, 7, tzinfo=timezone.utc)
    assert window.window_closes_at == datetime(2026, 3, 8, 8, tzinfo=timezone.utc)


def test_ambiguous_dst_time_uses_first_occurrence_once():
    calculator = HRDueTimeCalculator(
        config(VO_HR_TIMEZONE="America/New_York", VO_HR_DAILY_TIME="01:30")
    )
    window = calculator.window_for_date(date(2026, 11, 1))
    assert window.dst_adjusted is False
    assert window.scheduled_at == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
