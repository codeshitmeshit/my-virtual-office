#!/usr/bin/env python3
"""Tests for project-wide execution order helpers."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_execution_ordering import execution_order_map, ordered_tasks


def test_execution_order_map_preserves_partial_explicit_orders_and_fills_gaps():
    project = {
        "tasks": [
            {"id": "review", "title": "Review task", "order": 0, "executionOrder": 1},
            {"id": "backlog-a", "title": "Backlog A", "order": 0, "executionOrder": None},
            {"id": "backlog-b", "title": "Backlog B", "order": 1, "executionOrder": None},
            {"id": "explicit", "title": "Explicit", "order": 2, "executionOrder": 7},
        ]
    }

    orders = execution_order_map(project)

    assert orders == {
        "review": 1,
        "backlog-a": 2,
        "backlog-b": 3,
        "explicit": 7,
    }
    assert [task["id"] for task in ordered_tasks(project)] == [
        "review",
        "backlog-a",
        "backlog-b",
        "explicit",
    ]


def test_execution_order_map_reassigns_duplicate_explicit_orders():
    project = {
        "tasks": [
            {"id": "first", "order": 0, "executionOrder": 1},
            {"id": "duplicate", "order": 1, "executionOrder": 1},
            {"id": "legacy", "order": 2, "executionOrder": None},
        ]
    }

    orders = execution_order_map(project)

    assert orders == {"first": 1, "duplicate": 2, "legacy": 3}
