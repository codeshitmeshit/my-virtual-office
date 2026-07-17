#!/usr/bin/env python3
"""Configuration and overload contracts for project authoring."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_authoring_config import (
    ProjectAuthoringConfig,
    feature_disabled_error,
    is_authoring_enabled,
    is_recurrence_dispatch_paused,
    is_recurrence_enabled,
    outbox_capacity_error,
    pending_capacity_error,
)


def test_features_are_disabled_by_default_and_read_at_action_time():
    env = {}
    assert is_authoring_enabled(env) is False
    assert is_recurrence_enabled(env) is False
    assert is_recurrence_dispatch_paused(env) is False

    env["VO_AGENT_PROJECT_AUTHORING_ENABLED"] = "true"
    env["VO_PROJECT_INSTANCE_RECURRENCE_ENABLED"] = "1"
    env["VO_PROJECT_INSTANCE_RECURRENCE_DISPATCH_PAUSED"] = "yes"
    assert is_authoring_enabled(env) is True
    assert is_recurrence_enabled(env) is True
    assert is_recurrence_dispatch_paused(env) is True


def test_default_limits_match_conservative_rollout_values():
    config = ProjectAuthoringConfig.from_env({})

    assert config.body_limit_bytes == 64 * 1024
    assert config.max_initial_tasks == 100
    assert config.max_pending_per_agent == 20
    assert config.max_pending_global == 500
    assert config.max_maintenance_requests_per_project == 20
    assert config.audit_history_limit == 100
    assert config.recurrence_history_limit == 100
    assert config.terminal_retention_days == 30
    assert config.outbox_capacity == 1000
    assert config.outbox_worker_count == 2
    assert config.outbox_batch_size == 20
    assert config.outbox_retry_base_seconds == 2
    assert config.outbox_retry_max_seconds == 300
    assert config.outbox_max_attempts == 10


def test_limits_reject_invalid_values_and_clamp_extremes():
    config = ProjectAuthoringConfig.from_env({
        "VO_PROJECT_AUTHORING_BODY_LIMIT_BYTES": "invalid",
        "VO_PROJECT_AUTHORING_MAX_INITIAL_TASKS": "0",
        "VO_PROJECT_AUTHORING_MAX_PENDING_PER_AGENT": "999999",
        "VO_PROJECT_AUTHORING_OUTBOX_WORKERS": "0",
        "VO_PROJECT_AUTHORING_OUTBOX_BATCH_SIZE": "999999",
        "VO_PROJECT_AUTHORING_OUTBOX_RETRY_BASE_SECONDS": "50",
        "VO_PROJECT_AUTHORING_OUTBOX_RETRY_MAX_SECONDS": "10",
    })

    assert config.body_limit_bytes == 64 * 1024
    assert config.max_initial_tasks == 1
    assert config.max_pending_per_agent == 500
    assert config.outbox_worker_count == 1
    assert config.outbox_batch_size == 500
    assert config.outbox_retry_base_seconds == 50
    assert config.outbox_retry_max_seconds == 50


def test_overload_and_disabled_errors_have_stable_http_contracts():
    assert pending_capacity_error("agent").as_dict() == {
        "ok": False,
        "code": "project_authoring_pending_limit",
        "error": "Project authoring pending request capacity reached for agent scope",
        "retryable": True,
        "_status": 429,
        "scope": "agent",
    }
    assert pending_capacity_error("unexpected").as_dict()["scope"] == "global"
    assert outbox_capacity_error().as_dict()["_status"] == 503
    assert outbox_capacity_error().as_dict()["code"] == "project_authoring_outbox_full"
    assert feature_disabled_error("authoring").as_dict() == {
        "ok": False,
        "code": "project_authoring_disabled",
        "error": "Project authoring is disabled",
        "retryable": False,
        "_status": 503,
        "scope": "authoring",
    }
    assert feature_disabled_error("recurrence").as_dict()["code"] == "project_recurrence_disabled"
