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


def test_mcp_registry_tracks_agent_assignments(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_registry, "_status_dir", lambda: str(tmp_path))
    mcp_registry._handle_mcp_registry_save(
        {
            "name": "vibe-trading",
            "transport": "stdio",
            "command": "vibe-trading-mcp",
            "assignedAgentIds": ["market-analyst-team-agent"],
        }
    )

    added = mcp_registry._handle_mcp_registry_assign(
        "vibe-trading",
        {"agentId": "market-trader-agent", "mode": "add"},
    )

    assert added["ok"] is True
    assert added["assignedAgentIds"] == ["market-analyst-team-agent", "market-trader-agent"]
    listed = mcp_registry._handle_mcp_registry_list()
    assert listed["servers"][0]["assignedAgentIds"] == ["market-analyst-team-agent", "market-trader-agent"]


def test_mcp_registry_install_skill_adds_assignment(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_registry, "_status_dir", lambda: str(tmp_path))
    mcp_registry._handle_mcp_registry_save(
        {
            "name": "vibe-trading",
            "transport": "stdio",
            "command": "vibe-trading-mcp",
        }
    )

    from server_services import agents, skills

    calls = []
    monkeypatch.setattr(
        agents,
        "_handle_agents_list",
        lambda: {"agents": [{"id": "market-analyst-team-agent", "providerKind": "codex"}]},
    )
    monkeypatch.setattr(
        mcp_registry,
        "_handle_mcp_registry_register_native",
        lambda name, client, body=None: calls.append(("register", name, client)) or {"ok": True},
    )
    monkeypatch.setattr(skills, "_hydrate", lambda: calls.append(("hydrate",)))
    monkeypatch.setattr(
        skills,
        "_handle_skills_library_create",
        lambda body: calls.append(("create", body["name"])) or {"ok": True, "skill": body["name"]},
    )
    monkeypatch.setattr(
        skills,
        "_handle_skills_library_apply",
        lambda body: calls.append(("apply", body["skill"], body["agentId"])) or {"ok": True},
    )

    result = mcp_registry._handle_mcp_registry_install_skill(
        "vibe-trading",
        {"agentId": "market-analyst-team-agent"},
    )

    assert result["ok"] is True
    assert result["client"] == "codex"
    assert result["assignedAgentIds"] == ["market-analyst-team-agent"]
    assert calls == [
        ("register", "vibe-trading", "codex"),
        ("hydrate",),
        ("create", "mcp-vibe-trading"),
        ("apply", "mcp-vibe-trading", "market-analyst-team-agent"),
    ]
