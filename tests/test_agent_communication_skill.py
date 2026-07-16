#!/usr/bin/env python3
"""Canonical VO agent communication skill coverage."""

import os
import sys
import tempfile
import json
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-agent-communication-skill-test-"))

import server


def test_canonical_loader_matches_repository_skill():
    with open(server.CANONICAL_AGENT_COMM_SKILL_PATH, "r", encoding="utf-8") as f:
        expected = f.read()
    content = server._agent_platform_comm_skill_content()
    assert content == expected
    assert "name: vo-agent-communication" in content
    assert "POST /api/agent-platform-communications/send" in content
    assert "直接调用 OpenClaw 私有 session" in content


def test_canonical_loader_rejects_wrong_identity():
    old_path = server.CANONICAL_AGENT_COMM_SKILL_PATH
    with tempfile.TemporaryDirectory() as tmp:
        invalid = os.path.join(tmp, "SKILL.md")
        with open(invalid, "w", encoding="utf-8") as f:
            f.write("---\nname: wrong-skill\n---\n")
        server.CANONICAL_AGENT_COMM_SKILL_PATH = invalid
        try:
            try:
                server._agent_platform_comm_skill_content()
                raise AssertionError("invalid canonical identity was accepted")
            except ValueError as exc:
                assert "must declare name" in str(exc)
        finally:
            server.CANONICAL_AGENT_COMM_SKILL_PATH = old_path


def test_library_seed_uses_canonical_content_and_migrates_only_reserved_legacy():
    old_config = server.VO_CONFIG
    with tempfile.TemporaryDirectory() as home:
        server.VO_CONFIG = {**server.VO_CONFIG, "openclaw": {**server.VO_CONFIG["openclaw"], "homePath": home}}
        lib = os.path.join(home, "skills-library")
        legacy = os.path.join(lib, server.LEGACY_AGENT_PLATFORM_COMM_SKILL_NAME)
        unrelated = os.path.join(lib, "user-skill")
        os.makedirs(legacy)
        os.makedirs(unrelated)
        with open(os.path.join(legacy, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("legacy managed content")
        with open(os.path.join(unrelated, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("user content")
        try:
            canonical_path = server._ensure_builtin_communication_skill()
            assert canonical_path == os.path.join(lib, server.AGENT_PLATFORM_COMM_SKILL_NAME, "SKILL.md")
            with open(canonical_path, "r", encoding="utf-8") as f:
                assert f.read() == server._agent_platform_comm_skill_content()
            assert not os.path.exists(legacy)
            with open(os.path.join(unrelated, "SKILL.md"), "r", encoding="utf-8") as f:
                assert f.read() == "user content"
        finally:
            server.VO_CONFIG = old_config


def _openclaw_agent(workspace, agent_id="analyst"):
    return {"id": agent_id, "statusKey": agent_id, "providerKind": "openclaw", "workspace": workspace}


def test_workspace_sync_installs_noops_and_upgrades_managed_copy():
    old_base = server.WORKSPACE_BASE
    with tempfile.TemporaryDirectory() as home:
        workspace = os.path.join(home, "workspace-analyst")
        os.makedirs(workspace)
        server.WORKSPACE_BASE = home
        try:
            first = server._sync_openclaw_communication_skill(_openclaw_agent(workspace))
            assert first["ready"] is True and first["status"] == "updated"
            skill_dir = os.path.join(workspace, "skills", server.AGENT_PLATFORM_COMM_SKILL_NAME)
            skill_path = os.path.join(skill_dir, "SKILL.md")
            marker_path = os.path.join(skill_dir, server.AGENT_COMM_SKILL_MARKER)
            with open(marker_path, "r", encoding="utf-8") as f:
                marker = json.load(f)
            assert marker["managedBy"] == "virtual-office"
            assert marker["sha256"] == first["sha256"]

            before_mtime = os.stat(skill_path).st_mtime_ns
            second = server._sync_openclaw_communication_skill(_openclaw_agent(workspace))
            assert second["ready"] is True and second["status"] == "ready"
            assert os.stat(skill_path).st_mtime_ns == before_mtime

            with open(skill_path, "w", encoding="utf-8") as f:
                f.write("old managed content")
            upgraded = server._sync_openclaw_communication_skill(_openclaw_agent(workspace))
            assert upgraded["ready"] is True and upgraded["status"] == "updated"
            with open(skill_path, "r", encoding="utf-8") as f:
                assert f.read() == server._agent_platform_comm_skill_content()
        finally:
            server.WORKSPACE_BASE = old_base


def test_workspace_sync_preserves_unmarked_conflict_and_unrelated_files():
    old_base = server.WORKSPACE_BASE
    with tempfile.TemporaryDirectory() as home:
        workspace = os.path.join(home, "workspace-analyst")
        skill_dir = os.path.join(workspace, "skills", server.AGENT_PLATFORM_COMM_SKILL_NAME)
        unrelated = os.path.join(workspace, "skills", "user-skill", "SKILL.md")
        os.makedirs(skill_dir)
        os.makedirs(os.path.dirname(unrelated))
        conflict_path = os.path.join(skill_dir, "SKILL.md")
        with open(conflict_path, "w", encoding="utf-8") as f:
            f.write("user-owned conflicting content")
        with open(unrelated, "w", encoding="utf-8") as f:
            f.write("keep me")
        server.WORKSPACE_BASE = home
        try:
            result = server._sync_openclaw_communication_skill(_openclaw_agent(workspace))
            assert result == {"ready": False, "status": "conflict", "updated": False}
            with open(conflict_path, "r", encoding="utf-8") as f:
                assert f.read() == "user-owned conflicting content"
            with open(unrelated, "r", encoding="utf-8") as f:
                assert f.read() == "keep me"
        finally:
            server.WORKSPACE_BASE = old_base


def test_workspace_sync_migrates_known_legacy_and_rejects_unknown_legacy():
    old_base = server.WORKSPACE_BASE
    known_legacy = """---
name: AgentPlatform-to-AgentPlatform_Communications
---
# AgentPlatform-to-AgentPlatform Communications
Do **not** bypass the office.
POST /api/agent-platform-communications/send
"""
    with tempfile.TemporaryDirectory() as home:
        server.WORKSPACE_BASE = home
        try:
            for agent_id, legacy_content, expected in (
                ("known", known_legacy, "updated"),
                ("unknown", "user legacy content", "legacy_conflict"),
            ):
                workspace = os.path.join(home, f"workspace-{agent_id}")
                legacy_dir = os.path.join(workspace, "skills", server.LEGACY_AGENT_PLATFORM_COMM_SKILL_NAME)
                os.makedirs(legacy_dir)
                with open(os.path.join(legacy_dir, "SKILL.md"), "w", encoding="utf-8") as f:
                    f.write(legacy_content)
                result = server._sync_openclaw_communication_skill(_openclaw_agent(workspace, agent_id))
                assert result["status"] == expected
                assert os.path.isdir(legacy_dir) is (expected == "legacy_conflict")
        finally:
            server.WORKSPACE_BASE = old_base


def test_workspace_sync_rejects_outside_or_missing_workspace():
    old_base = server.WORKSPACE_BASE
    with tempfile.TemporaryDirectory() as root:
        home = os.path.join(root, "home")
        outside = os.path.join(root, "outside")
        os.makedirs(home)
        os.makedirs(outside)
        server.WORKSPACE_BASE = home
        try:
            rejected = server._sync_openclaw_communication_skill(_openclaw_agent(outside))
            assert rejected["status"] == "path_rejected"
            missing = server._sync_openclaw_communication_skill(_openclaw_agent(os.path.join(home, "missing")))
            assert missing["status"] == "workspace_missing"
            not_applicable = server._sync_openclaw_communication_skill({"providerKind": "codex", "workspace": outside})
            assert not_applicable["status"] == "not_applicable"
        finally:
            server.WORKSPACE_BASE = old_base


def test_discovery_sync_attaches_readiness_and_isolates_agent_failures():
    old_discover = server.discover_all_agents
    old_sync = server._sync_openclaw_communication_skill
    old_hermes_gateway = server._hermes_platform_roster_agent
    agents = [
        {"id": "ready", "statusKey": "ready", "providerKind": "openclaw", "workspace": "/tmp/ready"},
        {"id": "broken", "statusKey": "broken", "providerKind": "openclaw", "workspace": "/tmp/broken"},
        {"id": "codex-local", "statusKey": "codex-local", "providerKind": "codex", "workspace": "/tmp/codex"},
    ]
    calls = []
    server.discover_all_agents = lambda *args, **kwargs: [dict(agent) for agent in agents]
    server._hermes_platform_roster_agent = lambda: None

    def fake_sync(agent):
        calls.append(agent["id"])
        if agent["id"] == "broken":
            raise PermissionError("fixture")
        return {"ready": True, "status": "ready", "updated": False}

    server._sync_openclaw_communication_skill = fake_sync
    try:
        roster = server._discover_roster()
        assert [agent["id"] for agent in roster] == ["ready", "broken", "codex-local"]
        assert calls == ["ready", "broken"]
        assert roster[0]["communicationSkill"]["ready"] is True
        assert roster[1]["communicationSkill"] == {
            "ready": False,
            "status": "error",
            "updated": False,
            "error": "PermissionError",
        }
        assert "communicationSkill" not in roster[2]
    finally:
        server.discover_all_agents = old_discover
        server._sync_openclaw_communication_skill = old_sync
        server._hermes_platform_roster_agent = old_hermes_gateway


def test_workspace_payload_exposes_discovery_readiness():
    old_roster = server._discovered_roster
    old_discovered_at = server._discovered_at
    old_base = server.WORKSPACE_BASE
    with tempfile.TemporaryDirectory() as home:
        workspace = os.path.join(home, "workspace-analyst")
        os.makedirs(workspace)
        readiness = {"ready": False, "status": "conflict", "updated": False}
        server.WORKSPACE_BASE = home
        server._discovered_roster = [{
            "id": "analyst",
            "statusKey": "analyst",
            "providerKind": "openclaw",
            "workspace": workspace,
            "name": "Analyst",
            "emoji": "📊",
            "communicationSkill": readiness,
        }]
        server._discovered_at = time.time()
        server.refresh_agent_maps()
        try:
            payload = server._get_agent_workspace_payload("analyst")
            assert payload["ok"] is True
            assert payload["agent"]["communicationSkill"] == readiness
        finally:
            server._discovered_roster = old_roster
            server._discovered_at = old_discovered_at
            server.WORKSPACE_BASE = old_base
            server.refresh_agent_maps()


def test_openclaw_agent_template_requires_vo_routing_without_private_fallback():
    agents_md = server._agent_template_files("Analyst", "Market analyst", "📊")["AGENTS.md"]
    assert "`vo-agent-communication`" in agents_md
    assert "/api/agent-platform-communications/send" in agents_md
    assert "`sessions_list`" in agents_md
    assert "`sessions_send`" in agents_md
    assert "`openclaw agents`" in agents_md
    assert "report the real failure and stop" in agents_md


def test_openclaw_agent_creation_installs_skill_and_reports_partial_failure():
    old_base = server.WORKSPACE_BASE
    old_gateway = server._gateway_rpc_call
    old_model = server._default_openclaw_agent_model
    old_refresh = server.refresh_agent_maps
    old_sync = server._sync_openclaw_communication_skill
    with tempfile.TemporaryDirectory() as home:
        server.WORKSPACE_BASE = home
        server._default_openclaw_agent_model = lambda: ""
        server.refresh_agent_maps = lambda: None

        def fake_gateway(method, params=None, timeout=20):
            if method == "agents.create":
                os.makedirs(params["workspace"], exist_ok=True)
                return {"ok": True, "agentId": "analyst"}
            return {"ok": True}

        server._gateway_rpc_call = fake_gateway
        try:
            server._sync_openclaw_communication_skill = old_sync
            created = server._handle_agent_create({"name": "Analyst", "id": "analyst"})
            assert created["ok"] is True
            assert created["communicationSkill"]["ready"] is True

            server._sync_openclaw_communication_skill = lambda agent: {
                "ready": False, "status": "conflict", "updated": False,
            }
            partial = server._handle_agent_create({"name": "Blocked", "id": "blocked"})
            assert partial["ok"] is False
            assert partial["agentCreated"] is True
            assert partial["code"] == "agent_created_communication_skill_not_ready"
            assert partial["communicationSkill"]["status"] == "conflict"
        finally:
            server.WORKSPACE_BASE = old_base
            server._gateway_rpc_call = old_gateway
            server._default_openclaw_agent_model = old_model
            server.refresh_agent_maps = old_refresh
            server._sync_openclaw_communication_skill = old_sync


def test_existing_archive_manager_repairs_communication_skill():
    old_load = server._archive_manager_load_state
    old_roster = server._archive_manager_roster_agent
    old_profiles = server._archive_manager_write_profile_files
    old_sync = server._sync_openclaw_communication_skill
    old_save = server._archive_manager_save_state
    old_activity = server._archive_manager_append_activity
    calls = []
    server._archive_manager_load_state = lambda: {}
    server._archive_manager_roster_agent = lambda: {
        "id": server.ARCHIVE_MANAGER_AGENT_ID,
        "statusKey": server.ARCHIVE_MANAGER_AGENT_ID,
        "providerKind": "openclaw",
        "workspace": "/tmp/archive-manager",
    }
    server._archive_manager_write_profile_files = lambda agent_id: {
        "ok": True,
        "workspace": "/tmp/archive-manager",
        "profileFiles": [],
        "profileVersion": "test",
        "updated": False,
    }
    server._sync_openclaw_communication_skill = lambda agent: calls.append(agent) or {
        "ready": True, "status": "ready", "updated": False,
    }
    server._archive_manager_save_state = lambda state: state
    server._archive_manager_append_activity = lambda *args, **kwargs: None
    try:
        state = server._archive_manager_create_if_missing()
        assert state["status"] == "idle"
        assert state["communicationSkill"]["ready"] is True
        assert calls[0]["workspace"] == "/tmp/archive-manager"
    finally:
        server._archive_manager_load_state = old_load
        server._archive_manager_roster_agent = old_roster
        server._archive_manager_write_profile_files = old_profiles
        server._sync_openclaw_communication_skill = old_sync
        server._archive_manager_save_state = old_save
        server._archive_manager_append_activity = old_activity
