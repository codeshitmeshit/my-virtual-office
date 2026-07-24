from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_executor import AgentManagementCommandExecutor


def build_executor(calls):
    return AgentManagementCommandExecutor(
        create_agent=lambda body: calls.append(("create", body)) or {"ok": True},
        delete_agent=lambda body: calls.append(("delete", body)) or {"ok": True},
        update_agent=lambda target, patch: calls.append(("update", target, patch)),
    )


@pytest.mark.parametrize(
    ("action", "field"),
    [
        ("provider", "providerKind"),
        ("branch", "branch"),
        ("workspace", "workspace"),
        ("assignment", "assignment"),
        ("binding", "providerAgentId"),
    ],
)
def test_configuration_actions_update_only_the_owned_field(action, field):
    calls = []
    result = build_executor(calls).execute(
        action,
        "codex-local",
        {field: "before"},
        {field: "after"},
    )

    assert result["ok"] is True
    assert calls == [("update", "codex-local", {field: "after"})]


def test_create_and_delete_delegate_to_existing_operation_ports():
    calls = []
    executor = build_executor(calls)

    created = executor.execute(
        "create",
        "agent-new",
        None,
        {"id": "agent-new", "name": "Agent New"},
    )
    deleted = executor.execute(
        "delete",
        "agent-old",
        {"exists": True},
        None,
    )

    assert created["ok"] is True
    assert deleted["ok"] is True
    assert calls == [
        ("create", {"id": "agent-new", "name": "Agent New"}),
        ("delete", {"id": "agent-old"}),
    ]


def test_unknown_or_missing_action_value_never_calls_downstream_port():
    calls = []
    executor = build_executor(calls)

    unknown = executor.execute("unknown", "codex-local", None, {})
    missing = executor.execute("branch", "codex-local", None, {})

    assert unknown["_status"] == 400
    assert missing["_status"] == 400
    assert calls == []
