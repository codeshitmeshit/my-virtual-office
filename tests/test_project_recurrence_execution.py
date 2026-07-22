#!/usr/bin/env python3
"""Recurring execution-mode compatibility tests."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_recurrence_execution import stored_recurrence_execution_mode


def test_historical_recurrence_definitions_default_to_create_only():
    assert stored_recurrence_execution_mode({}) == "create_only"
    assert stored_recurrence_execution_mode({"executionMode": "unknown"}) == "create_only"
    assert stored_recurrence_execution_mode({"executionMode": "create_and_execute"}) == "create_and_execute"
