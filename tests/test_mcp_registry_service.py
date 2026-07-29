import json

from server_services import mcp_registry


def test_mcp_registry_saves_and_redacts_env(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_registry, "_status_dir", lambda: str(tmp_path))

    saved = mcp_registry._handle_mcp_registry_save(
        {
            "name": "vibe-trading",
            "description": "Research MCP",
            "transport": "stdio",
            "command": "vibe-trading-mcp",
            "args": ["--readonly"],
            "env": {"VIBE_MODE": "research"},
        }
    )

    assert saved["ok"] is True
    assert saved["server"]["name"] == "vibe-trading"
    assert saved["server"]["envKeys"] == ["VIBE_MODE"]
    assert "env" not in saved["server"]

    raw = json.loads((tmp_path / "mcp-registry.json").read_text())
    assert raw["servers"]["vibe-trading"]["env"] == {"VIBE_MODE": "research"}

    listed = mcp_registry._handle_mcp_registry_list()
    assert listed["servers"][0]["envKeys"] == ["VIBE_MODE"]
    assert "env" not in listed["servers"][0]


def test_mcp_registry_registers_openclaw_with_config(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_registry, "_status_dir", lambda: str(tmp_path))
    calls = []

    def fake_run(args, timeout=30):
        calls.append(args)
        return {"ok": True, "data": {}}

    monkeypatch.setattr(mcp_registry, "_run_openclaw", fake_run)
    mcp_registry._handle_mcp_registry_save(
        {
            "name": "vibe-trading",
            "transport": "stdio",
            "command": "vibe-trading-mcp",
            "include": ["*"],
        }
    )

    result = mcp_registry._handle_mcp_registry_register_openclaw("vibe-trading", {})

    assert result["ok"] is True
    assert calls[0][:3] == ["mcp", "set", "vibe-trading"]
    config = json.loads(calls[0][3])
    assert config["command"] == "vibe-trading-mcp"
    assert config["include"] == ["*"]
    assert calls[1] == ["mcp", "reload"]
    assert result["server"]["openclaw"]["registered"] is True
