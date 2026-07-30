from services import skill_agent_usage


def test_enrich_library_response_lists_agents_with_installed_skill(tmp_path):
    codex_root = tmp_path / "codex"
    claude_root = tmp_path / "claude"
    (codex_root / ".codex" / "skills" / "reviewer").mkdir(parents=True)
    (codex_root / ".codex" / "skills" / "reviewer" / "SKILL.md").write_text("# Reviewer\n")
    (claude_root / ".claude" / "skills").mkdir(parents=True)
    agents = [
        {
            "id": "codex-main",
            "name": "Codex",
            "emoji": "⚡",
            "branch": "开发部",
            "providerKind": "codex",
        },
        {
            "id": "claude-main",
            "name": "Claude Code",
            "emoji": "🧠",
            "branch": "开发部",
            "providerKind": "claude-code",
        },
    ]
    contexts = {
        "codex-main": {"id": "codex-main", "providerKind": "codex", "workspace": str(codex_root)},
        "claude-main": {"id": "claude-main", "providerKind": "claude-code", "workspace": str(claude_root)},
    }

    result = skill_agent_usage.enrich_library_response(
        {"skills": [{"name": "reviewer"}], "categories": []},
        agents,
        contexts.get,
    )

    assert result["skills"][0]["loadedAgentIds"] == ["codex-main"]
    assert result["skills"][0]["loadedAgents"] == [
        {
            "id": "codex-main",
            "statusKey": "codex-main",
            "name": "Codex",
            "emoji": "⚡",
            "branch": "开发部",
            "providerKind": "codex",
        }
    ]


def test_enrich_library_response_ignores_invalid_or_missing_skill_roots(tmp_path):
    agents = [{"id": "unknown", "providerKind": "unsupported"}]

    result = skill_agent_usage.enrich_library_response(
        {"skills": [{"name": "missing"}]},
        agents,
        lambda _agent_id: {"providerKind": "unsupported", "workspace": str(tmp_path)},
    )

    assert result["skills"][0]["loadedAgents"] == []
    assert result["skills"][0]["loadedAgentIds"] == []
