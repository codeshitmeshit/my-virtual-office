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
import providers.codex as codex_provider_module


def test_from_env_loads_codex_permission_settings(monkeypatch):
    monkeypatch.setenv("VO_CODEX_SANDBOX", "danger-full-access")
    monkeypatch.setenv("VO_CODEX_APPROVAL_POLICY", "never")
    monkeypatch.setenv("VO_CODEX_ROUTE_APPROVALS_THROUGH_VO", "true")

    provider = CodexProvider.from_env()

    assert provider.sandbox == "danger-full-access"
    assert provider.approval_policy == "never"
    assert provider.route_approvals_through_vo is True


def test_disabled_provider_is_invisible():
    provider = CodexProvider(enabled=False)
    assert provider.discover_agents() == []
    assert provider.test()["ok"] is False


def test_enabled_provider_discovers_collaborator_and_demo_reply():
    with tempfile.TemporaryDirectory() as tmp:
        workspace_root = os.path.join(tmp, "agents")
        home = os.path.join(tmp, "codex-home")
        provider = CodexProvider(
            enabled=True,
            workspace=tmp,
            workspace_root=workspace_root,
            home_path=home,
            include_main=False,
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
        assert agent["providerType"] == "app-server-bridge"
        assert agent["protocol"] == "reply-text"
        assert agent["nativeRuntime"] is False
        assert agent["name"] == "Codex QA"
        assert agent["workspace"] == tmp
        assert "collaboration" in agent["capabilities"]

        tested = provider.test()
        assert tested["ok"] is True
        assert tested["protocol"] == "reply-text"
        assert tested["nativeRuntime"] is False

        result = provider.send_message("please review", conversation_id="conv-1")
        assert result["ok"] is True
        assert result["reply"] == "ack from codex"
        assert result["threadId"] == "demo-conv-1"


def test_enabled_provider_reports_app_server_bridge_metadata_without_demo_reply():
    class FailingBridge:
        def probe_auth(self, timeout_sec=15):
            return {"ok": False, "protocol": "app-server", "authOk": False, "authStatus": "", "error": "fixture unavailable"}

    with tempfile.TemporaryDirectory() as tmp:
        original_bridge = codex_provider_module.get_codex_bridge
        codex_provider_module.get_codex_bridge = lambda *args, **kwargs: FailingBridge()
        try:
            provider = CodexProvider(
                enabled=True,
                workspace=tmp,
                workspace_root=os.path.join(tmp, "agents"),
                include_main=False,
                agent_id="native",
            )
            agents = provider.discover_agents()
            assert agents[0]["providerType"] == "app-server-bridge"
            assert agents[0]["protocol"] == "app-server"
            assert agents[0]["nativeRuntime"] is True

            tested = provider.test()
            assert tested["ok"] is False
            assert tested["protocol"] == "app-server"
            assert tested["nativeRuntime"] is True
            assert "binaryDetected" in tested
            assert tested["agents"] == []
            assert tested["error"] == "fixture unavailable"
        finally:
            codex_provider_module.get_codex_bridge = original_bridge


def test_codex_app_server_auth_probe_success_is_reference_compatible():
    class FakeBridge:
        def probe_auth(self, timeout_sec=15):
            return {
                "ok": True,
                "protocol": "app-server",
                "authOk": True,
                "authStatus": "qa@example.test",
                "account": {"email": "qa@example.test"},
            }

    original = codex_provider_module.get_codex_bridge
    codex_provider_module.get_codex_bridge = lambda *args, **kwargs: FakeBridge()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            provider = CodexProvider(
                enabled=True,
                workspace=tmp,
                workspace_root=os.path.join(tmp, "agents"),
                include_main=False,
                agent_id="native",
                binary="/tmp/fake-codex",
            )
            tested = provider.test()
            assert tested["ok"] is True
            assert tested["authOk"] is True
            assert tested["authStatus"] == "qa@example.test"
            assert tested["agents"][0]["id"] == "codex-native"
    finally:
        codex_provider_module.get_codex_bridge = original


def test_codex_app_server_auth_probe_failure_hides_agents():
    class FakeBridge:
        def probe_auth(self, timeout_sec=15):
            return {
                "ok": False,
                "protocol": "app-server",
                "authOk": False,
                "authStatus": "not authenticated",
                "error": "login required",
            }

    original = codex_provider_module.get_codex_bridge
    codex_provider_module.get_codex_bridge = lambda *args, **kwargs: FakeBridge()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            provider = CodexProvider(
                enabled=True,
                workspace=tmp,
                workspace_root=os.path.join(tmp, "agents"),
                include_main=False,
                agent_id="native",
                binary="/tmp/fake-codex",
            )
            tested = provider.test()
            assert tested["ok"] is False
            assert tested["authOk"] is False
            assert tested["error"] == "login required"
            assert tested["agents"] == []
    finally:
        codex_provider_module.get_codex_bridge = original


def test_codex_reference_style_chat_facade_preserves_local_bridge_contract():
    with tempfile.TemporaryDirectory() as tmp:
        provider = CodexProvider(
            enabled=True,
            workspace=tmp,
            workspace_root=os.path.join(tmp, "agents"),
            include_main=False,
            agent_id="native",
            reply_text="facade ack",
        )
        progress = []
        result = provider.send_chat_message(
            "native",
            "please implement",
            session_id="conv-native",
            timeout_sec=5,
            on_progress=lambda item: progress.append(item),
        )
        assert result["ok"] is True
        assert result["reply"] == "facade ack"
        assert result["threadId"] == "conv-native"
        assert result["sessionId"] == "conv-native"
        assert result["providerPath"] == "reply-text"
        assert result["modifiedFiles"] == []

        pending = provider.pending_approval("native")
        assert pending["ok"] is True
        assert pending["pending"] is None

        interrupted = provider.interrupt("native")
        assert interrupted["ok"] is False
        assert interrupted["status"] == "not_found"

        approval = provider.respond_approval("native", "approval-1")
        assert approval["ok"] is False
        assert approval["status"] == "not_found"


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
                "includeMain": False,
            },
        )
        assert [a["providerKind"] for a in agents] == ["codex"]
        assert agents[0]["statusKey"] == "codex-local"


def test_codex_native_agent_lifecycle_and_discovery():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = os.path.join(tmp, "legacy")
        workspace_root = os.path.join(tmp, "codex-agents")
        home = os.path.join(tmp, "codex-home")
        provider = CodexProvider(
            enabled=True,
            workspace=workspace,
            workspace_root=workspace_root,
            home_path=home,
            agent_id="local",
            include_main=True,
            include_native_agents=True,
            register_native_agents=True,
            reply_text="ok",
        )
        created = provider.create_agent(
            name="Review Bot",
            role="Code reviewer",
            model="gpt-test",
            profile="review-bot",
            prompt="Review changes carefully.",
        )
        assert created["ok"] is True
        assert os.path.isfile(os.path.join(created["workspace"], "office-agent.json"))
        assert os.path.isfile(os.path.join(created["workspace"], ".codex", "agents", "review-bot.toml"))
        assert os.path.isfile(os.path.join(home, "agents", "review-bot.toml"))

        agents = provider.discover_agents()
        ids = {a["id"] for a in agents}
        assert "codex-local" in ids
        assert "codex-main" in ids
        assert "codex-review-bot" in ids
        review = next(a for a in agents if a["id"] == "codex-review-bot")
        assert review["workspace"] == created["workspace"]
        assert review["nativeAgentPath"].endswith("review-bot.toml")

        deleted = provider.delete_agent("review-bot")
        assert deleted["ok"] is True
        assert deleted["deleted"] is True
        assert not os.path.exists(created["workspace"])
        assert not os.path.exists(os.path.join(home, "agents", "review-bot.toml"))


def test_codex_custom_agent_rejects_native_dir_parent():
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "codex-home")
        provider = CodexProvider(
            enabled=True,
            workspace=os.path.join(tmp, "legacy"),
            workspace_root=os.path.join(tmp, "agents"),
            home_path=home,
            reply_text="ok",
        )
        native_dir = os.path.join(home, "agents")
        result = provider.create_agent(
            name="Bad",
            profile="bad",
            creation_mode="custom",
            custom_directory=native_dir,
        )
        assert result["ok"] is False
        assert "native agents directory" in result["error"]


if __name__ == "__main__":
    test_disabled_provider_is_invisible()
    test_enabled_provider_discovers_collaborator_and_demo_reply()
    test_enabled_provider_reports_app_server_bridge_metadata_without_demo_reply()
    test_codex_app_server_auth_probe_success_is_reference_compatible()
    test_codex_app_server_auth_probe_failure_hides_agents()
    test_codex_reference_style_chat_facade_preserves_local_bridge_contract()
    test_discovery_aggregates_codex_without_openclaw_home()
    test_codex_native_agent_lifecycle_and_discovery()
    test_codex_custom_agent_rejects_native_dir_parent()
    print("ok")
