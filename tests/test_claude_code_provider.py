#!/usr/bin/env python3
"""Regression checks for the optional Claude Code provider harness."""

import os
import sys
import tempfile
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from discovery import discover_all_agents
from providers.claude_code import ClaudeCodeProvider, _ClaudeStreamState
import providers.claude_code as claude_provider_module


def test_disabled_provider_is_invisible():
    provider = ClaudeCodeProvider(enabled=False)
    assert provider.discover_agents() == []
    assert provider.test()["ok"] is False


def test_enabled_provider_discovers_collaborator_and_demo_reply():
    with tempfile.TemporaryDirectory() as tmp:
        workspace_root = os.path.join(tmp, "agents")
        home = os.path.join(tmp, "claude-home")
        provider = ClaudeCodeProvider(
            enabled=True,
            workspace=tmp,
            workspace_root=workspace_root,
            home_path=home,
            include_main=False,
            name="Claude QA",
            agent_id="qa",
            model="sonnet-test",
            reply_text="ack from claude",
        )
        agents = provider.discover_agents()
        assert len(agents) == 1
        agent = agents[0]
        assert agent["id"] == "claude-code-qa"
        assert agent["providerKind"] == "claude-code"
        assert agent["providerType"] == "harness"
        assert agent["name"] == "Claude QA"
        assert agent["workspace"] == tmp
        assert "chat" in agent["capabilities"]

        result = provider.send_chat_message("please review", conversation_id="conv-1")
        assert result["ok"] is True
        assert result["reply"] == "ack from claude"
        assert result["sessionId"] == "demo-conv-1"

        progress = []
        result = provider.send_chat_message("please review", conversation_id="conv-1", on_progress=progress.append)
        assert result["ok"] is True
        assert progress
        assert progress[-1]["status"] == "completed"
        assert progress[-1]["reply"] == "ack from claude"
        assert progress[-1]["sessionId"] == "demo-conv-1"


def test_claude_code_test_uses_auth_status_json_when_supported():
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "claude")
        with open(binary, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            assert cmd[:3] == [binary, "auth", "status"]
            return subprocess.CompletedProcess(cmd, 0, stdout='{"loggedIn":true,"account":{"email":"qa@example.test"}}', stderr="")

        original = claude_provider_module.subprocess.run
        claude_provider_module.subprocess.run = fake_run
        try:
            provider = ClaudeCodeProvider(
                enabled=True,
                binary=binary,
                workspace=tmp,
                workspace_root=os.path.join(tmp, "agents"),
                include_main=False,
            )
            result = provider.test()
            assert result["ok"] is True
            assert result["authOk"] is True
            assert result["authStatus"]["loggedIn"] is True
            assert result["agents"][0]["id"] == "claude-code-local"
            assert len(calls) == 1
        finally:
            claude_provider_module.subprocess.run = original


def test_claude_code_test_falls_back_to_version_when_auth_status_unsupported():
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "claude")
        with open(binary, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == [binary, "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="unknown command")
            return subprocess.CompletedProcess(cmd, 0, stdout="claude 1.2.3", stderr="")

        original = claude_provider_module.subprocess.run
        claude_provider_module.subprocess.run = fake_run
        try:
            provider = ClaudeCodeProvider(
                enabled=True,
                binary=binary,
                workspace=tmp,
                workspace_root=os.path.join(tmp, "agents"),
                include_main=False,
            )
            result = provider.test()
            assert result["ok"] is True
            assert result["authOk"] is None
            assert result["version"] == "claude 1.2.3"
            assert len(calls) == 2
        finally:
            claude_provider_module.subprocess.run = original


def test_discovery_aggregates_claude_code_without_openclaw_home():
    with tempfile.TemporaryDirectory() as oc_home, tempfile.TemporaryDirectory() as workspace:
        agents = discover_all_agents(
            oc_home,
            hermes_enabled=False,
            codex={"enabled": False},
            claude_code={
                "enabled": True,
                "workspace": workspace,
                "name": "Claude Code",
                "agentId": "local",
                "model": "sonnet-test",
                "replyText": "ok",
                "includeMain": False,
            },
        )
        assert [a["providerKind"] for a in agents] == ["claude-code"]
        assert agents[0]["statusKey"] == "claude-code-local"


def test_claude_code_native_agent_lifecycle_and_discovery():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = os.path.join(tmp, "legacy")
        workspace_root = os.path.join(tmp, "claude-agents")
        home = os.path.join(tmp, "claude-home")
        provider = ClaudeCodeProvider(
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
            model="sonnet-test",
            profile="review-bot",
            prompt="Review changes carefully.",
        )
        assert created["ok"] is True
        assert os.path.isfile(os.path.join(created["workspace"], "office-agent.json"))
        assert os.path.isfile(os.path.join(created["workspace"], "CLAUDE.md"))
        assert os.path.isfile(os.path.join(created["workspace"], ".claude", "agents", "review-bot.md"))
        assert os.path.isfile(os.path.join(home, "agents", "review-bot.md"))

        agents = provider.discover_agents()
        ids = {a["id"] for a in agents}
        assert "claude-code-local" in ids
        assert "claude-code-main" in ids
        assert "claude-code-review-bot" in ids
        review = next(a for a in agents if a["id"] == "claude-code-review-bot")
        assert review["workspace"] == created["workspace"]
        assert review["nativeAgentPath"].endswith("review-bot.md")

        deleted = provider.delete_agent("review-bot")
        assert deleted["ok"] is True
        assert deleted["deleted"] is True
        assert not os.path.exists(created["workspace"])
        assert not os.path.exists(os.path.join(home, "agents", "review-bot.md"))


def test_claude_code_custom_agent_rejects_native_dir_parent():
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "claude-home")
        provider = ClaudeCodeProvider(
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


def test_claude_code_native_user_agent_uses_profile_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "claude-home")
        native_dir = os.path.join(home, "agents")
        workspace_root = os.path.join(tmp, "agents")
        profile_workspace = os.path.join(workspace_root, "review-bot")
        os.makedirs(native_dir)
        os.makedirs(profile_workspace)
        native_agent = os.path.join(native_dir, "review-bot.md")
        with open(native_agent, "w", encoding="utf-8") as f:
            f.write('---\nname: "review-bot"\ndescription: "Native reviewer"\nmodel: "sonnet-test"\n---\nReview carefully.\n')

        provider = ClaudeCodeProvider(
            enabled=True,
            workspace=os.path.join(tmp, "legacy"),
            workspace_root=workspace_root,
            main_workspace=os.path.join(tmp, "main"),
            home_path=home,
            include_main=False,
            include_native_agents=True,
            reply_text="ok",
        )
        agents = provider.discover_agents()
        review = next(a for a in agents if a["id"] == "claude-code-review-bot" and a["claudeCodeSource"] == "native-user-agent")
        assert review["workspace"] == profile_workspace
        assert review["nativeAgentPath"] == native_agent


def test_claude_code_send_uses_profile_workspace_and_agent_flag():
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "claude")
        with open(binary, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        workspace_root = os.path.join(tmp, "agents")
        agent_workspace = os.path.join(workspace_root, "review-bot")
        os.makedirs(agent_workspace)
        calls = []

        class FakeStdout:
            def __iter__(self):
                return iter([
                    '{"type":"system","subtype":"init","session_id":"sess-1","model":"sonnet-test"}\n',
                    '{"type":"assistant","message":{"content":[{"type":"text","text":"ok"}]}}\n',
                    '{"type":"result","result":"ok","usage":{"input_tokens":1,"output_tokens":2}}\n',
                ])

        class FakeProc:
            def __init__(self, cmd, cwd, **kwargs):
                calls.append({"cmd": cmd, "cwd": cwd})
                self.stdout = FakeStdout()
                self.stderr = []
            def wait(self, timeout=None):
                return 0

        original = claude_provider_module.subprocess.Popen
        claude_provider_module.subprocess.Popen = FakeProc
        try:
            provider = ClaudeCodeProvider(
                enabled=True,
                binary=binary,
                workspace=os.path.join(tmp, "legacy"),
                workspace_root=workspace_root,
                home_path=os.path.join(tmp, "home"),
                agent_id="review-bot",
                model="sonnet-test",
                permission_mode="acceptEdits",
            )
            result = provider.send_chat_message("hello", conversation_id="conv-1")
            assert result["ok"] is True
            assert result["reply"] == "ok"
            assert calls[0]["cwd"] == agent_workspace
            assert "--agent" in calls[0]["cmd"]
            assert calls[0]["cmd"][calls[0]["cmd"].index("--agent") + 1] == "review-bot"
            assert "--permission-mode" in calls[0]["cmd"]
        finally:
            claude_provider_module.subprocess.Popen = original


def test_claude_code_send_progress_callback_streams_snapshots():
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "claude")
        with open(binary, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        progress = []

        class FakeStdout:
            def __iter__(self):
                return iter([
                    '{"type":"system","subtype":"init","session_id":"sess-1","model":"sonnet-test"}\n',
                    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tool-1","name":"Edit","input":{"file":"app.py"}}]}}\n',
                    '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"path\\":\\"app.py\\"}"}}}\n',
                    '{"type":"assistant","message":{"content":[{"type":"tool_result","tool_use_id":"tool-1","content":"done"},{"type":"text","text":"ok"}],"usage":{"input_tokens":1,"output_tokens":2}}}\n',
                    '{"type":"result","result":"ok","usage":{"input_tokens":3,"output_tokens":4}}\n',
                ])

        class FakeProc:
            def __init__(self, cmd, cwd, **kwargs):
                self.stdout = FakeStdout()
                self.stderr = []
            def wait(self, timeout=None):
                return 0

        original = claude_provider_module.subprocess.Popen
        claude_provider_module.subprocess.Popen = FakeProc
        try:
            provider = ClaudeCodeProvider(
                enabled=True,
                binary=binary,
                workspace=tmp,
                workspace_root=os.path.join(tmp, "agents"),
                home_path=os.path.join(tmp, "home"),
                agent_id="local",
            )
            result = provider.send_chat_message("hello", conversation_id="conv-1", on_progress=progress.append)
            assert result["ok"] is True
            assert result["reply"] == "ok"
            assert len(progress) >= 5
            assert progress[0]["sessionId"] == "sess-1"
            assert progress[0]["model"] == "sonnet-test"
            assert any(item["tools"] and item["tools"][0]["name"] == "Edit" for item in progress)
            assert progress[-1]["status"] == "completed"
            assert progress[-1]["reply"] == "ok"
            assert progress[-1]["tokenUsage"]["last"]["inputTokens"] == 3
            assert progress[-1]["tokenUsage"]["last"]["outputTokens"] == 4
        finally:
            claude_provider_module.subprocess.Popen = original


def test_claude_code_stream_json_argument_delta_updates_tool_args():
    state = _ClaudeStreamState()
    state.ingest({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Edit", "input": {}}]}})
    state.ingest({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{\"file\":\""}}})
    assert state.tools[0]["arguments"] == {"partial_json": "{\"file\":\""}
    state.ingest({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "app.py\"}"}}})
    assert state.tools[0]["arguments"] == {"file": "app.py"}


if __name__ == "__main__":
    test_disabled_provider_is_invisible()
    test_enabled_provider_discovers_collaborator_and_demo_reply()
    test_claude_code_test_uses_auth_status_json_when_supported()
    test_claude_code_test_falls_back_to_version_when_auth_status_unsupported()
    test_discovery_aggregates_claude_code_without_openclaw_home()
    test_claude_code_native_agent_lifecycle_and_discovery()
    test_claude_code_custom_agent_rejects_native_dir_parent()
    test_claude_code_native_user_agent_uses_profile_workspace()
    test_claude_code_send_uses_profile_workspace_and_agent_flag()
    test_claude_code_send_progress_callback_streams_snapshots()
    test_claude_code_stream_json_argument_delta_updates_tool_args()
    print("ok")
