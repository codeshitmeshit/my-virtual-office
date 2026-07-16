#!/usr/bin/env python3
"""Focused OpenClaw home inspection and discovery coverage."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from discovery import discover_agents, inspect_openclaw_home


def test_missing_and_residual_homes_are_not_detected():
    with tempfile.TemporaryDirectory() as root:
        missing = os.path.join(root, "missing")
        assert inspect_openclaw_home(missing) == {
            "detected": False,
            "reason": "home_missing",
            "agents": [],
        }

        residual = os.path.join(root, "residual")
        os.makedirs(os.path.join(residual, "skills-library", "example"))
        inspected = inspect_openclaw_home(residual)
        assert inspected["detected"] is False
        assert inspected["reason"] == "residual_home"
        assert discover_agents(residual) == []


def test_valid_config_discovers_only_agents_with_ids():
    with tempfile.TemporaryDirectory() as home:
        with open(os.path.join(home, "openclaw.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {"list": [{"id": "main"}, {"name": "invalid"}, "invalid"]}}, f)
        inspected = inspect_openclaw_home(home)
        assert inspected["detected"] is True
        assert inspected["reason"] == "configured_agents"
        assert [agent["id"] for agent in inspected["agents"]] == ["main"]
        assert [agent["id"] for agent in discover_agents(home)] == ["main"]


def test_directory_fallback_requires_sessions_directory():
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, "agents", "ignored"))
        os.makedirs(os.path.join(home, "agents", "analyst", "sessions"))
        inspected = inspect_openclaw_home(home)
        assert inspected["detected"] is True
        assert inspected["reason"] == "agent_directories"
        assert [agent["id"] for agent in discover_agents(home)] == ["analyst"]


def test_malformed_or_empty_config_does_not_fall_back_to_directories():
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, "agents", "analyst", "sessions"))
        config_path = os.path.join(home, "openclaw.json")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("{not-json")
        inspected = inspect_openclaw_home(home)
        assert inspected["detected"] is False
        assert inspected["reason"] == "malformed_config"
        assert discover_agents(home) == []

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"agents": {"list": []}}, f)
        inspected = inspect_openclaw_home(home)
        assert inspected["detected"] is False
        assert inspected["reason"] == "no_configured_agents"
        assert discover_agents(home) == []


def test_structurally_invalid_json_is_reported_as_malformed_config():
    invalid_documents = [
        [],
        "invalid-root",
        None,
        {"agents": "invalid"},
        {"agents": []},
        {"agents": 1},
        {"agents": {"list": "invalid"}},
    ]
    with tempfile.TemporaryDirectory() as home:
        config_path = os.path.join(home, "openclaw.json")
        os.makedirs(os.path.join(home, "agents", "guessed", "sessions"))
        for document in invalid_documents:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(document, f)
            inspected = inspect_openclaw_home(home)
            assert inspected == {
                "detected": False,
                "reason": "malformed_config",
                "agents": [],
            }
            assert discover_agents(home) == []
