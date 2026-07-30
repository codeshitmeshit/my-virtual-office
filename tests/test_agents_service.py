from server_services import agents


def test_agents_list_hides_retired_native_main_agents(monkeypatch):
    monkeypatch.setattr(agents, "refresh_agent_maps", lambda: None, raising=False)
    monkeypatch.setattr(agents, "_load_office_agent_overrides", lambda: ({}, {}), raising=False)
    monkeypatch.setattr(agents, "_office_agent_override_for", lambda agent, overrides: {}, raising=False)
    monkeypatch.setattr(agents, "_agent_archive_manager_meta", lambda agent_id: {}, raising=False)
    monkeypatch.setattr(agents, "_apply_agent_limit_balanced", lambda roster: roster, raising=False)
    monkeypatch.setattr(
        agents,
        "get_roster",
        lambda: [
            {
                "id": "codex-local",
                "statusKey": "codex-local",
                "name": "Codex",
                "emoji": "C",
                "providerKind": "codex",
                "source": "legacy-local",
            },
            {
                "id": "codex-main",
                "statusKey": "codex-main",
                "name": "Main",
                "emoji": "M",
                "providerKind": "codex",
                "source": "native-main",
            },
            {
                "id": "claude-code-main",
                "statusKey": "claude-code-main",
                "name": "Main",
                "emoji": "M",
                "providerKind": "claude-code",
                "source": "native-main",
            },
        ],
        raising=False,
    )

    ids = [item["id"] for item in agents._handle_agents_list()["agents"]]

    assert ids == ["codex-local"]
