"""Provider-neutral contracts and state model for VO system-Agent lifecycles."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

from .system_agent_profiles import ProfileSyncResult
from .system_agent_roles import SystemAgentRole


DEFAULT_ACTIVITY_LIMIT = 12
MAX_ACTIVITY_LIMIT = 100


class LifecycleStatus(str, Enum):
    MISSING = "missing"
    CREATING = "creating"
    CONFIGURING = "configuring"
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    ERROR = "error"


class ActivityStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    RUNNING = "running"
    SKIPPED = "skipped"


_STATUS_ALIASES = {
    "absent": LifecycleStatus.MISSING,
    "unavailable": LifecycleStatus.MISSING,
    "provisioning": LifecycleStatus.CREATING,
    "syncing": LifecycleStatus.CONFIGURING,
    "ready": LifecycleStatus.IDLE,
    "available": LifecycleStatus.IDLE,
    "failed": LifecycleStatus.ERROR,
    "degraded": LifecycleStatus.ERROR,
}


def normalize_lifecycle_status(value: Any, *, paused: bool = False) -> LifecycleStatus:
    if paused:
        return LifecycleStatus.PAUSED
    normalized = str(value or "").strip().lower()
    try:
        return LifecycleStatus(normalized)
    except ValueError:
        return _STATUS_ALIASES.get(normalized, LifecycleStatus.MISSING)


def _timestamp(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("system-Agent timestamps must be timezone-aware")
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    raise ValueError("system-Agent timestamps must be datetime, string, or None")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return copy.deepcopy(value)


def _mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return _freeze(value or {})


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ProviderAgent:
    id: str
    name: str
    provider_kind: str
    workspace: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("provider Agent id must not be empty")
        if not self.provider_kind.strip():
            raise ValueError("provider kind must not be empty")
        object.__setattr__(self, "raw", _mapping(self.raw))

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        default_provider_kind: str,
    ) -> "ProviderAgent":
        return cls(
            id=str(payload.get("id") or payload.get("agentId") or "").strip(),
            name=str(payload.get("name") or payload.get("id") or "").strip(),
            provider_kind=str(payload.get("providerKind") or default_provider_kind).strip(),
            workspace=str(payload.get("workspace") or "").strip(),
            raw=payload,
        )


@dataclass(frozen=True, slots=True)
class LifecycleActivity:
    id: str
    action: str
    status: ActivityStatus
    at: str
    message: str = ""
    error: str = ""
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.action.strip():
            raise ValueError("lifecycle activity id and action are required")
        object.__setattr__(self, "context", _mapping(self.context))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LifecycleActivity":
        status_value = str(value.get("status") or "ok").strip().lower()
        try:
            status = ActivityStatus(status_value)
        except ValueError:
            status = ActivityStatus.ERROR
        known = {"id", "action", "status", "at", "message", "error", "context"}
        context = dict(value.get("context") or {}) if isinstance(value.get("context"), Mapping) else {}
        context.update({key: item for key, item in value.items() if key not in known})
        return cls(
            id=str(value.get("id") or "").strip(),
            action=str(value.get("action") or "").strip(),
            status=status,
            at=_timestamp(value.get("at")),
            message=str(value.get("message") or ""),
            error=str(value.get("error") or ""),
            context=context,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "status": self.status.value,
            "at": self.at,
            "message": self.message,
            "error": self.error,
            "context": _thaw(self.context),
        }


@dataclass(frozen=True, slots=True)
class SystemAgentLifecycleState:
    role_key: str
    agent_id: str
    name: str
    emoji: str
    provider_kind: str
    status: LifecycleStatus = LifecycleStatus.MISSING
    paused: bool = False
    auto_created: bool = False
    created_at: str = ""
    updated_at: str = ""
    reconciled_at: str = ""
    workspace: str = ""
    profile_files: tuple[str, ...] = ()
    profile_version: str = ""
    profile_updated_at: str = ""
    communication_skill: Mapping[str, Any] = field(default_factory=dict)
    last_action: str = ""
    last_error: str = ""
    recent_activity: tuple[LifecycleActivity, ...] = ()

    def __post_init__(self) -> None:
        if not self.role_key.strip() or not self.agent_id.strip():
            raise ValueError("lifecycle role_key and agent_id are required")
        object.__setattr__(self, "communication_skill", _mapping(self.communication_skill))
        if self.paused and self.status is not LifecycleStatus.PAUSED:
            object.__setattr__(self, "status", LifecycleStatus.PAUSED)

    @classmethod
    def initial(cls, role: SystemAgentRole, now: datetime | str) -> "SystemAgentLifecycleState":
        return cls(
            role_key=role.role_key,
            agent_id=role.stable_id,
            name=role.display_name,
            emoji=role.emoji,
            provider_kind=role.provider_kind,
            updated_at=_timestamp(now),
        )

    @classmethod
    def from_mapping(
        cls,
        role: SystemAgentRole,
        payload: Mapping[str, Any] | None,
        *,
        now: datetime | str,
        activity_limit: int = DEFAULT_ACTIVITY_LIMIT,
    ) -> "SystemAgentLifecycleState":
        data = dict(payload or {})
        paused = bool(data.get("paused"))
        raw_activity = data.get("recentActivity", data.get("recent_activity", ()))
        activities: list[LifecycleActivity] = []
        if isinstance(raw_activity, Sequence) and not isinstance(raw_activity, (str, bytes)):
            for item in raw_activity:
                if not isinstance(item, Mapping):
                    continue
                try:
                    activities.append(LifecycleActivity.from_mapping(item))
                except ValueError:
                    continue
        limit = validate_activity_limit(activity_limit)
        return cls(
            role_key=role.role_key,
            agent_id=str(data.get("agentId") or data.get("agent_id") or role.stable_id).strip(),
            name=str(data.get("name") or role.display_name).strip(),
            emoji=str(data.get("emoji") or role.emoji).strip(),
            provider_kind=str(data.get("providerKind") or data.get("provider_kind") or role.provider_kind).strip(),
            status=normalize_lifecycle_status(data.get("status"), paused=paused),
            paused=paused,
            auto_created=bool(data.get("autoCreated", data.get("auto_created", False))),
            created_at=_timestamp(data.get("createdAt", data.get("created_at"))),
            updated_at=_timestamp(data.get("updatedAt", data.get("updated_at"))) or _timestamp(now),
            reconciled_at=_timestamp(data.get("reconciledAt", data.get("reconciled_at"))),
            workspace=str(data.get("workspace") or ""),
            profile_files=tuple(str(item) for item in data.get("profileFiles", data.get("profile_files", ())) if str(item)),
            profile_version=str(data.get("profileVersion") or data.get("profile_version") or ""),
            profile_updated_at=_timestamp(data.get("profileUpdatedAt", data.get("profile_updated_at"))),
            communication_skill=data.get("communicationSkill", data.get("communication_skill", {}))
            if isinstance(data.get("communicationSkill", data.get("communication_skill", {})), Mapping)
            else {},
            last_action=str(data.get("lastAction") or data.get("last_action") or ""),
            last_error=str(data.get("lastError") or data.get("last_error") or ""),
            recent_activity=tuple(activities[-limit:]),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "roleKey": self.role_key,
            "agentId": self.agent_id,
            "name": self.name,
            "emoji": self.emoji,
            "providerKind": self.provider_kind,
            "status": self.status.value,
            "paused": self.paused,
            "autoCreated": self.auto_created,
            "createdAt": self.created_at or None,
            "updatedAt": self.updated_at or None,
            "reconciledAt": self.reconciled_at or None,
            "workspace": self.workspace,
            "profileFiles": list(self.profile_files),
            "profileVersion": self.profile_version,
            "profileUpdatedAt": self.profile_updated_at or None,
            "communicationSkill": _thaw(self.communication_skill),
            "lastAction": self.last_action,
            "lastError": self.last_error,
            "recentActivity": [item.to_mapping() for item in self.recent_activity],
        }


def validate_activity_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ACTIVITY_LIMIT:
        raise ValueError(f"activity limit must be between 1 and {MAX_ACTIVITY_LIMIT}")
    return limit


def record_lifecycle_activity(
    state: SystemAgentLifecycleState,
    *,
    action: str,
    status: ActivityStatus | str,
    message: str = "",
    error: str = "",
    context: Mapping[str, Any] | None = None,
    clock: Callable[[], datetime],
    new_id: Callable[[], str],
    activity_limit: int = DEFAULT_ACTIVITY_LIMIT,
) -> tuple[SystemAgentLifecycleState, LifecycleActivity]:
    normalized_status = status if isinstance(status, ActivityStatus) else ActivityStatus(str(status))
    at = _timestamp(clock())
    activity = LifecycleActivity(
        id=str(new_id()).strip(),
        action=action.strip(),
        status=normalized_status,
        at=at,
        message=message,
        error=error,
        context=context or {},
    )
    limit = validate_activity_limit(activity_limit)
    updated = replace(
        state,
        updated_at=at,
        last_action=activity.action,
        last_error=error,
        recent_activity=(*state.recent_activity, activity)[-limit:],
    )
    return updated, activity


class SystemAgentProviderPort(Protocol):
    def discover(
        self,
        role: SystemAgentRole,
        *,
        force_refresh: bool = False,
    ) -> Sequence[ProviderAgent]: ...
    def create(self, role: SystemAgentRole) -> ProviderAgent: ...
    def resolve_workspace(self, agent: ProviderAgent) -> Path: ...
    def sync_managed_skills(self, agent: ProviderAgent) -> Mapping[str, Any]: ...


class SystemAgentProfilePort(Protocol):
    def synchronize(
        self,
        role: SystemAgentRole,
        agent: ProviderAgent,
        workspace: Path,
    ) -> ProfileSyncResult: ...


class SystemAgentStatePort(Protocol):
    def load(self, role: SystemAgentRole) -> SystemAgentLifecycleState | Mapping[str, Any] | None: ...
    def save(self, role: SystemAgentRole, state: SystemAgentLifecycleState) -> SystemAgentLifecycleState: ...


class SystemAgentPresencePort(Protocol):
    def set_presence(self, agent_id: str, state: str, reason: str = "") -> None: ...


@dataclass(frozen=True, slots=True)
class SystemAgentPorts:
    provider: SystemAgentProviderPort
    profiles: SystemAgentProfilePort
    state: SystemAgentStatePort
    presence: SystemAgentPresencePort
    clock: Callable[[], datetime]
    new_id: Callable[[], str]


@dataclass(frozen=True, slots=True)
class AutomaticWorkDecision:
    allowed: bool
    code: str
    reason: str
    category: str


class SystemAgentLifecycleService:
    """Idempotent provider reconciliation shared by all VO system-Agent roles."""

    _locks_guard = threading.Lock()
    _role_locks: dict[str, threading.RLock] = {}

    def __init__(
        self,
        ports: SystemAgentPorts,
        *,
        provider_retry_limit: int = 1,
        activity_limit: int = DEFAULT_ACTIVITY_LIMIT,
    ):
        if isinstance(provider_retry_limit, bool) or not isinstance(provider_retry_limit, int):
            raise ValueError("provider_retry_limit must be an integer")
        if not 0 <= provider_retry_limit <= 5:
            raise ValueError("provider_retry_limit must be between 0 and 5")
        self._ports = ports
        self._provider_retry_limit = provider_retry_limit
        self._activity_limit = validate_activity_limit(activity_limit)

    @classmethod
    def _lock_for(cls, role_key: str) -> threading.RLock:
        with cls._locks_guard:
            return cls._role_locks.setdefault(role_key, threading.RLock())

    def _load_state(self, role: SystemAgentRole) -> SystemAgentLifecycleState:
        loaded = self._ports.state.load(role)
        if isinstance(loaded, SystemAgentLifecycleState):
            if loaded.role_key != role.role_key:
                raise ValueError("state repository returned a different system-Agent role")
            loaded = loaded.to_mapping()
        if loaded is not None and not isinstance(loaded, Mapping):
            raise ValueError("state repository returned an unsupported lifecycle value")
        return SystemAgentLifecycleState.from_mapping(
            role,
            loaded,
            now=self._ports.clock(),
            activity_limit=self._activity_limit,
        )

    @staticmethod
    def _provider_agent(role: SystemAgentRole, value: Any) -> ProviderAgent:
        if isinstance(value, ProviderAgent):
            return value
        if isinstance(value, Mapping):
            return ProviderAgent.from_mapping(value, default_provider_kind=role.provider_kind)
        raise ValueError("provider returned an unsupported Agent value")

    def _discover_once(self, role: SystemAgentRole) -> tuple[ProviderAgent, ...]:
        result = self._ports.provider.discover(role, force_refresh=True)
        if result is None:
            return ()
        if isinstance(result, (ProviderAgent, Mapping)):
            values: Sequence[Any] = (result,)
        elif isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
            values = result
        else:
            raise ValueError("provider discovery must return a sequence of Agents")
        unique: dict[str, ProviderAgent] = {}
        for value in values:
            agent = self._provider_agent(role, value)
            unique.setdefault(agent.id, agent)
        return tuple(unique.values())

    def _discover_with_retries(self, role: SystemAgentRole) -> tuple[ProviderAgent, ...]:
        last_error: BaseException | None = None
        for _attempt in range(self._provider_retry_limit + 1):
            try:
                return self._discover_once(role)
            except Exception as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    @staticmethod
    def _select_agent(
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
        agents: Sequence[ProviderAgent],
    ) -> tuple[ProviderAgent | None, tuple[str, ...]]:
        if not agents:
            return None, ()
        preferred_ids = tuple(
            value for value in (state.agent_id, role.stable_id) if value
        )
        selected = next(
            (agent for preferred in preferred_ids for agent in agents if agent.id == preferred),
            agents[0] if len(agents) == 1 else None,
        )
        duplicates = tuple(agent.id for agent in agents if selected is None or agent.id != selected.id)
        return selected, duplicates

    def _create_with_recovery(
        self,
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
    ) -> tuple[ProviderAgent, bool, tuple[str, ...]]:
        last_error: BaseException | None = None
        for attempt in range(self._provider_retry_limit + 1):
            try:
                created = self._provider_agent(role, self._ports.provider.create(role))
                try:
                    refreshed = self._discover_with_retries(role)
                except Exception:
                    # A successful create response is authoritative enough to continue
                    # configuration. Retrying create after a refresh outage can duplicate
                    # a provider Agent.
                    return created, True, ()
                selected, duplicates = self._select_agent(role, state, refreshed or (created,))
                if selected is None:
                    raise RuntimeError(
                        "provider creation produced conflicting system-Agent instances: "
                        + ", ".join(duplicates)
                    )
                return selected, True, duplicates
            except Exception as exc:
                last_error = exc
                try:
                    refreshed = self._discover_with_retries(role)
                except Exception:
                    refreshed = ()
                selected, duplicates = self._select_agent(role, state, refreshed)
                if selected is not None:
                    return selected, True, duplicates
                if duplicates:
                    raise RuntimeError(
                        "provider contains ambiguous system-Agent instances: "
                        + ", ".join(duplicates)
                    ) from exc
                if attempt >= self._provider_retry_limit:
                    break
        assert last_error is not None
        raise last_error

    def _record(
        self,
        state: SystemAgentLifecycleState,
        *,
        action: str,
        status: ActivityStatus,
        message: str,
        error: str = "",
        context: Mapping[str, Any] | None = None,
    ) -> SystemAgentLifecycleState:
        updated, _activity = record_lifecycle_activity(
            state,
            action=action,
            status=status,
            message=message,
            error=error,
            context=context,
            clock=self._ports.clock,
            new_id=self._ports.new_id,
            activity_limit=self._activity_limit,
        )
        return updated

    def _save_error(
        self,
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
        *,
        action: str,
        error: BaseException | str,
        agent: ProviderAgent | None = None,
    ) -> SystemAgentLifecycleState:
        if isinstance(error, BaseException):
            message = str(error).strip() or error.__class__.__name__
        else:
            message = str(error).strip() or "unknown lifecycle error"
        if agent is not None:
            state = replace(
                state,
                agent_id=agent.id,
                provider_kind=agent.provider_kind,
                workspace=agent.workspace or state.workspace,
            )
        state = replace(state, status=LifecycleStatus.ERROR, last_error=message)
        state = self._record(
            state,
            action=action,
            status=ActivityStatus.ERROR,
            message=f"System Agent {action} failed",
            error=message,
        )
        return self._ports.state.save(role, state)

    def reconcile(self, role: SystemAgentRole) -> SystemAgentLifecycleState:
        with self._lock_for(role.role_key):
            state = self._load_state(role)
            try:
                discovered = self._discover_with_retries(role)
            except Exception as exc:
                return self._save_error(role, state, action="discover", error=exc)

            agent, duplicates = self._select_agent(role, state, discovered)
            created_now = False
            if agent is None and duplicates:
                return self._save_error(
                    role,
                    state,
                    action="discover",
                    error="ambiguous provider Agents: " + ", ".join(duplicates),
                )
            if agent is None:
                try:
                    agent, created_now, duplicates = self._create_with_recovery(role, state)
                except Exception as exc:
                    return self._save_error(role, state, action="create", error=exc)
            if duplicates:
                return self._save_error(
                    role,
                    state,
                    action="duplicate_detected",
                    error="duplicate provider Agents: " + ", ".join(duplicates),
                    agent=agent,
                )

            now = _timestamp(self._ports.clock())
            state = replace(
                state,
                agent_id=agent.id,
                name=role.display_name,
                emoji=role.emoji,
                provider_kind=agent.provider_kind,
                status=LifecycleStatus.CONFIGURING,
                auto_created=state.auto_created or created_now,
                created_at=state.created_at or (now if created_now else ""),
                reconciled_at=now,
                last_error="",
            )
            try:
                workspace = self._ports.provider.resolve_workspace(agent)
                profile = self._ports.profiles.synchronize(role, agent, workspace)
            except Exception as exc:
                return self._save_error(role, state, action="profile_sync", error=exc, agent=agent)
            try:
                skill = self._ports.provider.sync_managed_skills(agent)
                if not isinstance(skill, Mapping) or skill.get("ready") is not True:
                    detail = skill.get("status") if isinstance(skill, Mapping) else "invalid skill result"
                    raise RuntimeError(str(detail or "managed communication skill is not ready"))
            except Exception as exc:
                return self._save_error(role, state, action="skill_sync", error=exc, agent=agent)

            finished_at = _timestamp(self._ports.clock())
            state = replace(
                state,
                workspace=str(profile.workspace or workspace),
                profile_files=tuple(dict.fromkeys((
                    *role.required_files,
                    *profile.written_files,
                    *profile.unchanged_files,
                ))),
                profile_version=profile.version,
                profile_updated_at=finished_at if profile.updated else state.profile_updated_at,
                communication_skill=skill,
                status=LifecycleStatus.PAUSED if state.paused else LifecycleStatus.IDLE,
                reconciled_at=finished_at,
                last_error="",
            )
            action = "auto_create" if created_now else ("profile_update" if profile.updated else "reconcile")
            state = self._record(
                state,
                action=action,
                status=ActivityStatus.OK,
                message="System Agent lifecycle is ready",
                context={"profileVersion": profile.version, "profileUpdated": profile.updated},
            )
            return self._ports.state.save(role, state)

    def pause(self, role: SystemAgentRole) -> SystemAgentLifecycleState:
        with self._lock_for(role.role_key):
            state = self.reconcile(role)
            prior_error = state.last_error
            state = replace(state, paused=True, status=LifecycleStatus.PAUSED)
            state = self._record(
                state,
                action="pause",
                status=ActivityStatus.OK,
                message="System Agent automatic work is paused",
            )
            if prior_error:
                state = replace(state, last_error=prior_error)
            try:
                self._ports.presence.set_presence(
                    state.agent_id,
                    "break",
                    "System Agent paused by human control",
                )
            except Exception as exc:
                return self._save_error(
                    role,
                    state,
                    action="presence",
                    error=exc,
                )
            return self._ports.state.save(role, state)

    def resume(self, role: SystemAgentRole) -> SystemAgentLifecycleState:
        with self._lock_for(role.role_key):
            state = self._load_state(role)
            state = replace(
                state,
                paused=False,
                status=LifecycleStatus.MISSING,
                last_error="",
            )
            state = self._record(
                state,
                action="resume",
                status=ActivityStatus.RUNNING,
                message="System Agent resume reconciliation started",
            )
            self._ports.state.save(role, state)
            state = self.reconcile(role)
            if state.status is not LifecycleStatus.IDLE:
                return state
            try:
                self._ports.presence.set_presence(state.agent_id, "idle", "")
            except Exception as exc:
                return self._save_error(
                    role,
                    state,
                    action="presence",
                    error=exc,
                )
            state = self._record(
                state,
                action="resume",
                status=ActivityStatus.OK,
                message="System Agent resumed",
            )
            return self._ports.state.save(role, state)

    @staticmethod
    def automatic_work_decision(
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
        category: str,
    ) -> AutomaticWorkDecision:
        normalized = str(category or "").strip()
        if normalized not in role.automatic_work_categories:
            return AutomaticWorkDecision(
                False,
                "unsupported_work_category",
                "The work category is not owned by this system-Agent role",
                normalized,
            )
        if state.paused or state.status is LifecycleStatus.PAUSED:
            return AutomaticWorkDecision(
                False,
                "system_agent_paused",
                "The system Agent is paused by human control",
                normalized,
            )
        if state.status is not LifecycleStatus.IDLE:
            return AutomaticWorkDecision(
                False,
                "system_agent_unavailable",
                f"The system Agent lifecycle is {state.status.value}",
                normalized,
            )
        return AutomaticWorkDecision(True, "allowed", "Automatic work is allowed", normalized)

    def check_automatic_work(
        self,
        role: SystemAgentRole,
        category: str,
        *,
        record_skip: bool = True,
    ) -> AutomaticWorkDecision:
        with self._lock_for(role.role_key):
            state = self._load_state(role)
            decision = self.automatic_work_decision(role, state, category)
            if decision.allowed or not record_skip:
                return decision
            prior_error = state.last_error
            state = self._record(
                state,
                action="automatic_work_skipped",
                status=ActivityStatus.SKIPPED,
                message=decision.reason,
                context={"category": decision.category, "code": decision.code},
            )
            if prior_error:
                state = replace(state, last_error=prior_error)
            self._ports.state.save(role, state)
            return decision

    @staticmethod
    def _candidate_identities(candidate: Any) -> tuple[str, ...]:
        if isinstance(candidate, Mapping):
            return tuple(
                value
                for key in ("id", "agentId", "agent_id", "statusKey", "name")
                if (value := str(candidate.get(key) or "").strip())
            )
        value = str(candidate or "").strip()
        return (value,) if value else ()

    def metadata(self, role: SystemAgentRole, candidate: Any) -> dict[str, Any]:
        state = self._load_state(role)
        explicit_role = ""
        if isinstance(candidate, Mapping):
            explicit_role = str(
                candidate.get("systemRole") or candidate.get("system_role") or ""
            ).strip()
        identities = self._candidate_identities(candidate)
        if explicit_role != role.role_key and not any(
            role.matches_identity(value, state.agent_id, state.name)
            for value in identities
        ):
            return {}
        return {
            "systemRole": role.role_key,
            "systemAgent": True,
            "assignable": role.assignable,
            "deletable": role.deletable,
            "meetingEligible": role.meeting_eligible,
            "lifecycleStatus": state.status.value,
            "paused": state.paused,
        }

    @staticmethod
    def _public_projection(
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
    ) -> dict[str, Any]:
        return {
            "role": role.role_key,
            "agentId": state.agent_id,
            "name": state.name,
            "emoji": state.emoji,
            "providerKind": state.provider_kind,
            "status": state.status.value,
            "paused": state.paused,
            "autoCreated": state.auto_created,
            "createdAt": state.created_at or None,
            "updatedAt": state.updated_at or None,
            "reconciledAt": state.reconciled_at or None,
            "profileVersion": state.profile_version,
            "profileUpdatedAt": state.profile_updated_at or None,
            "communicationSkill": _thaw(state.communication_skill),
            "lastAction": state.last_action,
            "lastError": state.last_error,
            "recentActivity": [item.to_mapping() for item in state.recent_activity],
        }

    def public_state(
        self,
        role: SystemAgentRole,
        *,
        ensure: bool = False,
    ) -> dict[str, Any]:
        state = self.reconcile(role) if ensure else self._load_state(role)
        return self._public_projection(role, state)
