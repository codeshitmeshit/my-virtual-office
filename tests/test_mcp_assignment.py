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
def test_assignment_registers_provider_client_before_recording_assignment(
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
        assign_registry=lambda name, body: events.append(("assign", name, body["agentId"]))
        or {"ok": True, "assignedAgentIds": [body["agentId"]]},
    )

    assert result["ok"] is True
    assert result["client"] == expected_client
    assert result["registrationScope"] == expected_scope
    assert events == [
        ("register", "echo", expected_client),
        ("assign", "echo", "agent-1"),
    ]
    assert result["assignedAgentIds"] == ["agent-1"]
    assert "skill" not in result


def test_assignment_stops_before_registry_assignment_when_registration_fails():
    assignments = []

    result = mcp_assignment.assign_to_agent(
        "echo",
        {"agentId": "agent-1"},
        list_agents=lambda: {"agents": [{"id": "agent-1", "providerKind": "codex"}]},
        register_client=lambda name, client, body: {
            "ok": False,
            "error": "codex CLI not found",
            "_status": 500,
        },
        assign_registry=lambda name, body: assignments.append((name, body)) or {"ok": True},
    )

    assert result["ok"] is False
    assert result["stage"] == "register-client"
    assert result["client"] == "codex"
    assert assignments == []


def test_assignment_rejects_agents_without_a_supported_native_client():
    result = mcp_assignment.assign_to_agent(
        "echo",
        {"agentId": "agent-1"},
        list_agents=lambda: {"agents": [{"id": "agent-1", "providerKind": "hermes"}]},
        register_client=lambda *args: pytest.fail("registration must not run"),
        assign_registry=lambda *args: pytest.fail("assignment must not run"),
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
        "_handle_mcp_registry_assign",
        lambda name, body: calls.append(("assign", name, body["agentId"]))
        or {"ok": True, "assignedAgentIds": [body["agentId"]]},
    )

    result = mcp_registry._handle_mcp_registry_assign_agent(
        "echo",
        {"agentId": "claude-main", "overwrite": True},
    )

    assert result["ok"] is True
    assert result["client"] == "claude"
    assert calls == [
        ("register", "echo", "claude"),
        ("assign", "echo", "claude-main"),
    ]


def test_branch_assignment_registers_each_native_client_once_before_acl_update():
    calls = []

    result = mcp_assignment.assign_to_agents(
        "echo",
        {"agentIds": ["codex-a", "codex-b", "claude-a"]},
        list_agents=lambda: {
            "agents": [
                {"id": "codex-a", "providerKind": "codex"},
                {"id": "codex-b", "providerKind": "codex"},
                {"id": "claude-a", "providerKind": "claude-code"},
            ]
        },
        register_client=lambda name, client, body: calls.append(("register", client, body["agentId"])) or {"ok": True},
        assign_registry=lambda name, body: calls.append(("assign", body["agentIds"]))
        or {"ok": True, "assignedAgentIds": body["agentIds"]},
    )

    assert result["ok"] is True
    assert result["clients"] == ["codex", "claude"]
    assert calls == [
        ("register", "codex", "codex-a"),
        ("register", "claude", "claude-a"),
        ("assign", ["codex-a", "codex-b", "claude-a"]),
    ]


def test_saved_assignment_replaces_the_complete_acl_after_registration():
    calls = []

    result = mcp_assignment.assign_to_agents(
        "echo",
        {"agentIds": ["codex-a"], "mode": "replace"},
        list_agents=lambda: {"agents": [{"id": "codex-a", "providerKind": "codex"}]},
        register_client=lambda name, client, body: calls.append(("register", client)) or {"ok": True},
        assign_registry=lambda name, body: calls.append(("assign", body))
        or {"ok": True, "assignedAgentIds": body["agentIds"]},
    )

    assert result["ok"] is True
    assert calls == [
        ("register", "codex"),
        ("assign", {"agentIds": ["codex-a"], "mode": "replace"}),
    ]
