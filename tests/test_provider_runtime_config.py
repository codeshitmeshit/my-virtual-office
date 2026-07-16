#!/usr/bin/env python3
"""Provider runtime config persistence and safe exposure coverage."""

import os
import sys
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

STATUS_DIR = tempfile.mkdtemp(prefix="vo-provider-runtime-config-test-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_CLAUDE_CODE_ENABLED"] = "0"

import server


def test_setup_config_merge_preserves_provider_secrets_and_strips_codex_demo_reply():
    existing = {
        "hermes": {
            "enabled": True,
            "homePath": "/old/hermes",
            "apiEnabled": True,
            "apiUrl": "http://127.0.0.1:8642",
            "apiKey": "secret-token",
            "customField": "keep",
        },
        "codex": {"enabled": True, "workspace": "/old/workspace", "replyText": "demo"},
        "claudeCode": {"enabled": False, "workspace": "/old/claude", "timeoutSec": 900, "includeMain": True},
        "_setupComplete": True,
    }
    incoming = {
        "hermes": {
            "homePath": "/new/hermes",
            "preferApi": False,
            "apiKey": "",
        },
        "codex": {"workspace": "/new/workspace", "workspaceRoot": "/new/codex-agents", "model": "gpt-5-codex"},
        "claudeCode": {"enabled": True, "binary": "claude", "workspaceRoot": "/new/claude-agents"},
        "_ignored": {"bad": True},
    }

    merged = server._merge_setup_config(existing, incoming)

    assert merged["hermes"]["homePath"] == "/new/hermes"
    assert merged["hermes"]["preferApi"] is False
    assert merged["hermes"]["apiKey"] == "secret-token"
    assert merged["hermes"]["customField"] == "keep"
    assert merged["codex"]["workspace"] == "/new/workspace"
    assert merged["codex"]["workspaceRoot"] == "/new/codex-agents"
    assert "replyText" not in merged["codex"]
    assert merged["codex"]["model"] == "gpt-5-codex"
    assert merged["claudeCode"]["enabled"] is True
    assert merged["claudeCode"]["workspaceRoot"] == "/new/claude-agents"
    assert merged["claudeCode"]["timeoutSec"] == 900
    assert merged["claudeCode"]["includeMain"] is True
    assert "_ignored" not in merged


def test_persist_setup_payload_writes_explicit_vo_config_path_for_feature_settings():
    old_env_config = os.environ.get("VO_CONFIG")
    old_env_status = os.environ.get("VO_STATUS_DIR")
    old_config = server.VO_CONFIG
    old_workspace_base = server.WORKSPACE_BASE
    old_discover = server._discover_roster
    old_refresh = server.refresh_agent_maps
    old_gateway_stop = server.gateway_presence.stop
    old_gateway_start = server.gateway_presence.start
    with tempfile.TemporaryDirectory(prefix="vo-explicit-config-") as tmp:
        explicit_dir = os.path.join(tmp, "explicit")
        status_dir = os.path.join(tmp, "status")
        os.makedirs(explicit_dir)
        os.makedirs(status_dir)
        explicit_path = os.path.join(explicit_dir, "vo-config.json")
        status_path = os.path.join(status_dir, "vo-config.json")
        with open(explicit_path, "w", encoding="utf-8") as f:
            json.dump({
                "_setupComplete": True,
                "openclaw": {"homePath": "/tmp/openclaw"},
                "features": {"shiftEnterToSend": False},
            }, f)
        os.environ["VO_CONFIG"] = explicit_path
        os.environ["VO_STATUS_DIR"] = status_dir
        server._discover_roster = lambda: []
        server.refresh_agent_maps = lambda: None
        server.gateway_presence.stop = lambda: None
        server.gateway_presence.start = lambda *args, **kwargs: None
        try:
            result = server._persist_setup_payload({"features": {"shiftEnterToSend": True}})
            assert result["ok"] is True
            with open(explicit_path, "r", encoding="utf-8") as f:
                explicit_saved = json.load(f)
            assert explicit_saved["features"]["shiftEnterToSend"] is True
            assert not os.path.exists(status_path)
            assert server.VO_CONFIG["features"]["shiftEnterToSend"] is True
        finally:
            if old_env_config is None:
                os.environ.pop("VO_CONFIG", None)
            else:
                os.environ["VO_CONFIG"] = old_env_config
            if old_env_status is None:
                os.environ.pop("VO_STATUS_DIR", None)
            else:
                os.environ["VO_STATUS_DIR"] = old_env_status
            server.VO_CONFIG = old_config
            server.WORKSPACE_BASE = old_workspace_base
            server._discover_roster = old_discover
            server.refresh_agent_maps = old_refresh
            server.gateway_presence.stop = old_gateway_stop
            server.gateway_presence.start = old_gateway_start


def test_safe_vo_config_round_trips_provider_fields_without_secret_exposure():
    old_config = server.VO_CONFIG
    old_license = server.get_license_status
    old_hermes = server._handle_hermes_test
    old_codex = server._handle_codex_test
    old_claude = server._handle_claude_code_test
    old_openclaw_inspection = server.inspect_openclaw_home
    server.VO_CONFIG = {
        **server.VO_CONFIG,
        "hermes": {
            "enabled": True,
            "homePath": "/tmp/hermes-home",
            "binary": "/tmp/hermes",
            "timeoutSec": 600,
            "apiEnabled": True,
            "preferApi": True,
            "apiUrl": "http://127.0.0.1:8642",
            "apiKey": "secret-token",
        },
        "codex": {
            "enabled": True,
            "workspace": "/tmp/codex-workspace",
            "homePath": "/tmp/codex-home",
            "binary": "codex",
            "workspaceRoot": "/tmp/codex-agents",
            "mainWorkspace": "/tmp/codex-main",
            "name": "Codex Runtime",
            "agentId": "local",
            "model": "gpt-5-codex",
            "replyText": "hidden demo text",
            "bridgeUrl": "http://127.0.0.1:17345",
            "includeMain": True,
            "includeNativeAgents": True,
            "registerNativeAgents": False,
        },
        "claudeCode": {
            "enabled": True,
            "homePath": "/tmp/claude-home",
            "binary": "claude",
            "workspace": "/tmp/claude-workspace",
            "workspaceRoot": "/tmp/claude-agents",
            "mainWorkspace": "/tmp/claude-main",
            "name": "Claude Code",
            "agentId": "local",
            "model": "sonnet",
            "replyText": "hidden claude demo text",
            "timeoutSec": 900,
            "permissionMode": "acceptEdits",
            "includeMain": True,
            "includeNativeAgents": True,
            "registerNativeAgents": False,
        },
    }
    server.get_license_status = lambda: {"licensed": True, "tier": "dev", "tierName": "Dev", "demo": False, "limits": {}}
    server._handle_hermes_test = lambda body=None: {"ok": True, "api": {"ok": True}}
    server._handle_codex_test = lambda body=None: {"ok": True}
    server._handle_claude_code_test = lambda body=None: {"ok": True}
    server.inspect_openclaw_home = lambda home: {
        "detected": False,
        "reason": "residual_home",
        "agents": [],
    }
    try:
        safe = server._build_safe_vo_config()
        assert safe["openclaw"]["detected"] is False
        assert safe["openclaw"]["detectionReason"] == "residual_home"
        assert safe["openclaw"]["agentCount"] == 0
        assert safe["hermes"]["apiEnabled"] is True
        assert safe["hermes"]["preferApi"] is True
        assert safe["hermes"]["apiUrl"] == "http://127.0.0.1:8642"
        assert safe["hermes"]["apiDetected"] is True
        assert safe["codex"]["workspace"] == "/tmp/codex-workspace"
        assert safe["codex"]["workspaceRoot"] == "/tmp/codex-agents"
        assert safe["codex"]["mainWorkspace"] == "/tmp/codex-main"
        assert safe["codex"]["model"] == "gpt-5-codex"
        assert safe["claudeCode"]["workspace"] == "/tmp/claude-workspace"
        assert safe["claudeCode"]["workspaceRoot"] == "/tmp/claude-agents"
        assert safe["claudeCode"]["mainWorkspace"] == "/tmp/claude-main"
        assert safe["claudeCode"]["permissionMode"] == "acceptEdits"
        assert safe["claudeCode"]["model"] == "sonnet"
        assert "secret-token" not in str(safe)
        assert "hidden demo text" not in str(safe)
        assert "hidden claude demo text" not in str(safe)
    finally:
        server.VO_CONFIG = old_config
        server.get_license_status = old_license
        server._handle_hermes_test = old_hermes
        server._handle_codex_test = old_codex
        server._handle_claude_code_test = old_claude
        server.inspect_openclaw_home = old_openclaw_inspection


def test_model_provider_config_includes_safe_native_runtime_status():
    old_config = server.VO_CONFIG
    old_license = server.get_license_status
    old_hermes = server._handle_hermes_test
    old_codex = server._handle_codex_test
    old_claude = server._handle_claude_code_test
    old_roster = server.get_roster
    old_config_path = server.CONFIG_PATH
    old_auth_path = server.AUTH_PROFILES_PATH
    with tempfile.TemporaryDirectory(prefix="vo-provider-model-config-") as tmp:
        cfg_path = os.path.join(tmp, "openclaw.json")
        auth_path = os.path.join(tmp, "auth-profiles.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write('{"agents":{"defaults":{"models":{"openai-codex/gpt-5":{"alias":"Codex"}}}},"models":{"providers":{}}}')
        with open(auth_path, "w", encoding="utf-8") as f:
            f.write('{"version":1,"profiles":{},"lastGood":{}}')
        server.CONFIG_PATH = cfg_path
        server.AUTH_PROFILES_PATH = auth_path
        server.VO_CONFIG = {
            **server.VO_CONFIG,
            "hermes": {
                "enabled": True,
                "homePath": "/tmp/hermes-home",
                "binary": "/tmp/hermes",
                "timeoutSec": 600,
                "apiEnabled": True,
                "preferApi": True,
                "apiUrl": "http://127.0.0.1:8642",
                "apiKey": "secret-token",
            },
            "codex": {
                "enabled": True,
                "homePath": "/tmp/codex-home",
                "binary": "codex",
                "workspace": "/tmp/codex-workspace",
                "workspaceRoot": "/tmp/codex-agents",
                "mainWorkspace": "/tmp/codex-main",
                "model": "gpt-5-codex",
                "sandbox": "workspace-write",
                "approvalPolicy": "never",
                "includeMain": True,
                "includeNativeAgents": True,
                "registerNativeAgents": False,
                "replyText": "hidden codex reply",
            },
            "claudeCode": {
                "enabled": True,
                "homePath": "/tmp/claude-home",
                "binary": "claude",
                "workspace": "/tmp/claude-workspace",
                "workspaceRoot": "/tmp/claude-agents",
                "mainWorkspace": "/tmp/claude-main",
                "model": "sonnet",
                "permissionMode": "acceptEdits",
                "includeMain": True,
                "includeNativeAgents": True,
                "registerNativeAgents": False,
                "replyText": "hidden claude reply",
            },
        }
        server.get_license_status = lambda: {"licensed": True, "tier": "dev", "tierName": "Dev", "demo": False, "limits": {}}
        server._handle_hermes_test = lambda body=None: {"ok": True, "api": {"ok": True}}
        server._handle_codex_test = lambda body=None: {"ok": True}
        server._handle_claude_code_test = lambda body=None: {"ok": True}
        server.get_roster = lambda: [
            {"providerKind": "hermes", "model": "deepseek-v4"},
            {"providerKind": "codex", "model": "gpt-5-codex"},
            {"providerKind": "claude-code", "model": "sonnet"},
        ]
        try:
            data = server.OfficeHandler._get_providers(None)
            native = data["nativeProviders"]
            assert native["hermes"]["apiEnabled"] is True
            assert native["hermes"]["preferApi"] is True
            assert native["hermes"]["apiDetected"] is True
            assert native["hermes"]["homePath"] == "/tmp/hermes-home"
            assert native["hermes"]["apiUrl"] == "http://127.0.0.1:8642"
            assert native["hermes"]["model"] == "deepseek-v4"
            assert native["codex"]["workspace"] == "/tmp/codex-workspace"
            assert native["codex"]["workspaceRoot"] == "/tmp/codex-agents"
            assert native["codex"]["mainWorkspace"] == "/tmp/codex-main"
            assert native["codex"]["homePath"] == "/tmp/codex-home"
            assert native["codex"]["sandbox"] == "workspace-write"
            assert native["codex"]["registerNativeAgents"] is False
            assert native["codex"]["model"] == "gpt-5-codex"
            assert native["claude-code"]["workspace"] == "/tmp/claude-workspace"
            assert native["claude-code"]["workspaceRoot"] == "/tmp/claude-agents"
            assert native["claude-code"]["mainWorkspace"] == "/tmp/claude-main"
            assert native["claude-code"]["homePath"] == "/tmp/claude-home"
            assert native["claude-code"]["permissionMode"] == "acceptEdits"
            assert native["claude-code"]["registerNativeAgents"] is False
            assert native["claude-code"]["model"] == "sonnet"
            assert "secret-token" not in str(data)
            assert "hidden codex reply" not in str(data)
            assert "hidden claude reply" not in str(data)
        finally:
            server.VO_CONFIG = old_config
            server.get_license_status = old_license
            server._handle_hermes_test = old_hermes
            server._handle_codex_test = old_codex
            server._handle_claude_code_test = old_claude
            server.get_roster = old_roster
            server.CONFIG_PATH = old_config_path
            server.AUTH_PROFILES_PATH = old_auth_path


def test_load_vo_config_accepts_hermes_prefer_api_alias_and_env_override():
    old_env = {key: os.environ.get(key) for key in ("VO_CONFIG", "VO_HERMES_API_ENABLED", "VO_HERMES_PREFER_API")}
    with tempfile.TemporaryDirectory(prefix="vo-prefer-api-config-") as tmp:
        cfg_path = os.path.join(tmp, "vo-config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"hermes": {"preferApi": True, "apiUrl": "http://127.0.0.1:8642"}}, f)
        try:
            os.environ["VO_CONFIG"] = cfg_path
            os.environ.pop("VO_HERMES_API_ENABLED", None)
            os.environ.pop("VO_HERMES_PREFER_API", None)
            cfg = server._load_vo_config()
            assert cfg["hermes"]["apiEnabled"] is True
            assert cfg["hermes"]["preferApi"] is True

            os.environ["VO_HERMES_PREFER_API"] = "0"
            cfg = server._load_vo_config()
            assert cfg["hermes"]["apiEnabled"] is False
            assert cfg["hermes"]["preferApi"] is False

            os.environ["VO_HERMES_API_ENABLED"] = "1"
            cfg = server._load_vo_config()
            assert cfg["hermes"]["apiEnabled"] is True
            assert cfg["hermes"]["preferApi"] is True
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def test_load_vo_config_ignores_persisted_codex_reply_text_unless_env_set():
    old_env = {key: os.environ.get(key) for key in ("VO_CONFIG", "VO_CODEX_REPLY_TEXT")}
    with tempfile.TemporaryDirectory(prefix="vo-codex-reply-config-") as tmp:
        cfg_path = os.path.join(tmp, "vo-config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"codex": {"enabled": True, "replyText": "stale fixture"}}, f)
        try:
            os.environ["VO_CONFIG"] = cfg_path
            os.environ.pop("VO_CODEX_REPLY_TEXT", None)
            cfg = server._load_vo_config()
            assert cfg["codex"]["replyText"] is None

            os.environ["VO_CODEX_REPLY_TEXT"] = "explicit fixture"
            cfg = server._load_vo_config()
            assert cfg["codex"]["replyText"] == "explicit fixture"
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    test_setup_config_merge_preserves_provider_secrets_and_strips_codex_demo_reply()
    test_persist_setup_payload_writes_explicit_vo_config_path_for_feature_settings()
    test_safe_vo_config_round_trips_provider_fields_without_secret_exposure()
    test_model_provider_config_includes_safe_native_runtime_status()
    test_load_vo_config_accepts_hermes_prefer_api_alias_and_env_override()
    test_load_vo_config_ignores_persisted_codex_reply_text_unless_env_set()
    print("ok")
