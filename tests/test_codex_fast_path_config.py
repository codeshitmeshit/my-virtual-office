#!/usr/bin/env python3
"""Codex fast-path startup configuration and safe diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.codex_fast_path import CodexEventFastPath, CodexFastPathSettings, classify_codex_event, load_codex_fast_path_settings


def test_defaults_are_valid_enabled_and_capacity_eight():
    settings = load_codex_fast_path_settings({}, {})
    assert settings.enabled is True
    assert settings.requested_enabled is True
    assert settings.valid is True
    assert settings.max_concurrent_turns == 8
    assert settings.coalesce_min_ms == 33
    assert settings.coalesce_max_ms == 100
    assert settings.diagnostics()["startupOnly"] is True


def test_environment_overrides_valid_persisted_values():
    settings = load_codex_fast_path_settings(
        {
            "VO_CODEX_CHAT_FAST_PATH_ENABLED": "true",
            "VO_CODEX_MAX_CONCURRENT_TURNS": "2",
            "VO_CODEX_STREAM_COALESCE_MIN_MS": "40",
            "VO_CODEX_STREAM_COALESCE_MAX_MS": "80",
        },
        {"fastPath": {"enabled": False, "maxConcurrentTurns": 1}},
    )
    assert settings.enabled is True
    assert settings.valid is True
    assert settings.max_concurrent_turns == 2
    assert (settings.coalesce_min_ms, settings.coalesce_max_ms) == (40, 80)


def test_invalid_configuration_fails_closed_without_echoing_values():
    secret_canary = "Bearer do-not-expose-fast-path-config"
    settings = load_codex_fast_path_settings(
        {
            "VO_CODEX_CHAT_FAST_PATH_ENABLED": "true",
            "VO_CODEX_MAX_CONCURRENT_TURNS": secret_canary,
            "VO_CODEX_STREAM_COALESCE_MIN_MS": "99",
            "VO_CODEX_STREAM_COALESCE_MAX_MS": "40",
        },
        {},
    )
    diagnostics = settings.diagnostics()
    assert settings.requested_enabled is True
    assert settings.enabled is False
    assert settings.valid is False
    assert settings.max_concurrent_turns == 8
    assert (settings.coalesce_min_ms, settings.coalesce_max_ms) == (33, 100)
    assert set(diagnostics["issues"]) == {"invalid_max_concurrent_turns", "invalid_coalesce_window"}
    assert secret_canary not in str(diagnostics)


def test_capacity_eight_is_valid_and_nine_fails_closed():
    valid = load_codex_fast_path_settings({"VO_CODEX_MAX_CONCURRENT_TURNS": "8"}, {})
    assert valid.enabled is True
    assert valid.valid is True
    assert valid.max_concurrent_turns == 8

    invalid = load_codex_fast_path_settings({"VO_CODEX_MAX_CONCURRENT_TURNS": "9"}, {})
    assert invalid.requested_enabled is True
    assert invalid.enabled is False
    assert invalid.valid is False
    assert invalid.max_concurrent_turns == 8
    assert invalid.diagnostics()["issues"] == ["invalid_max_concurrent_turns"]


def test_explicit_disable_preserves_legacy_path_setting():
    settings = load_codex_fast_path_settings({"VO_CODEX_CHAT_FAST_PATH_ENABLED": "0"}, {})
    assert settings.requested_enabled is False
    assert settings.enabled is False
    assert settings.valid is True
    assert settings.max_concurrent_turns == 8


def test_server_load_and_safe_projection_expose_only_bounded_diagnostics(monkeypatch, tmp_path):
    config_path = tmp_path / "vo-config.json"
    config_path.write_text('{"codex":{"enabled":true}}', encoding="utf-8")
    monkeypatch.setenv("VO_CONFIG", str(config_path))
    monkeypatch.setenv("VO_STATUS_DIR", str(tmp_path / "status"))
    monkeypatch.setenv("VO_CODEX_CHAT_FAST_PATH_ENABLED", "1")
    monkeypatch.setenv("VO_CODEX_MAX_CONCURRENT_TURNS", "2")
    monkeypatch.setenv("VO_CODEX_STREAM_COALESCE_MIN_MS", "33")
    monkeypatch.setenv("VO_CODEX_STREAM_COALESCE_MAX_MS", "100")
    import server

    loaded = server._load_vo_config()
    assert loaded["codex"]["fastPath"] == {
        "requestedEnabled": True,
        "enabled": True,
        "valid": True,
        "startupOnly": True,
        "maxConcurrentTurns": 2,
        "streamCoalesceMinMs": 33,
        "streamCoalesceMaxMs": 100,
        "issues": [],
    }
    old_config = server.VO_CONFIG
    old_license = server.get_license_status
    old_codex_test = server._handle_codex_test
    old_hermes_test = server._handle_hermes_test
    old_claude_test = server._handle_claude_code_test
    server.VO_CONFIG = loaded
    server.get_license_status = lambda: {"licensed": True, "tier": "dev", "tierName": "Dev", "demo": False, "limits": {}}
    server._handle_codex_test = lambda body=None: {"ok": True}
    server._handle_hermes_test = lambda body=None: {"ok": False, "api": {}}
    server._handle_claude_code_test = lambda body=None: {"ok": False}
    try:
        safe = server._build_safe_vo_config()["codex"]["fastPath"]
        assert safe == loaded["codex"]["fastPath"]
        assert "VO_CODEX" not in str(safe)
        runtime = server._build_safe_vo_config()["codex"]["fastPathRuntime"]
        assert runtime["timing"]["maxRuns"] == 1024
        assert runtime["timing"]["maxSamplesPerMetric"] == 2048
        assert "prompt" not in str(runtime).lower()
    finally:
        server.VO_CONFIG = old_config
        server.get_license_status = old_license
        server._handle_codex_test = old_codex_test
        server._handle_hermes_test = old_hermes_test
        server._handle_claude_code_test = old_claude_test
        if server._CODEX_EVENT_COALESCER is not None:
            server._CODEX_EVENT_COALESCER.close()
        server._CODEX_EVENT_COALESCER = None
        server.PROVIDER_RUN_COORDINATOR.event_pipeline = None
        server._CODEX_EVENT_FAST_PATH = CodexEventFastPath(CodexFastPathSettings(enabled=False))


def test_disabled_event_service_is_exact_passthrough():
    service = CodexEventFastPath(CodexFastPathSettings(enabled=False))
    event = {"type": "reasoning", "text": "unchanged", "nested": {"value": 1}}
    seen = []
    result = service.process_event("agent", "conversation", "run", event, legacy_callback=lambda item: seen.append(item) or item)
    assert result is event
    assert seen == [event]
    assert seen[0] is event
    assert service.diagnostics()["disabledPassThrough"] == 1
    assert service.diagnostics()["liveScopes"] == 0


def test_enabled_event_service_classifies_sanitizes_and_sequences_by_scope():
    service = CodexEventFastPath(CodexFastPathSettings(requested_enabled=True, enabled=True), max_scopes=4)
    first = service.process_event("agent", "conversation", "run", {
        "type": "reasoning", "sequence": 9, "text": "safe", "authorization": "Bearer secret-token-value",
    })
    second = service.process_event("agent", "conversation", "run", {"type": "interaction", "status": "pending"})
    terminal = service.process_event("agent", "conversation", "run", {"type": "turn", "status": "completed"})
    assert [first["sequence"], second["sequence"], terminal["sequence"]] == [1, 2, 3]
    assert first["providerSequence"] == 9
    assert "authorization" not in first
    assert [first["eventClass"], second["eventClass"], terminal["eventClass"]] == ["transient", "durable_key", "terminal"]
    assert service.live_snapshot("agent", "conversation", "run")["status"] == "completed"
    diagnostics = service.diagnostics()
    assert diagnostics["normalized"] == 3
    assert diagnostics["transient"] == diagnostics["durableKey"] == diagnostics["terminal"] == 1


def test_event_classification_and_active_scope_capacity_are_bounded():
    assert classify_codex_event({"type": "tool", "status": "running"}) == "transient"
    assert classify_codex_event({"type": "approval", "status": "pending"}) == "durable_key"
    assert classify_codex_event({"type": "run", "status": "failed"}) == "terminal"
    service = CodexEventFastPath(CodexFastPathSettings(requested_enabled=True, enabled=True), max_scopes=2)
    assert service.begin("agent", "conversation-1", "run-1") is True
    assert service.begin("agent", "conversation-2", "run-2") is True
    assert service.begin("agent", "conversation-3", "run-3") is False
    service.end("agent", "conversation-1", "run-1")
    assert service.begin("agent", "conversation-3", "run-3") is True
    diagnostics = service.diagnostics()
    assert diagnostics["liveScopes"] == 2
    assert diagnostics["scopeEvictions"] == 1
    assert diagnostics["capacityBypass"] == 1


def test_sequences_continue_across_runs_and_live_events_are_replaceable():
    service = CodexEventFastPath(CodexFastPathSettings(requested_enabled=True, enabled=True), max_scopes=4)
    assert service.begin("agent", "conversation", "run-1", initial_sequence=7) is True
    first = service.process_event("agent", "conversation", "run-1", {"id": "delta-1", "type": "reasoning", "text": "one"})
    service.end("agent", "conversation", "run-1")
    assert service.begin("agent", "conversation", "run-2") is True
    second = service.process_event("agent", "conversation", "run-2", {"id": "delta-2", "type": "reasoning", "text": "two"})

    assert [first["sequence"], second["sequence"]] == [8, 9]
    assert [event["id"] for event in service.live_events("agent", "conversation", after=7)] == ["delta-1", "delta-2"]
    assert service.live_events("agent", "conversation", after=8)[0]["id"] == "delta-2"
