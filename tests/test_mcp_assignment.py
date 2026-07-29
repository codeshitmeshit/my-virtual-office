import pytest

from server_services import mcp_assignment, mcp_registry


@pytest.mark.parametrize(
    ("provider_kind", "expected_client", "expected_scope"),
    [
        ("openclaw", "openclaw", "client"),
        ("codex", "codex", "client"),
        ("claude-code", "claude", "user"),
    ],
)
def test_assignment_registers_provider_client_before_installing_skill(
    provider_kind,
    expected_client,
    expected_scope,
):
    events = []

    result = mcp_assignment.assign_to_agent(
        "echo",
        {"agentId": "agent-1", "overwrite": True},
        list_agents=lambda: {
            "agents": [
                {
                    "id": "agent-1",
                    "providerKind": provider_kind,
                }
            ]
        },
        register_client=lambda name, client, body: events.append(("register", name, client)) or {"ok": True},
        install_skill=lambda name, body: events.append(("install", name, body["agentId"]))
        or {"ok": True, "skill": "mcp-echo"},
    )

    assert result["ok"] is True
    assert result["client"] == expected_client
    assert result["registrationScope"] == expected_scope
    assert events == [
        ("register", "echo", expected_client),
        ("install", "echo", "agent-1"),
    ]


def test_assignment_stops_before_skill_install_when_registration_fails():
    installs = []

    result = mcp_assignment.assign_to_agent(
        "echo",
        {"agentId": "agent-1"},
        list_agents=lambda: {"agents": [{"id": "agent-1", "providerKind": "codex"}]},
        register_client=lambda name, client, body: {
            "ok": False,
            "error": "codex CLI not found",
            "_status": 500,
        },
        install_skill=lambda name, body: installs.append((name, body)) or {"ok": True},
    )

    assert result["ok"] is False
    assert result["stage"] == "register-client"
    assert result["client"] == "codex"
    assert installs == []


def test_assignment_rejects_agents_without_a_supported_native_client():
    result = mcp_assignment.assign_to_agent(
        "echo",
        {"agentId": "agent-1"},
        list_agents=lambda: {"agents": [{"id": "agent-1", "providerKind": "hermes"}]},
        register_client=lambda *args: pytest.fail("registration must not run"),
        install_skill=lambda *args: pytest.fail("skill install must not run"),
    )

    assert result["ok"] is False
    assert result["_status"] == 400
    assert result["stage"] == "resolve-client"


def test_registry_assignment_wires_agent_provider_to_native_registration(monkeypatch):
    from server_services import agents

    calls = []
    monkeypatch.setattr(
        agents,
        "_handle_agents_list",
        lambda: {"agents": [{"id": "claude-main", "providerKind": "claude-code"}]},
    )
    monkeypatch.setattr(
        mcp_registry,
        "_handle_mcp_registry_register_native",
        lambda name, client, body=None: calls.append(("register", name, client)) or {"ok": True},
    )
    monkeypatch.setattr(
        mcp_registry,
        "_install_mcp_skill_only",
        lambda name, body: calls.append(("install", name, body["agentId"]))
        or {"ok": True, "skill": "mcp-echo"},
    )

    result = mcp_registry._handle_mcp_registry_install_skill(
        "echo",
        {"agentId": "claude-main", "overwrite": True},
    )

    assert result["ok"] is True
    assert result["client"] == "claude"
    assert calls == [
        ("register", "echo", "claude"),
        ("install", "echo", "claude-main"),
    ]
