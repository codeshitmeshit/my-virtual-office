"""Feature-gate and restart coverage for HR startup reconciliation."""

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_bootstrap import HRBootstrap, is_hr_enabled
from services.hr_lifecycle import (
    HR_ACTIVITY_LIMIT,
    HRLifecycleAdapter,
    HRProfilePort,
    HRProviderPort,
    HRStateRepository,
)
from services.system_agent_lifecycle import (
    CallbackPresencePort,
    LifecycleStatus,
    SystemAgentLifecycleService,
    SystemAgentPorts,
)
from system_agent_fakes import FakeClock, SequenceIdProvider


@pytest.mark.parametrize("value", ("1", "true", "TRUE", "yes", "on", "enabled", " Enabled "))
def test_hr_feature_gate_accepts_explicit_truthy_values(value):
    assert is_hr_enabled({"VO_HR_ENABLED": value}) is True


@pytest.mark.parametrize("environment", ({}, {"VO_HR_ENABLED": ""}))
def test_hr_feature_gate_defaults_on(environment):
    assert is_hr_enabled(environment) is True


@pytest.mark.parametrize("environment", ({"VO_HR_ENABLED": "0"}, {"VO_HR_ENABLED": "false"}, {"VO_HR_ENABLED": "off"}))
def test_hr_feature_gate_honors_explicit_disable(environment):
    assert is_hr_enabled(environment) is False


def test_disabled_bootstrap_never_constructs_adapter_or_touches_storage(tmp_path):
    calls = []

    def forbidden_factory():
        calls.append("factory")
        raise AssertionError("disabled HR must not construct dependencies")

    result = HRBootstrap(forbidden_factory, enabled=lambda: False).reconcile_startup()
    assert result.enabled is False
    assert result.attempted is False
    assert result.state is None
    assert result.error == ""
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def idempotent_factory(tmp_path, roster, create_calls):
    clock = FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc))
    profile = HRProfilePort(APP_DIR / "hr-profile.md", tmp_path / "openclaw")

    def create_agent(params, _timeout):
        create_calls.append(dict(params))
        roster.append({
            "id": "hr",
            "name": "HR",
            "providerKind": "openclaw",
            "workspace": params["workspace"],
        })
        return {"ok": True, "agentId": "hr"}

    provider = HRProviderPort(
        list_agents=lambda _force: list(roster),
        create_agent=create_agent,
        profile_port=profile,
        sync_managed_skills=lambda _agent: {"ready": True},
    )
    repository = HRStateRepository(tmp_path / "status", clock=clock)
    lifecycle = SystemAgentLifecycleService(
        SystemAgentPorts(
            provider=provider,
            profiles=profile,
            state=repository,
            presence=CallbackPresencePort(lambda _agent, _state, _reason: None),
            clock=clock,
            new_id=SequenceIdProvider("startup"),
        ),
        provider_retry_limit=0,
        activity_limit=HR_ACTIVITY_LIMIT,
    )
    return HRLifecycleAdapter(lifecycle, repository)


def test_enabled_repeated_and_restarted_bootstrap_creates_at_most_one_hr(tmp_path):
    roster = []
    create_calls = []
    factory = lambda: idempotent_factory(tmp_path, roster, create_calls)
    first_process = HRBootstrap(factory, enabled=lambda: True)

    first = first_process.reconcile_startup()
    repeated = first_process.reconcile_startup()
    restarted_process = HRBootstrap(factory, enabled=lambda: True)
    restarted = restarted_process.reconcile_startup()

    assert first.enabled and first.attempted
    assert repeated.state["status"] == LifecycleStatus.IDLE.value
    assert restarted.state["agentId"] == "hr"
    assert restarted.state["autoCreated"] is True
    assert len(create_calls) == 1
    assert [agent["id"] for agent in roster] == ["hr"]
    assert (tmp_path / "status" / "human-resources" / "hr.json").is_file()
    assert (tmp_path / "openclaw" / "workspace-hr" / "AGENTS.md").is_file()


def test_enabled_bootstrap_reports_unexpected_construction_failure():
    result = HRBootstrap(
        lambda: (_ for _ in ()).throw(RuntimeError("construction failed")),
        enabled=lambda: True,
    ).reconcile_startup()
    assert result.enabled is True
    assert result.attempted is True
    assert result.state is None
    assert result.error == "construction failed"


def test_server_keeps_hr_bootstrap_as_feature_gated_thin_wiring():
    source = (APP_DIR / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"_hr_shared_list_agents", "_hr_shared_adapter", "_hr_profile_check_on_startup"}.issubset(functions)
    startup_source = ast.get_source_segment(source, functions["_hr_profile_check_on_startup"])
    assert "HRBootstrap(_hr_shared_adapter)" in startup_source
    assert "is_hr_enabled()" in startup_source
    assert "agents.create" not in startup_source

    main_guard = source[source.index('if __name__ == "__main__":'):]
    assert "if hr_bootstrap_service.is_hr_enabled():" in main_guard
    assert 'name="hr-profile-check"' in main_guard
