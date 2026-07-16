#!/usr/bin/env python3
"""Canonical VO agent communication skill coverage."""

import os
import sys
import tempfile

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
