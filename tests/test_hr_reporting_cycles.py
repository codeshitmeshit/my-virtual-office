"""Daily cycle creation, dated uniqueness, request states, and claim fencing."""

import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_reporting import HRReportingService, HRReportingValidationError
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 2, tzinfo=timezone.utc)


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: NOW)
    result.initialize()
    for ai_id in ("hr", "agent-1", "agent-2", "agent-3"):
        result.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability="available",
            source="test",
        )
    return result


def service(repository, token_prefix="claim"):
    return HRReportingService(
        repository,
        clock=lambda: NOW,
        claim_token_factory=lambda request_id: f"{token_prefix}:{request_id}",
        claim_lease_seconds=120,
    )


def open_cycle(service, eligible=("agent-2", "hr", "agent-1")):
    return service.open_cycle(
        local_date="2026-07-19",
        timezone_name="Asia/Shanghai",
        scheduled_at=datetime(2026, 7, 19, 10, tzinfo=timezone.utc),
        window_opens_at=datetime(2026, 7, 19, 9, 55, tzinfo=timezone.utc),
        window_closes_at=datetime(2026, 7, 19, 18, tzinfo=timezone.utc),
        eligible_ai_ids=eligible,
    )


def test_open_cycle_creates_one_request_and_report_per_eligible_agent(repository):
    result = open_cycle(service(repository))
    assert result.cycle.id == "hr-cycle:2026-07-19"
    assert result.cycle.roster_snapshot == ("agent-1", "agent-2")
    assert [item.ai_id for item in result.requests] == ["agent-1", "agent-2"]
    assert [item.status for item in result.requests] == ["pending", "pending"]
    assert [item.conversation_key for item in result.requests] == [
        "hr:daily-report:2026-07-19:agent-1",
        "hr:daily-report:2026-07-19:agent-2",
    ]
    assert [item.submission_state for item in result.reports] == ["waiting", "waiting"]
    assert repository.get_daily_report("hr", "2026-07-19") is None


def test_duplicate_trigger_and_restart_reuse_cycle_requests_and_reports(repository):
    first = open_cycle(service(repository, "first"))
    repeated = open_cycle(service(repository, "second"), eligible=("agent-3",))
    assert repeated == first

    restarted = HRRepository(repository.status_dir, clock=lambda: NOW)
    restarted.initialize()
    after_restart = open_cycle(service(restarted, "restart"), eligible=("agent-3",))
    assert after_restart == first
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT count(*) FROM daily_cycles").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM report_requests").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM daily_reports").fetchone()[0] == 2


def test_concurrent_duplicate_triggers_converge_on_one_effective_snapshot(repository):
    first_service = service(repository, "first")
    second_service = service(repository, "second")
    barrier = threading.Barrier(3)
    results = []
    failures = []

    def trigger(reporting, eligible):
        barrier.wait()
        try:
            results.append(open_cycle(reporting, eligible=eligible))
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [
        threading.Thread(target=trigger, args=(first_service, ("agent-1", "agent-2"))),
        threading.Thread(target=trigger, args=(second_service, ("agent-2", "agent-3"))),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert not failures
    assert len(results) == 2
    assert results[0].cycle.roster_snapshot == results[1].cycle.roster_snapshot
    effective = set(results[0].cycle.roster_snapshot)
    assert effective in ({"agent-1", "agent-2"}, {"agent-2", "agent-3"})
    assert {item.ai_id for item in results[0].requests} == effective
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT count(*) FROM daily_cycles").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM report_requests").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM daily_reports").fetchone()[0] == 2


def test_concurrent_claims_have_one_winner_and_durable_state(repository):
    opened = open_cycle(service(repository))
    request_id = opened.requests[0].id
    barrier = threading.Barrier(3)
    results = []

    def claim(reporting):
        barrier.wait()
        results.append(reporting.claim_request(request_id, worker_id="worker"))

    threads = [
        threading.Thread(target=claim, args=(service(repository, "one"),)),
        threading.Thread(target=claim, args=(service(repository, "two"),)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert sum(item is not None for item in results) == 1
    stored = repository.get_report_request(request_id)
    assert stored.status == "claimed"
    assert stored.attempt_count == 1
    assert stored.claim_expires_at == "2026-07-19T02:02:00+00:00"


def test_request_listing_filters_and_paginates(repository):
    opened = open_cycle(service(repository), eligible=("agent-1", "agent-2", "agent-3"))
    reporting = service(repository)
    first = reporting.list_requests(opened.cycle.id, limit=2)
    second = reporting.list_requests(
        opened.cycle.id,
        limit=2,
        cursor=first.next_cursor,
    )
    assert [item.ai_id for item in first.items] == ["agent-1", "agent-2"]
    assert [item.ai_id for item in second.items] == ["agent-3"]
    reporting.claim_request(first.items[0].id, worker_id="worker")
    claimed = reporting.list_requests(opened.cycle.id, status="claimed")
    assert [item.ai_id for item in claimed.items] == ["agent-1"]


def test_invalid_cycle_inputs_fail_before_persistence(repository):
    reporting = service(repository)
    with pytest.raises(HRReportingValidationError):
        reporting.open_cycle(
            local_date="2026-07-19",
            timezone_name="Asia/Shanghai",
            scheduled_at=datetime(2026, 7, 19, 10),
            window_opens_at=datetime(2026, 7, 19, 9, tzinfo=timezone.utc),
            window_closes_at=datetime(2026, 7, 19, 18, tzinfo=timezone.utc),
            eligible_ai_ids=("agent-1",),
        )
    with pytest.raises(HRReportingValidationError):
        open_cycle(reporting, eligible=("agent-1", None))
    assert repository.get_daily_cycle("hr-cycle:2026-07-19") is None


def test_reporting_module_has_no_server_or_transport_dependency():
    source = (APP_DIR / "services" / "hr_reporting.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
