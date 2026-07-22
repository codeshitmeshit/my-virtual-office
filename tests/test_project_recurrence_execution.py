#!/usr/bin/env python3
"""Recurring execution-mode compatibility tests."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_recurrence_execution import (
    new_occurrence_execution_intent,
    stored_recurrence_execution_mode,
    transition_occurrence_execution_intent,
)


def test_historical_recurrence_definitions_default_to_create_only():
    assert stored_recurrence_execution_mode({}) == "create_only"
    assert stored_recurrence_execution_mode({"executionMode": "unknown"}) == "create_only"
    assert stored_recurrence_execution_mode({"executionMode": "create_and_execute"}) == "create_and_execute"


def test_execution_intent_transitions_are_bounded_and_copy_safe():
    original = new_occurrence_execution_intent(
        project_id="project-1", occurrence_id="occurrence-1", timestamp="t0",
    )
    retryable = transition_occurrence_execution_intent(
        original, state="failed_retryable", timestamp="t1", code="launcher_busy",
    )
    started = transition_occurrence_execution_intent(
        retryable, state="started", timestamp="t2", history_limit=2,
    )
    intervention = transition_occurrence_execution_intent(
        retryable, state="intervention_required", timestamp="t3", code="executor_missing",
    )

    assert original["state"] == "pending" and original["attempts"] == 0
    assert retryable["state"] == "failed_retryable" and retryable["attempts"] == 1
    assert started["state"] == "started" and started["attempts"] == 2
    assert [item["state"] for item in started["history"]] == ["failed_retryable", "started"]
    assert intervention["state"] == "intervention_required"
    assert intervention["code"] == "executor_missing"
