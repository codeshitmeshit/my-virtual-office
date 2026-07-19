"""Human Resources adapter for the shared VO system-Agent lifecycle."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .system_agent_lifecycle import (
    LifecycleStatus,
    ProviderAgent,
    SystemAgentLifecycleService,
    SystemAgentLifecycleState,
)
from .system_agent_profiles import (
    ProfileSyncResult,
    RenderedSystemAgentProfile,
    UnsafeProfilePathError,
    extract_template_version,
    load_and_render_profile,
    resolve_safe_workspace,
    sync_profile_files,
)
from .system_agent_roles import HR_ROLE, SystemAgentRole


HR_ACTIVITY_LIMIT = 60
HR_PUBLIC_ACTIVITY_LIMIT = 12


def hr_label(state: SystemAgentLifecycleState) -> str:
    if state.paused or state.status is LifecycleStatus.PAUSED:
        return "已暂停"
    if state.status is LifecycleStatus.MISSING:
        return "未接入"
    if state.status is LifecycleStatus.CREATING:
        return "创建中"
    if state.status is LifecycleStatus.CONFIGURING:
        return "配置中"
    if state.status is LifecycleStatus.ERROR:
        if state.last_action == "profile_sync":
            return "HR Profile 配置失败"
        if state.last_action == "skill_sync":
            return "HR 通信技能未就绪"
        if state.last_action == "duplicate_detected":
            return "HR 身份冲突"
        return "HR 接入失败"
    return "已自动创建" if state.auto_created else "已接入"


class HRStateRepository:
    """Atomic ``human-resources/hr.json`` lifecycle-state authority."""

    def __init__(
        self,
        status_dir: str | os.PathLike[str],
        *,
        clock: Callable[[], Any],
    ):
        self.hr_dir = Path(status_dir).absolute() / "human-resources"
        self.path = self.hr_dir / "hr.json"
        self._clock = clock

    def load(self, role: SystemAgentRole = HR_ROLE) -> SystemAgentLifecycleState:
        if role.role_key != HR_ROLE.role_key:
            raise ValueError("HRStateRepository only accepts hr")
        payload: Mapping[str, Any] | None = None
        try:
            if self.path.is_symlink():
                raise UnsafeProfilePathError("HR lifecycle state must not be a symbolic link")
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, Mapping):
                payload = loaded
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload = None
        return SystemAgentLifecycleState.from_mapping(
            role,
            payload,
            now=self._clock(),
            activity_limit=HR_ACTIVITY_LIMIT,
        )

    def _write(self, payload: Mapping[str, Any]) -> None:
        if self.hr_dir.is_symlink() or self.path.is_symlink():
            raise UnsafeProfilePathError("HR lifecycle state path must not be a symbolic link")
        self.hr_dir.mkdir(parents=True, exist_ok=True)
        descriptor = -1
        temporary = ""
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".hr.", suffix=".tmp", dir=self.hr_dir,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                descriptor = -1
                json.dump(dict(payload), output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o666, follow_symlinks=False)
            if self.path.is_symlink():
                raise UnsafeProfilePathError("HR lifecycle state target became a symbolic link")
            os.replace(temporary, self.path)
            temporary = ""
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def save(
        self,
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
    ) -> SystemAgentLifecycleState:
        if role.role_key != HR_ROLE.role_key or state.role_key != HR_ROLE.role_key:
            raise ValueError("HR lifecycle state role mismatch")
        payload = state.to_mapping()
        payload["label"] = hr_label(state)
        payload["recentActivity"] = payload["recentActivity"][-HR_ACTIVITY_LIMIT:]
        self._write(payload)
        return state

    def public_state(self) -> dict[str, Any]:
        state = self.load()
        return hr_public_state(state)


class HRProfilePort:
    """Render and safely synchronize the HR OpenClaw Profile."""

    def __init__(
        self,
        template_path: str | os.PathLike[str],
        openclaw_home: str | os.PathLike[str],
    ):
        self.template_path = Path(template_path).absolute()
        self.openclaw_home = Path(openclaw_home).resolve(strict=False)

    def render(self) -> RenderedSystemAgentProfile:
        if self.template_path.is_symlink():
            raise UnsafeProfilePathError("HR profile template must not be a symbolic link")
        try:
            template = self.template_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"HR Profile template cannot be read: {exc}") from exc
        version = extract_template_version(template, HR_ROLE.version_marker)
        return load_and_render_profile(
            self.template_path,
            HR_ROLE,
            tokens={
                "HR_NAME": HR_ROLE.display_name,
                "HR_EMOJI": HR_ROLE.emoji,
                "HR_AGENT_ID": HR_ROLE.stable_id,
                "HR_PROFILE_VERSION": version,
            },
        )

    def workspace_for(
        self,
        agent_id: str,
        configured_workspace: str | os.PathLike[str] | None = None,
    ) -> Path:
        return resolve_safe_workspace(self.openclaw_home, agent_id, configured_workspace)

    def synchronize(
        self,
        role: SystemAgentRole,
        agent: ProviderAgent,
        workspace: Path,
    ) -> ProfileSyncResult:
        if role.role_key != HR_ROLE.role_key:
            raise ValueError("HRProfilePort only accepts hr")
        safe_workspace = self.workspace_for(agent.id, workspace)
        return sync_profile_files(
            self.openclaw_home,
            safe_workspace,
            self.render(),
            version_marker=role.version_marker,
        )


class HRProviderPort:
    """OpenClaw-shaped HR provider port with injected runtime callbacks."""

    def __init__(
        self,
        *,
        list_agents: Callable[[bool], list[Mapping[str, Any]]],
        create_agent: Callable[[Mapping[str, Any], int], Mapping[str, Any]],
        profile_port: HRProfilePort,
        sync_managed_skills: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        default_model: Callable[[], str] = lambda: "",
    ):
        self._list_agents = list_agents
        self._create_agent = create_agent
        self._profile_port = profile_port
        self._sync_managed_skills = sync_managed_skills
        self._default_model = default_model

    @staticmethod
    def _matches(role: SystemAgentRole, candidate: Mapping[str, Any]) -> bool:
        return any(
            role.matches_identity(candidate.get(key))
            for key in ("id", "statusKey", "name")
        )

    def discover(
        self,
        role: SystemAgentRole,
        *,
        force_refresh: bool = False,
    ) -> tuple[ProviderAgent, ...]:
        if role.role_key != HR_ROLE.role_key:
            raise ValueError("HRProviderPort only accepts hr")
        return tuple(
            ProviderAgent.from_mapping(agent, default_provider_kind=role.provider_kind)
            for agent in self._list_agents(force_refresh)
            if isinstance(agent, Mapping) and self._matches(role, agent)
        )

    def create(self, role: SystemAgentRole) -> ProviderAgent:
        if role.role_key != HR_ROLE.role_key:
            raise ValueError("HRProviderPort only accepts hr")
        workspace = self._profile_port.workspace_for(role.stable_id)
        params: dict[str, Any] = {
            "name": role.stable_id,
            "workspace": str(workspace),
            "emoji": role.emoji,
        }
        if model := str(self._default_model() or "").strip():
            params["model"] = model
        result = self._create_agent(params, 30)
        if not isinstance(result, Mapping) or not result.get("ok"):
            detail = result.get("error") if isinstance(result, Mapping) else "invalid provider response"
            raise RuntimeError(str(detail or "OpenClaw HR creation failed"))
        agent_id = str(result.get("agentId") or role.stable_id).strip()
        return ProviderAgent(
            id=agent_id,
            name=role.display_name,
            provider_kind=role.provider_kind,
            workspace=str(workspace),
            raw={**dict(result), "statusKey": agent_id, "workspace": str(workspace)},
        )

    def resolve_workspace(self, agent: ProviderAgent) -> Path:
        configured = Path(agent.workspace).resolve(strict=False) if agent.workspace else None
        return self._profile_port.workspace_for(agent.id, configured)

    def sync_managed_skills(self, agent: ProviderAgent) -> Mapping[str, Any]:
        payload = {
            **dict(agent.raw),
            "id": agent.id,
            "statusKey": agent.id,
            "providerKind": agent.provider_kind,
            "workspace": agent.workspace,
        }
        result = self._sync_managed_skills(payload)
        return result if isinstance(result, Mapping) else {
            "ready": False,
            "status": "invalid managed-skill response",
        }


def hr_public_state(state: SystemAgentLifecycleState) -> dict[str, Any]:
    mapping = state.to_mapping()
    return {
        "agentId": state.agent_id,
        "name": state.name,
        "emoji": state.emoji,
        "providerKind": state.provider_kind,
        "status": state.status.value,
        "label": hr_label(state),
        "paused": state.paused,
        "autoCreated": state.auto_created,
        "createdAt": state.created_at or None,
        "updatedAt": state.updated_at or None,
        "profileVersion": state.profile_version,
        "profileUpdatedAt": state.profile_updated_at or None,
        "communicationSkill": mapping["communicationSkill"] or None,
        "lastAction": state.last_action,
        "lastError": state.last_error,
        "recentActivity": mapping["recentActivity"][-HR_PUBLIC_ACTIVITY_LIMIT:],
    }


class HRLifecycleAdapter:
    """HR-domain facade over ``SystemAgentLifecycleService``."""

    def __init__(
        self,
        lifecycle: SystemAgentLifecycleService,
        repository: HRStateRepository,
    ):
        self.lifecycle = lifecycle
        self.repository = repository

    def reconcile(self) -> SystemAgentLifecycleState:
        return self.lifecycle.reconcile(HR_ROLE)

    def pause(self) -> SystemAgentLifecycleState:
        return self.lifecycle.pause(HR_ROLE)

    def resume(self) -> SystemAgentLifecycleState:
        return self.lifecycle.resume(HR_ROLE)

    def public_state(self, *, ensure: bool = True) -> dict[str, Any]:
        state = self.reconcile() if ensure else self.repository.load()
        return hr_public_state(state)

    def is_hr(self, candidate: Any) -> bool:
        state = self.repository.load()
        if isinstance(candidate, Mapping):
            values = tuple(
                value
                for key in ("id", "agentId", "agent_id", "statusKey", "name")
                if (value := str(candidate.get(key) or "").strip())
            )
            if str(candidate.get("systemRole") or candidate.get("system_role") or "").strip() == HR_ROLE.role_key:
                return True
        else:
            value = str(candidate or "").strip()
            values = (value,) if value else ()
        return any(
            HR_ROLE.matches_identity(value, state.agent_id, state.name)
            for value in values
        )

    def update(self, action: str) -> SystemAgentLifecycleState:
        normalized = str(action or "").strip().lower()
        if normalized == "pause":
            return self.pause()
        if normalized == "resume":
            return self.resume()
        raise ValueError("HR lifecycle action must be pause or resume")
