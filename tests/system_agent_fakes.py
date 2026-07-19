"""Reusable deterministic test doubles for VO system-Agent services.

The helpers deliberately depend only on the Python standard library.  Unit tests
can therefore exercise lifecycle orchestration without importing ``server`` or
requiring an OpenClaw installation.
"""

from __future__ import annotations

import copy
import shutil
import tempfile
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _role_id(role: object) -> str:
    value = _field(role, "stable_id") or _field(role, "id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("system-Agent role must have a non-empty stable_id")
    return value.strip()


def _agent_id(agent: object) -> str:
    value = _field(agent, "id") or _field(agent, "agent_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("system Agent must have a non-empty id")
    return value.strip()


@dataclass(frozen=True)
class RecordedSystemAgentCall:
    operation: str
    arguments: dict[str, Any]


class FakeClock:
    """Callable, timezone-aware clock whose value advances only when requested."""

    def __init__(self, current: datetime | None = None):
        self._lock = threading.Lock()
        self._current = current or datetime(2026, 1, 1, tzinfo=timezone.utc)
        if self._current.tzinfo is None or self._current.utcoffset() is None:
            raise ValueError("FakeClock requires a timezone-aware datetime")

    def __call__(self) -> datetime:
        with self._lock:
            return self._current

    def advance(self, delta: timedelta = timedelta(), **parts: float) -> datetime:
        step = delta + timedelta(**parts)
        with self._lock:
            self._current += step
            return self._current


class SequenceIdProvider:
    """Thread-safe deterministic ID provider suitable for injection as ``new_id``."""

    def __init__(self, prefix: str = "test", start: int = 1):
        if not prefix:
            raise ValueError("ID prefix must not be empty")
        self._prefix = prefix
        self._next = start
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            value = self._next
            self._next += 1
        return f"{self._prefix}-{value}"


class TemporarySystemAgentWorkspace:
    """Builds isolated status, OpenClaw, and per-Agent workspace directories."""

    def __init__(self, prefix: str = "vo-system-agent-test-"):
        self._prefix = prefix
        self._root: Path | None = None

    def __enter__(self) -> "TemporarySystemAgentWorkspace":
        self._root = Path(tempfile.mkdtemp(prefix=self._prefix))
        self.status_dir.mkdir()
        self.openclaw_home.mkdir()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self._root is not None:
            shutil.rmtree(self._root)
            self._root = None

    @property
    def root(self) -> Path:
        if self._root is None:
            raise RuntimeError("temporary workspace is not active")
        return self._root

    @property
    def status_dir(self) -> Path:
        return self.root / "status"

    @property
    def openclaw_home(self) -> Path:
        return self.root / "openclaw"

    def workspace_for(self, agent_id: str) -> Path:
        if not agent_id or Path(agent_id).name != agent_id:
            raise ValueError("agent_id must be one safe path segment")
        workspace = self.openclaw_home / f"workspace-{agent_id}"
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace


class FakeSystemAgentPorts:
    """Thread-safe in-memory implementation of the planned lifecycle ports."""

    def __init__(
        self,
        workspace: TemporarySystemAgentWorkspace,
        *,
        agents: Iterable[Mapping[str, Any]] = (),
        clock: FakeClock | None = None,
        ids: SequenceIdProvider | None = None,
    ):
        self.workspace = workspace
        self.clock = clock or FakeClock()
        self.new_id = ids or SequenceIdProvider("event")
        self.calls: list[RecordedSystemAgentCall] = []
        self.agents = {_agent_id(agent): copy.deepcopy(dict(agent)) for agent in agents}
        self.states: dict[str, dict[str, Any]] = {}
        self.presence: dict[str, str] = {}
        self.synced_agents: set[str] = set()
        self._failures: dict[str, deque[BaseException]] = defaultdict(deque)
        self._hooks: dict[str, Callable[[RecordedSystemAgentCall], None]] = {}
        self._lock = threading.RLock()

    def fail_next(self, operation: str, error: BaseException) -> None:
        with self._lock:
            self._failures[operation].append(error)

    def set_hook(
        self,
        operation: str,
        hook: Callable[[RecordedSystemAgentCall], None] | None,
    ) -> None:
        with self._lock:
            if hook is None:
                self._hooks.pop(operation, None)
            else:
                self._hooks[operation] = hook

    def _record(self, operation: str, **arguments: Any) -> None:
        with self._lock:
            call = RecordedSystemAgentCall(operation, copy.deepcopy(arguments))
            self.calls.append(call)
            failure = self._failures[operation].popleft() if self._failures[operation] else None
            hook = self._hooks.get(operation)
        if hook is not None:
            hook(call)
        if failure is not None:
            raise failure

    def discover(self, role: object) -> dict[str, Any] | None:
        role_id = _role_id(role)
        self._record("discover", role_id=role_id)
        with self._lock:
            agent = self.agents.get(role_id)
            return copy.deepcopy(agent) if agent is not None else None

    def create(self, role: object) -> dict[str, Any]:
        role_id = _role_id(role)
        workspace = self.workspace.workspace_for(role_id)
        self._record("create", role_id=role_id, workspace=str(workspace))
        with self._lock:
            agent = self.agents.setdefault(
                role_id,
                {
                    "id": role_id,
                    "name": _field(role, "display_name", role_id),
                    "workspace": str(workspace),
                },
            )
            return copy.deepcopy(agent)

    def resolve_workspace(self, agent: object) -> Path:
        agent_id = _agent_id(agent)
        self._record("resolve_workspace", agent_id=agent_id)
        configured = _field(agent, "workspace")
        if configured:
            return Path(configured)
        return self.workspace.workspace_for(agent_id)

    def sync_managed_skills(self, agent: object) -> None:
        agent_id = _agent_id(agent)
        self._record("sync_managed_skills", agent_id=agent_id)
        with self._lock:
            self.synced_agents.add(agent_id)

    def load_state(self, role: object) -> dict[str, Any]:
        role_id = _role_id(role)
        self._record("load_state", role_id=role_id)
        with self._lock:
            return copy.deepcopy(self.states.get(role_id, {}))

    def save_state(self, role: object, state: Mapping[str, Any]) -> None:
        role_id = _role_id(role)
        snapshot = copy.deepcopy(dict(state))
        self._record("save_state", role_id=role_id, state=snapshot)
        with self._lock:
            self.states[role_id] = snapshot

    def set_presence(self, agent: object, state: str) -> None:
        agent_id = _agent_id(agent)
        self._record("set_presence", agent_id=agent_id, state=state)
        with self._lock:
            self.presence[agent_id] = state


def assert_provider_calls(
    ports: FakeSystemAgentPorts,
    expected_operations: Iterable[str],
) -> None:
    actual = [call.operation for call in ports.calls]
    expected = list(expected_operations)
    assert actual == expected, f"provider calls differ: expected {expected!r}, got {actual!r}"


def assert_provider_call(
    ports: FakeSystemAgentPorts,
    operation: str,
    *,
    occurrence: int = 0,
    **argument_subset: Any,
) -> RecordedSystemAgentCall:
    matches = [call for call in ports.calls if call.operation == operation]
    assert len(matches) > occurrence, (
        f"provider call {operation!r} occurrence {occurrence} missing; "
        f"recorded {[call.operation for call in ports.calls]!r}"
    )
    call = matches[occurrence]
    for key, expected in argument_subset.items():
        assert call.arguments.get(key) == expected, (
            f"provider call {operation!r} argument {key!r}: "
            f"expected {expected!r}, got {call.arguments.get(key)!r}"
        )
    return call
