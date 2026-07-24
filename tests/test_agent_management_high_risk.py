from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_confirmations import AgentManagementConfirmationService
from services.agent_management_high_risk import AgentManagementHighRiskService
from services.agent_profile_configuration import ConfigurationActor
from services.agent_profile_store import AgentProfileStore


def test_command_consumes_exact_challenge_then_executes_once(tmp_path):
    profiles = AgentProfileStore(tmp_path / "profiles.json")
    confirmations = AgentManagementConfirmationService()
    calls = []
    service = AgentManagementHighRiskService(
        profiles=profiles,
        confirmations=confirmations,
        executor=lambda *args: calls.append(args) or {"ok": True},
    )
    actor = ConfigurationActor.human()
    change = {
        "targetAiId": "codex-local",
        "action": "branch",
        "before": {"branch": "hq"},
        "after": {"branch": "finance"},
        "revision": 0,
    }
    challenge = confirmations.issue(
        actor,
        target_ai_id=change["targetAiId"],
        action=change["action"],
        before=change["before"],
        after=change["after"],
        revision=change["revision"],
    )
    command = {**change, "challengeToken": challenge.token}

    result = service.execute(actor, command)
    replay = service.execute(actor, command)

    assert result.status == 200
    assert calls == [
        ("branch", "codex-local", {"branch": "hq"}, {"branch": "finance"})
    ]
    assert replay.status == 410


def test_boolean_or_substituted_confirmation_never_executes(tmp_path):
    profiles = AgentProfileStore(tmp_path / "profiles.json")
    confirmations = AgentManagementConfirmationService()
    calls = []
    service = AgentManagementHighRiskService(
        profiles=profiles,
        confirmations=confirmations,
        executor=lambda *args: calls.append(args) or {"ok": True},
    )
    actor = ConfigurationActor.human()
    boolean = service.execute(actor, {"confirmed": True})
    assert boolean.status == 400

    challenge = confirmations.issue(
        actor,
        target_ai_id="codex-local",
        action="workspace",
        before={"workspace": "/old"},
        after={"workspace": "/new"},
        revision=0,
    )
    substituted = service.execute(actor, {
        "challengeToken": challenge.token,
        "targetAiId": "codex-local",
        "action": "workspace",
        "before": {"workspace": "/old"},
        "after": {"workspace": "/evil"},
        "revision": 0,
    })
    assert substituted.status == 409
    assert calls == []


def test_agent_actor_cannot_execute_high_risk_command(tmp_path):
    service = AgentManagementHighRiskService(
        profiles=AgentProfileStore(tmp_path / "profiles.json"),
        confirmations=AgentManagementConfirmationService(),
        executor=lambda *_args: {"ok": True},
    )
    result = service.execute(
        ConfigurationActor.agent("codex-local"),
        {},
    )
    assert result.status == 403


@pytest.mark.parametrize(
    ("action", "before", "after"),
    [
        ("provider", {"providerKind": "openclaw"}, {"providerKind": "codex"}),
        ("branch", {"branch": "hq"}, {"branch": "finance"}),
        ("workspace", {"workspace": "/old"}, {"workspace": "/new"}),
        ("assignment", {"assignment": "review"}, {"assignment": "build"}),
        ("binding", {"providerAgentId": "old"}, {"providerAgentId": "new"}),
        ("create", None, {"id": "agent-new", "name": "Agent New"}),
        ("delete", {"exists": True}, None),
    ],
)
def test_all_supported_high_risk_actions_preserve_confirmed_impact(
    tmp_path,
    action,
    before,
    after,
):
    calls = []
    profiles = AgentProfileStore(tmp_path / "profiles.json")
    confirmations = AgentManagementConfirmationService()
    service = AgentManagementHighRiskService(
        profiles=profiles,
        confirmations=confirmations,
        executor=lambda *args: calls.append(args) or {"ok": True},
    )
    change = {
        "targetAiId": "agent-new" if action == "create" else "codex-local",
        "action": action,
        "before": before,
        "after": after,
        "revision": 0,
    }
    challenge = confirmations.issue(
        ConfigurationActor.human(),
        target_ai_id=change["targetAiId"],
        action=action,
        before=before,
        after=after,
        revision=0,
    )

    result = service.execute(
        ConfigurationActor.human(),
        {**change, "challengeToken": challenge.token},
    )

    assert result.status == 200
    assert calls == [(action, change["targetAiId"], before, after)]
