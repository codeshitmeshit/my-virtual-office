"""Bounded HR metrics, rate limiting, and sensitive-data-free health output."""

import json
import sys
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_observability import HRObservability, HRObservabilityValidationError


NOW = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)


def test_all_required_domains_record_counters_durations_and_queue_gauges():
    metrics = HRObservability(clock=lambda: NOW)
    for domain in ("lifecycle", "directory", "report", "assessment", "query", "skill"):
        metrics.increment(f"{domain}.operations_total")
        metrics.observe_duration(f"{domain}.duration_seconds", 0.25)
    metrics.increment("report.operations_total", 2)
    metrics.gauge("report.queue_depth", 7)
    metrics.gauge("assessment.oldest_queue_age_seconds", 42.5)
    snapshot = metrics.metrics()
    assert snapshot.counters["report.operations_total"] == 3
    assert snapshot.gauges["report.queue_depth"] == 7
    assert snapshot.gauges["assessment.oldest_queue_age_seconds"] == 42.5
    assert snapshot.durations["directory.duration_seconds"].count == 1
    assert snapshot.durations["directory.duration_seconds"].total_seconds == 0.25
    assert snapshot.durations["directory.duration_seconds"].max_seconds == 0.25


def test_repeated_logs_are_rate_limited_by_event_status_and_code():
    current = [NOW]
    logs = []
    metrics = HRObservability(
        logger=lambda event: logs.append(dict(event)),
        clock=lambda: current[0],
        log_rate_limit_seconds=30,
    )
    assert metrics.event("report.request", status="failed", code="timeout") is True
    assert metrics.event("report.request", status="failed", code="timeout") is False
    assert metrics.event("report.request", status="failed", code="other_error") is True
    current[0] += timedelta(seconds=30)
    assert metrics.event("report.request", status="failed", code="timeout") is True
    assert len(logs) == 3
    assert metrics.metrics().counters["report.request.suppressed"] == 1


def test_logs_have_fixed_fields_and_drop_secret_like_values():
    logs = []
    metrics = HRObservability(logger=lambda event: logs.append(dict(event)), clock=lambda: NOW)
    metrics.event(
        "assessment.generate",
        status="failed",
        code="token=super-secret",
        ai_id="Bearer abc123",
        cycle_id="provider-envelope-secret",
        duration_seconds=1.5,
    )
    encoded = json.dumps(logs, ensure_ascii=False)
    assert "super-secret" not in encoded
    assert "abc123" not in encoded
    assert "provider-envelope" not in encoded
    assert logs == [
        {
            "event": "assessment.generate",
            "status": "failed",
            "code": "invalid_code",
            "at": NOW.isoformat(),
            "durationSeconds": 1.5,
        }
    ]


def test_health_snapshot_excludes_path_error_and_sensitive_repository_fields():
    metrics = HRObservability(clock=lambda: NOW)
    health = metrics.health(
        {
            "status": "ok",
            "code": "ready",
            "schema_version": 1,
            "integrity": "ok",
            "foreign_key_violations": 0,
            "path": "/secret/status/hr.sqlite3",
            "error": "provider envelope with credential",
            "raw_response": "private report",
            "assessment": "private judgment",
            "secret_digest": "digest",
        },
        feature_enabled=True,
        scheduler_enabled=False,
    )
    serialized = json.dumps(asdict(health), ensure_ascii=False)
    assert health.status == "ok"
    for forbidden in (
        "/secret/status",
        "provider envelope",
        "private report",
        "private judgment",
        "digest",
    ):
        assert forbidden not in serialized


def test_degraded_health_is_derived_without_copying_raw_repository_error():
    metrics = HRObservability(clock=lambda: NOW)
    health = metrics.health(
        {
            "status": "error",
            "code": "integrity_failed",
            "integrity": "failed",
            "foreign_key_violations": 2,
            "error": "password=do-not-log",
        },
        feature_enabled=True,
        scheduler_enabled=True,
    )
    assert health.status == "degraded"
    assert health.foreign_key_violations == 2
    assert "do-not-log" not in str(health)


@pytest.mark.parametrize(
    "operation",
    (
        lambda metrics: metrics.increment("unknown.total"),
        lambda metrics: metrics.increment("report"),
        lambda metrics: metrics.increment("report.total", 0),
        lambda metrics: metrics.gauge("report.queue_depth", -1),
        lambda metrics: metrics.observe_duration("report.duration", float("nan")),
        lambda metrics: metrics.event("report.event", status="ok", duration_seconds=-1),
    ),
)
def test_invalid_metrics_fail_closed(operation):
    with pytest.raises(HRObservabilityValidationError):
        operation(HRObservability(clock=lambda: NOW))


def test_counter_updates_are_thread_safe():
    metrics = HRObservability(clock=lambda: NOW)
    threads = [
        threading.Thread(
            target=lambda: [metrics.increment("query.requests_total") for _ in range(200)]
        )
        for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert metrics.metrics().counters["query.requests_total"] == 1_000


def test_logging_failure_never_breaks_caller_and_is_counted():
    metrics = HRObservability(
        logger=lambda _event: (_ for _ in ()).throw(RuntimeError("logger failed")),
        clock=lambda: NOW,
    )
    assert metrics.event("lifecycle.reconcile", status="failed", code="timeout") is False
    assert metrics.metrics().counters["lifecycle.reconcile.log_failures"] == 1


def test_observability_module_has_no_report_assessment_or_provider_payload_parameters():
    source = (APP_DIR / "services" / "hr_observability.py").read_text(encoding="utf-8")
    assert "raw_response" not in source
    assert "secret_digest" not in source
    assert "provider_envelope" not in source
    assert "assessment_text" not in source
