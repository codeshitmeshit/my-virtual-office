#!/usr/bin/env python3
"""Durable recurring-project registration outbox tests."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_authoring_config import DEFAULT_CONFIG
from services.project_authoring_store import OUTBOX_KEY, RECURRENCES_KEY, ProjectAuthoringRootStore
from services.project_recurrence import ProjectRecurrenceReconciler, RecurrenceRegistrationPorts
from services.project_repository import ProjectRepository


def _root(count=1):
    recurrences = {}
    outbox = []
    for index in range(1, count + 1):
        recurrence_id = f"recurrence-{index}"
        recurrences[recurrence_id] = {
            "id": recurrence_id,
            "targetType": "projectTemplateInstance",
            "templateId": f"template-{index}",
            "templateVersion": 1,
            "schedule": {"kind": "cron", "expr": f"0 {index} * * *", "timezone": "UTC"},
            "paused": False,
            "state": "pending_registration",
            "requestingAgentId": "author",
            "audit": [],
            "occurrenceHistory": [],
        }
        outbox.append({
            "id": f"outbox-{recurrence_id}",
            "kind": "register_project_template_instance",
            "recurrenceId": recurrence_id,
            "state": "pending",
            "attempts": 0,
        })
    return {
        "projects": [],
        "templates": [],
        RECURRENCES_KEY: recurrences,
        OUTBOX_KEY: outbox,
    }


def _store(tmp_path, *, count=1, batch_size=20, max_attempts=3):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all(_root(count))
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    config = replace(
        DEFAULT_CONFIG,
        outbox_batch_size=batch_size,
        outbox_retry_base_seconds=2,
        outbox_retry_max_seconds=8,
        outbox_max_attempts=max_attempts,
    )
    return markdown, ProjectAuthoringRootStore(repository, config=config)


def _ports(gateway, clock, *, enabled=True, paused=False):
    return RecurrenceRegistrationPorts(
        gateway=gateway,
        validate_schedule=lambda schedule: None if schedule.get("kind") == "cron" else "invalid schedule",
        extract_job_id=lambda result: str((result.get("job") or {}).get("id") or result.get("id") or ""),
        enabled=lambda: enabled,
        paused=lambda: paused,
        clock=lambda: clock[0],
        new_token=lambda: "worker-token",
    )


def test_reconciler_registers_bounded_batch_with_distinct_template_instance_binding(tmp_path):
    markdown, store = _store(tmp_path, count=2, batch_size=1)
    calls = []

    def gateway(method, params, timeout):
        calls.append((method, params, timeout))
        return {"ok": True, "job": {"id": f"cron-{len(calls)}"}}

    clock = [datetime(2025, 3, 1, tzinfo=timezone.utc)]
    reconciler = ProjectRecurrenceReconciler(store, _ports(gateway, clock))

    first = reconciler.reconcile_once()
    root = markdown.load_all()

    assert first == {"ok": True, "status": "ready", "claimed": 1, "registered": 1, "failed": 0}
    assert len(calls) == 1
    job = calls[0][1]
    assert job["idempotencyKey"] == "vo-project-recurrence:recurrence-1"
    assert job["delivery"] == {"mode": "none"}
    recurrence = root[RECURRENCES_KEY]["recurrence-1"]
    assert recurrence["state"] == "registered"
    assert recurrence["binding"] == {
        "cronJobId": "cron-1",
        "targetType": "projectTemplateInstance",
        "recurrenceId": "recurrence-1",
        "templateId": "template-1",
        "templateVersion": 1,
        "requestingAgentId": "author",
        "schedule": {"kind": "cron", "expr": "0 1 * * *", "timezone": "UTC"},
        "enabled": True,
        "updatedAt": "2025-03-01T00:00:00+00:00",
    }
    assert root[OUTBOX_KEY][0]["state"] == "completed"
    assert root[OUTBOX_KEY][1]["state"] == "pending"
    assert root["projects"] == []

    second = reconciler.reconcile_once()
    assert second["registered"] == 1
    assert markdown.load_all()[RECURRENCES_KEY]["recurrence-2"]["binding"]["targetType"] == "projectTemplateInstance"


def test_gateway_failure_is_redacted_and_retried_with_exponential_backoff(tmp_path):
    markdown, store = _store(tmp_path, max_attempts=2)
    clock = [datetime(2025, 3, 1, tzinfo=timezone.utc)]

    def gateway(_method, _params, _timeout):
        return {"ok": False, "error": "Authorization: Bearer gateway-secret token=other-secret"}

    reconciler = ProjectRecurrenceReconciler(store, _ports(gateway, clock))
    first = reconciler.reconcile_once()
    root = markdown.load_all()
    item = root[OUTBOX_KEY][0]

    assert first["failed"] == 1
    assert item["state"] == "retry"
    assert item["attempts"] == 1
    assert item["nextAttemptAt"] == "2025-03-01T00:00:02+00:00"
    assert root[RECURRENCES_KEY]["recurrence-1"]["state"] == "registration_retry"
    assert "gateway-secret" not in json.dumps(root)
    assert "other-secret" not in json.dumps(root)

    clock[0] += timedelta(seconds=1)
    assert reconciler.reconcile_once()["claimed"] == 0
    clock[0] += timedelta(seconds=1)
    second = reconciler.reconcile_once()
    terminal = markdown.load_all()
    assert second["failed"] == 1
    assert terminal[OUTBOX_KEY][0]["state"] == "failed"
    assert terminal[RECURRENCES_KEY]["recurrence-1"]["state"] == "intervention_required"


def test_disabled_paused_and_live_claim_states_do_not_call_gateway(tmp_path):
    markdown, store = _store(tmp_path)
    clock = [datetime(2025, 3, 1, tzinfo=timezone.utc)]
    calls = []
    gateway = lambda *args: calls.append(args) or {"ok": True, "id": "cron-1"}

    assert ProjectRecurrenceReconciler(
        store, _ports(gateway, clock, enabled=False),
    ).reconcile_once()["status"] == "disabled"
    assert ProjectRecurrenceReconciler(
        store, _ports(gateway, clock, paused=True),
    ).reconcile_once()["status"] == "paused"

    root = markdown.load_all()
    root[OUTBOX_KEY][0].update({
        "state": "processing",
        "claimToken": "live-worker",
        "claimExpiresAt": "2025-03-01T00:05:00+00:00",
    })
    markdown.save_all(root)
    active = ProjectRecurrenceReconciler(store, _ports(gateway, clock)).reconcile_once()
    assert active["claimed"] == 0
    assert calls == []


def test_expired_processing_claim_is_recovered_after_restart(tmp_path):
    markdown, store = _store(tmp_path)
    root = markdown.load_all()
    root[OUTBOX_KEY][0].update({
        "state": "processing",
        "attempts": 1,
        "claimToken": "dead-worker",
        "claimExpiresAt": "2025-02-28T23:59:59+00:00",
    })
    markdown.save_all(root)
    clock = [datetime(2025, 3, 1, tzinfo=timezone.utc)]
    reconciler = ProjectRecurrenceReconciler(
        store,
        _ports(lambda *_args: {"ok": True, "id": "cron-recovered"}, clock),
    )

    result = reconciler.reconcile_once()
    recovered = markdown.load_all()

    assert result["registered"] == 1
    assert recovered[OUTBOX_KEY][0]["attempts"] == 2
    assert recovered[RECURRENCES_KEY]["recurrence-1"]["gatewayCronId"] == "cron-recovered"

