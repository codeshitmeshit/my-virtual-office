#!/usr/bin/env python3
"""Regression checks for the optional Codex provider harness."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from discovery import discover_all_agents
from providers.codex import CodexProvider


def test_disabled_provider_is_invisible():
    provider = CodexProvider(enabled=False)
    assert provider.discover_agents() == []
    assert provider.test()["ok"] is False


def test_enabled_provider_discovers_collaborator_and_demo_reply():
    with tempfile.TemporaryDirectory() as tmp:
        provider = CodexProvider(
            enabled=True,
            workspace=tmp,
            name="Codex QA",
            agent_id="qa",
            model="gpt-test",
            reply_text="ack from codex",
        )
        agents = provider.discover_agents()
        assert len(agents) == 1
        agent = agents[0]
        assert agent["id"] == "codex-qa"
        assert agent["providerKind"] == "codex"
        assert agent["providerType"] == "harness"
        assert agent["name"] == "Codex QA"
        assert agent["workspace"] == tmp
        assert "collaboration" in agent["capabilities"]

        result = provider.send_message("please review", conversation_id="conv-1")
        assert result["ok"] is True
        assert result["reply"] == "ack from codex"
        assert result["threadId"] == "demo-conv-1"


def test_discovery_aggregates_codex_without_openclaw_home():
    with tempfile.TemporaryDirectory() as oc_home, tempfile.TemporaryDirectory() as workspace:
        agents = discover_all_agents(
            oc_home,
            hermes_enabled=False,
            codex={
                "enabled": True,
                "workspace": workspace,
                "name": "Codex",
                "agentId": "local",
                "model": "gpt-test",
                "replyText": "ok",
            },
        )
        assert [a["providerKind"] for a in agents] == ["codex"]
        assert agents[0]["statusKey"] == "codex-local"


if __name__ == "__main__":
    test_disabled_provider_is_invisible()
    test_enabled_provider_discovers_collaborator_and_demo_reply()
    test_discovery_aggregates_codex_without_openclaw_home()
    print("ok")
