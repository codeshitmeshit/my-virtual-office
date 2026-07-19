"""Deterministic reconciliation coverage for shared system-Agent lifecycle."""

import sys
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.system_agent_lifecycle import (
    LifecycleStatus,
    ProfileSyncResult,
    ProviderAgent,
    SystemAgentLifecycleService,
    SystemAgentLifecycleState,
    SystemAgentPorts,
)
from services.system_agent_roles import HR_ROLE
from system_agent_fakes import FakeClock, SequenceIdProvider, TemporarySystemAgentWorkspace


class FakeProvider:
    def __init__(self, workspace, agents=()):
        self.workspace = workspace
        self.agents = {agent.id: agent for agent in agents}
        self.calls = []
        self.failures = defaultdict(deque)
        self.cached_discovery = None
        self.skill_ready = True
        self.create_then_raise = False
        self.fail_refresh_after_create = False
        self._lock = threading.RLock()

    def fail_next(self, operation, error):
        self.failures[operation].append(error)

    def _call(self, operation, **details):
        with self._lock:
            self.calls.append((operation, details))
            if self.failures[operation]:
                raise self.failures[operation].popleft()

    def discover(self, role, *, force_refresh=False):
        self._call("discover", force_refresh=force_refresh)
        with self._lock:
            if self.cached_discovery is not None and not force_refresh:
                return tuple(self.cached_discovery)
            return tuple(self.agents.values())

    def create(self, role):
        self._call("create", role_id=role.stable_id)
        with self._lock:
            agent = self.agents.setdefault(
                role.stable_id,
                ProviderAgent(
                    id=role.stable_id,
                    name=role.display_name,
                    provider_kind=role.provider_kind,
                    workspace=str(self.workspace.workspace_for(role.stable_id)),
                ),
            )
        if self.create_then_raise:
            self.create_then_raise = False
            raise TimeoutError("create response timed out")
        if self.fail_refresh_after_create:
            self.fail_refresh_after_create = False
            self.fail_next("discover", TimeoutError("refresh timeout one"))
            self.fail_next("discover", TimeoutError("refresh timeout two"))
        return agent

    def resolve_workspace(self, agent):
        self._call("resolve_workspace", agent_id=agent.id)
        return Path(agent.workspace) if agent.workspace else self.workspace.workspace_for(agent.id)

    def sync_managed_skills(self, agent):
        self._call("sync_managed_skills", agent_id=agent.id)
        return {"ready": self.skill_ready, "status": "ready" if self.skill_ready else "skill unavailable"}


class FakeProfiles:
    def __init__(self):
        self.calls = []
        self.failures = deque()
        self.updated = True
        self.write_partial_before_failure = False

    def fail_next(self, error):
        self.failures.append(error)

    def synchronize(self, role, agent, workspace):
        self.calls.append((role.role_key, agent.id, str(workspace)))
        if self.failures:
            if self.write_partial_before_failure:
                self.write_partial_before_failure = False
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / role.required_files[0]).write_text("partial", encoding="utf-8")
            raise self.failures.popleft()
        written = role.required_files if self.updated else ()
        unchanged = () if self.updated else role.required_files
        result = ProfileSyncResult(
            workspace=str(workspace),
            version="v1",
            updated=self.updated,
            written_files=written,
            unchanged_files=unchanged,
        )
        self.updated = False
        return result


class FakeStateRepository:
    def __init__(self, initial=None):
        self.value = initial
        self.saved = []
        self._lock = threading.Lock()

    def load(self, _role):
        with self._lock:
            return self.value

    def save(self, _role, state):
        with self._lock:
            self.value = state
            self.saved.append(state)
            return state


class FakePresence:
    def __init__(self):
        self.calls = []

    def set_presence(self, agent_id, state, reason=""):
        self.calls.append((agent_id, state, reason))


def build_service(workspace, *, agents=(), state=None, retries=1):
    provider = FakeProvider(workspace, agents)
    profiles = FakeProfiles()
    repository = FakeStateRepository(state)
    presence = FakePresence()
    clock = FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc))
    ports = SystemAgentPorts(
        provider=provider,
        profiles=profiles,
        state=repository,
        presence=presence,
        clock=clock,
        new_id=SequenceIdProvider("activity"),
    )
    return SystemAgentLifecycleService(ports, provider_retry_limit=retries), provider, profiles, repository


def existing_hr(workspace, agent_id="hr"):
    return ProviderAgent(
        id=agent_id,
        name="HR",
        provider_kind="openclaw",
        workspace=str(workspace.workspace_for(agent_id)),
    )


def operations(provider, name):
    return [call for call in provider.calls if call[0] == name]


def test_missing_agent_is_created_profiled_and_persisted_once():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, profiles, repository = build_service(workspace)
        state = service.reconcile(HR_ROLE)

        assert state.status is LifecycleStatus.IDLE
        assert state.agent_id == "hr"
        assert state.auto_created is True
        assert state.profile_version == "v1"
        assert state.communication_skill["ready"] is True
        assert state.last_action == "auto_create"
        assert len(operations(provider, "create")) == 1
        assert profiles.calls == [("hr", "hr", str(workspace.workspace_for("hr")))]
        assert repository.value is state


def test_existing_and_restarted_services_reuse_agent_without_creation():
    with TemporarySystemAgentWorkspace() as workspace:
        agent = existing_hr(workspace)
        first, provider, profiles, repository = build_service(workspace, agents=(agent,))
        first_state = first.reconcile(HR_ROLE)
        profiles.updated = False

        restarted = SystemAgentLifecycleService(first._ports)
        second_state = restarted.reconcile(HR_ROLE)
        assert second_state.agent_id == first_state.agent_id
        assert second_state.auto_created is False
        assert len(operations(provider, "create")) == 0
        assert len(repository.saved) == 2


def test_profile_failure_retains_created_identity_and_later_repairs_without_recreate():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, profiles, _repository = build_service(workspace)
        profiles.write_partial_before_failure = True
        profiles.fail_next(OSError("profile write failed"))
        failed = service.reconcile(HR_ROLE)
        assert failed.status is LifecycleStatus.ERROR
        assert failed.agent_id == "hr"
        assert failed.auto_created is True
        assert "profile write failed" in failed.last_error
        assert (workspace.workspace_for("hr") / HR_ROLE.required_files[0]).read_text() == "partial"

        repaired = service.reconcile(HR_ROLE)
        assert repaired.status is LifecycleStatus.IDLE
        assert repaired.agent_id == "hr"
        assert repaired.last_error == ""
        assert len(operations(provider, "create")) == 1


def test_skill_failure_is_partial_and_retry_only_repeats_configuration():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, _repository = build_service(workspace, agents=(existing_hr(workspace),))
        provider.skill_ready = False
        failed = service.reconcile(HR_ROLE)
        assert failed.status is LifecycleStatus.ERROR
        assert failed.agent_id == "hr"
        assert failed.last_error == "skill unavailable"
        assert failed.last_action == "skill_sync"

        provider.skill_ready = True
        repaired = service.reconcile(HR_ROLE)
        assert repaired.status is LifecycleStatus.IDLE
        assert len(operations(provider, "create")) == 0
        assert len(operations(provider, "sync_managed_skills")) == 2


def test_discovery_retries_provider_exception_then_succeeds():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, _repository = build_service(workspace, agents=(existing_hr(workspace),))
        provider.fail_next("discover", TimeoutError("temporary timeout"))
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.IDLE
        assert len(operations(provider, "discover")) == 2
        assert all(call[1]["force_refresh"] is True for call in operations(provider, "discover"))


def test_exhausted_discovery_timeout_degrades_and_preserves_last_identity():
    with TemporarySystemAgentWorkspace() as workspace:
        previous = SystemAgentLifecycleState.from_mapping(
            HR_ROLE,
            {"agentId": "provider-hr-7", "status": "idle", "workspace": "/known/workspace"},
            now="before",
        )
        service, provider, _profiles, repository = build_service(workspace, state=previous)
        provider.fail_next("discover", TimeoutError("timeout one"))
        provider.fail_next("discover", TimeoutError("timeout two"))
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.ERROR
        assert state.agent_id == "provider-hr-7"
        assert state.workspace == "/known/workspace"
        assert state.last_error == "timeout two"
        assert repository.value is state


def test_create_response_timeout_recovers_by_rediscovery_without_duplicate():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, _repository = build_service(workspace)
        provider.create_then_raise = True
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.IDLE
        assert state.agent_id == "hr"
        assert len(provider.agents) == 1
        assert len(operations(provider, "create")) == 1


def test_successful_create_is_not_retried_when_post_create_refresh_fails():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, _repository = build_service(workspace)
        provider.fail_refresh_after_create = True
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.IDLE
        assert state.agent_id == "hr"
        assert len(operations(provider, "create")) == 1
        assert len(provider.agents) == 1


def test_failed_create_retries_only_after_fresh_rediscovery():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, _repository = build_service(workspace)
        provider.fail_next("create", RuntimeError("gateway unavailable"))
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.IDLE
        assert len(operations(provider, "create")) == 2
        call_names = [name for name, _details in provider.calls]
        first_create = call_names.index("create")
        second_create = call_names.index("create", first_create + 1)
        assert "discover" in call_names[first_create + 1:second_create]


def test_force_refresh_ignores_stale_negative_cache_before_creation():
    with TemporarySystemAgentWorkspace() as workspace:
        agent = existing_hr(workspace)
        service, provider, _profiles, _repository = build_service(workspace, agents=(agent,))
        provider.cached_discovery = ()
        state = service.reconcile(HR_ROLE)
        assert state.agent_id == "hr"
        assert len(operations(provider, "create")) == 0
        assert operations(provider, "discover")[0][1]["force_refresh"] is True


def test_concurrent_reconciliation_across_service_instances_creates_once():
    with TemporarySystemAgentWorkspace() as workspace:
        first, provider, profiles, repository = build_service(workspace)
        second = SystemAgentLifecycleService(first._ports)
        with ThreadPoolExecutor(max_workers=8) as executor:
            states = list(executor.map(lambda service: service.reconcile(HR_ROLE), [first, second] * 10))
        assert {state.agent_id for state in states} == {"hr"}
        assert all(state.status is LifecycleStatus.IDLE for state in states)
        assert len(operations(provider, "create")) == 1
        assert len(provider.agents) == 1
        assert len(repository.saved) == 20
        assert len(profiles.calls) == 20


def test_duplicate_provider_agents_fail_closed_and_keep_canonical_identity():
    with TemporarySystemAgentWorkspace() as workspace:
        canonical = existing_hr(workspace)
        duplicate = existing_hr(workspace, "hr-copy")
        service, provider, profiles, _repository = build_service(
            workspace, agents=(canonical, duplicate),
        )
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.ERROR
        assert state.agent_id == "hr"
        assert "hr-copy" in state.last_error
        assert profiles.calls == []
        assert len(operations(provider, "create")) == 0


def test_ambiguous_noncanonical_duplicates_are_not_exposed_as_valid_owner():
    with TemporarySystemAgentWorkspace() as workspace:
        service, _provider, profiles, _repository = build_service(
            workspace,
            agents=(existing_hr(workspace, "hr-one"), existing_hr(workspace, "hr-two")),
        )
        state = service.reconcile(HR_ROLE)
        assert state.status is LifecycleStatus.ERROR
        assert state.agent_id == "hr"
        assert "ambiguous" in state.last_error
        assert profiles.calls == []
