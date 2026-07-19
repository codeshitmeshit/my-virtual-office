"""Self-tests for reusable VO system-Agent lifecycle test doubles."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from system_agent_fakes import (
    FakeClock,
    FakeSystemAgentPorts,
    SequenceIdProvider,
    TemporarySystemAgentWorkspace,
    assert_provider_call,
    assert_provider_calls,
)


@dataclass(frozen=True)
class ExampleRole:
    stable_id: str = "hr"
    display_name: str = "HR"


def test_fake_clock_and_id_provider_are_deterministic_and_thread_safe():
    start = datetime(2026, 7, 19, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    clock = FakeClock(start)
    assert clock() == start
    assert clock.advance(minutes=30) == start + timedelta(minutes=30)

    ids = SequenceIdProvider("assessment", start=7)
    with ThreadPoolExecutor(max_workers=4) as executor:
        generated = list(executor.map(lambda _: ids(), range(20)))
    assert set(generated) == {f"assessment-{value}" for value in range(7, 27)}


def test_fake_clock_rejects_ambiguous_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(datetime(2026, 7, 19, 9, 30))


def test_temporary_workspace_builds_isolated_safe_paths_and_cleans_up():
    with TemporarySystemAgentWorkspace() as workspace:
        root = workspace.root
        hr_workspace = workspace.workspace_for("hr")
        assert workspace.status_dir.is_dir()
        assert workspace.openclaw_home.is_dir()
        assert hr_workspace == workspace.openclaw_home / "workspace-hr"
        assert hr_workspace.is_dir()
        with pytest.raises(ValueError, match="safe path segment"):
            workspace.workspace_for("../outside")

    assert not root.exists()
    with pytest.raises(RuntimeError, match="not active"):
        _ = workspace.root


def test_fake_ports_cover_lifecycle_flow_and_defensively_copy_state():
    role = ExampleRole()
    with TemporarySystemAgentWorkspace() as workspace:
        ports = FakeSystemAgentPorts(workspace)
        assert ports.discover(role) is None

        agent = ports.create(role)
        assert agent["id"] == "hr"
        assert agent["name"] == "HR"
        assert ports.discover(role) == agent
        assert ports.resolve_workspace(agent) == Path(agent["workspace"])
        ports.sync_managed_skills(agent)

        source_state = {"paused": True, "nested": {"version": 1}}
        ports.save_state(role, source_state)
        source_state["nested"]["version"] = 999
        loaded = ports.load_state(role)
        loaded["nested"]["version"] = 2
        assert ports.load_state(role)["nested"]["version"] == 1

        ports.set_presence(agent, "idle")
        assert ports.synced_agents == {"hr"}
        assert ports.presence == {"hr": "idle"}
        assert_provider_call(ports, "create", role_id="hr")
        assert_provider_calls(
            ports,
            [
                "discover",
                "create",
                "discover",
                "resolve_workspace",
                "sync_managed_skills",
                "save_state",
                "load_state",
                "load_state",
                "set_presence",
            ],
        )


def test_fake_ports_inject_one_shot_failure_and_record_concurrent_calls():
    role = ExampleRole()
    with TemporarySystemAgentWorkspace() as workspace:
        ports = FakeSystemAgentPorts(workspace)
        ports.fail_next("discover", TimeoutError("provider timeout"))
        with pytest.raises(TimeoutError, match="provider timeout"):
            ports.discover(role)
        assert ports.discover(role) is None

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: ports.discover(role), range(40)))
        assert results == [None] * 40
        assert len([call for call in ports.calls if call.operation == "discover"]) == 42
