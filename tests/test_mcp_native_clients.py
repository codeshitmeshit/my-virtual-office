import json

from server_services import mcp_native_clients, mcp_registry


def test_codex_stdio_registration_uses_native_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mcp_native_clients,
        "_run_client",
        lambda client, args, timeout=30: calls.append((client, args)) or {"ok": True},
    )

    result = mcp_native_clients.register_native_client(
        "codex",
        {
            "name": "echo",
            "transport": "stdio",
            "command": "node",
            "args": ["server.mjs"],
            "env": {"MODE": "test"},
        },
    )

    assert result["ok"] is True
    assert calls == [
        (
            "codex",
            ["mcp", "add", "--env", "MODE=test", "echo", "--", "node", "server.mjs"],
        )
    ]


def test_claude_registration_uses_user_scoped_native_json(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mcp_native_clients,
        "_run_client",
        lambda client, args, timeout=30: calls.append((client, args)) or {"ok": True},
    )

    result = mcp_native_clients.register_native_client(
        "claude",
        {
            "name": "echo",
            "transport": "stdio",
            "command": "node",
            "args": ["server.mjs"],
            "cwd": "/tmp/mcp",
            "env": {"MODE": "test"},
        },
    )

    assert result["ok"] is True
    client, args = calls[0]
    assert client == "claude"
    assert args[:5] == ["mcp", "add-json", "--scope", "user", "echo"]
    assert json.loads(args[5]) == {
        "type": "stdio",
        "command": "node",
        "args": ["server.mjs"],
        "env": {"MODE": "test"},
    }
    assert result["warnings"] == ["Claude CLI does not persist the configured working directory"]
    assert result["warningCodes"] == [
        {
            "code": "mcp_client_cwd_not_persisted",
            "params": {"client": "Claude"},
        }
    ]


def test_codex_rejects_legacy_sse_transport(monkeypatch):
    monkeypatch.setattr(
        mcp_native_clients,
        "_run_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CLI must not run")),
    )

    result = mcp_native_clients.register_native_client(
        "codex",
        {"name": "legacy", "transport": "sse", "url": "https://example.test/sse"},
    )

    assert result["ok"] is False
    assert result["_status"] == 400
    assert "SSE" in result["error"]


def test_claude_registration_replaces_an_existing_scoped_server(monkeypatch):
    calls = []

    def fake_run(client, args, timeout=30):
        calls.append((client, args))
        if len(calls) == 1:
            return {"ok": False, "error": "MCP server echo already exists in user config"}
        return {"ok": True}

    monkeypatch.setattr(mcp_native_clients, "_run_client", fake_run)

    result = mcp_native_clients.register_native_client(
        "claude",
        {
            "name": "echo",
            "transport": "stdio",
            "command": "node",
            "args": ["updated.mjs"],
        },
    )

    assert result["ok"] is True
    assert calls[1] == (
        "claude",
        ["mcp", "remove", "echo", "--scope", "user"],
    )
    assert calls[2][1][:5] == ["mcp", "add-json", "--scope", "user", "echo"]


def test_native_client_errors_redact_environment_values(monkeypatch):
    monkeypatch.setattr(
        mcp_native_clients,
        "_run_client",
        lambda *args, **kwargs: {"ok": False, "error": "invalid TOKEN=secret-value"},
    )

    result = mcp_native_clients.register_native_client(
        "codex",
        {
            "name": "echo",
            "transport": "stdio",
            "command": "node",
            "env": {"TOKEN": "secret-value"},
        },
    )

    assert result["error"] == "invalid TOKEN=***"


def test_registry_persists_codex_and_claude_registration_status(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_registry, "_status_dir", lambda: str(tmp_path))
    calls = []

    def fake_register(client, server, claude_scope="user"):
        calls.append((client, server["name"], claude_scope))
        return {"ok": True}

    monkeypatch.setattr(mcp_native_clients, "register_native_client", fake_register)
    mcp_registry._handle_mcp_registry_save(
        {
            "name": "echo",
            "transport": "stdio",
            "command": "node",
            "args": ["server.mjs"],
        }
    )

    codex = mcp_registry._handle_mcp_registry_register_codex("echo")
    claude = mcp_registry._handle_mcp_registry_register_claude("echo", {"scope": "user"})

    assert codex["server"]["codex"]["registered"] is True
    assert claude["server"]["codex"]["registered"] is True
    assert claude["server"]["claude"]["registered"] is True
    assert calls == [("codex", "echo", "user"), ("claude", "echo", "user")]
