from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_authoring_observability import ProjectAuthoringObservability
from services.project_authoring_store import OUTBOX_KEY, RECURRENCES_KEY, REQUESTS_KEY


def _root() -> dict:
    return {REQUESTS_KEY: {}, OUTBOX_KEY: [], RECURRENCES_KEY: {}}


def test_records_counters_durations_and_rate_limits_structured_logs():
    emitted: list[str] = []
    clock = [100.0]
    metrics = ProjectAuthoringObservability(
        clock=lambda: clock[0], emit=emitted.append, log_interval_seconds=60,
    )

    metrics.observe("post /api/agent/project-authoring/projects", status="failure", duration_ms=12, code="idempotency_conflict")
    metrics.observe("post /api/agent/project-authoring/projects", status="failure", duration_ms=8, code="idempotency_conflict")
    metrics.observe("post /api/agent/project-authoring/projects", status="success", duration_ms=20)

    snapshot = metrics.snapshot(
        _root(), authoring_enabled=True, recurrence_enabled=False, recurrence_paused=False,
    )
    assert snapshot["counters"]["operations.total"] == 3
    assert snapshot["counters"]["operations.failure"] == 2
    assert snapshot["counters"]["logs.emitted"] == 1
    assert snapshot["counters"]["logs.suppressed"] == 1
    timing = snapshot["durations"]["post /api/agent/project-authoring/projects"]
    assert timing == {"count": 3, "totalMs": 40, "maxMs": 20, "averageMs": 13.33}
    assert len(emitted) == 1
    assert json.loads(emitted[0]) == {
        "type": "project_authoring_operation",
        "operation": "post /api/agent/project-authoring/projects",
        "status": "failure",
        "code": "idempotency_conflict",
        "durationMs": 12,
    }
    assert "secret" not in emitted[0].lower()


def test_health_ignores_legacy_requests_and_reports_outbox_age_and_intervention_safely():
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    root = _root()
    root[REQUESTS_KEY]["request-1"] = {
        "id": "request-1",
        "state": "pending",
        "createdAt": (now - timedelta(hours=2)).isoformat(),
        "requestSecretHash": "must-not-leak",
    }
    root[OUTBOX_KEY].append({
        "id": "outbox-1",
        "state": "retry",
        "createdAt": (now - timedelta(minutes=20)).isoformat(),
        "claimToken": "must-not-leak",
    })
    root[RECURRENCES_KEY]["recurrence-1"] = {
        "id": "recurrence-1",
        "state": "intervention_required",
        "updatedAt": now.isoformat(),
        "lastError": {"code": "agent_not_found", "error": "private payload", "at": now.isoformat()},
    }

    snapshot = ProjectAuthoringObservability().snapshot(
        root,
        authoring_enabled=True,
        recurrence_enabled=True,
        recurrence_paused=False,
        now=now,
    )

    assert snapshot["ok"] is False
    assert snapshot["status"] == "intervention_required"
    assert snapshot["queues"] == {
        "recurrenceOutbox": 1,
        "oldestRecurrenceOutboxAgeSeconds": 1200,
    }
    assert snapshot["interventionAlerts"] == [{
        "type": "recurrence_intervention",
        "recurrenceId": "recurrence-1",
        "code": "agent_not_found",
        "at": now.isoformat(),
    }]
    encoded = json.dumps(snapshot)
    assert "must-not-leak" not in encoded
    assert "private payload" not in encoded


def test_health_distinguishes_disabled_paused_degraded_and_healthy():
    metrics = ProjectAuthoringObservability()
    root = _root()
    assert metrics.snapshot(root, authoring_enabled=False, recurrence_enabled=False, recurrence_paused=False)["status"] == "disabled"
    assert metrics.snapshot(root, authoring_enabled=True, recurrence_enabled=True, recurrence_paused=True)["status"] == "paused"
    assert metrics.snapshot(root, authoring_enabled=True, recurrence_enabled=True, recurrence_paused=False)["status"] == "healthy"

    old = datetime.now(timezone.utc) - timedelta(hours=2)
    root[REQUESTS_KEY]["old"] = {"state": "pending", "createdAt": old.isoformat()}
    assert metrics.snapshot(root, authoring_enabled=True, recurrence_enabled=False, recurrence_paused=False)["status"] == "healthy"
    root[OUTBOX_KEY].append({"state": "pending", "createdAt": old.isoformat()})
    assert metrics.snapshot(root, authoring_enabled=True, recurrence_enabled=False, recurrence_paused=False)["status"] == "degraded"
