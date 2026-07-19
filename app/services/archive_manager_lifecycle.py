"""Archive Room compatibility adapter for the shared system-Agent lifecycle."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .system_agent_lifecycle import (
    CallbackPresencePort,
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
from .system_agent_roles import ARCHIVE_MANAGER_ROLE, SystemAgentRole


ARCHIVE_MANAGER_PHASE = "phase-4"
ARCHIVE_MANAGER_ACTIVITY_LIMIT = 60
ARCHIVE_MANAGER_PUBLIC_ACTIVITY_LIMIT = 12


def archive_manager_label(state: SystemAgentLifecycleState) -> str:
    if state.paused or state.status is LifecycleStatus.PAUSED:
        return "已暂停"
    if state.status is LifecycleStatus.MISSING:
        return "未接入"
    if state.status is LifecycleStatus.ERROR:
        if state.last_action == "profile_sync":
            if state.auto_created and not state.profile_version:
                return "档案管理员创建失败"
            return "档案管理员配置失败"
        if state.last_action == "skill_sync":
            if state.auto_created and not state.communication_skill:
                return "档案管理员创建后通信技能未就绪"
            return "档案管理员通信技能未就绪"
        return "档案管理员创建失败"
    return "已自动创建" if state.auto_created else "已接入"


def archive_manager_legacy_action(state: SystemAgentLifecycleState, action: str) -> str:
    if action in {"create", "discover"}:
        return "auto_create"
    if action == "profile_sync":
        return "auto_create" if state.auto_created and not state.profile_version else "profile_repair"
    if action == "skill_sync" and state.auto_created and not state.communication_skill:
        return "auto_create"
    return action


def _legacy_activity(state: SystemAgentLifecycleState) -> list[dict[str, Any]]:
    result = []
    for activity in state.recent_activity[-ARCHIVE_MANAGER_ACTIVITY_LIMIT:]:
        item = activity.to_mapping()
        item["action"] = archive_manager_legacy_action(state, item["action"])
        context = item.pop("context", {})
        if isinstance(context, Mapping):
            item.update(context)
        result.append(item)
    return result


class ArchiveManagerStateRepository:
    """Atomic adapter for the existing ``archive-room/manager.json`` authority."""

    def __init__(
        self,
        status_dir: str | os.PathLike[str],
        *,
        clock: Callable[[], Any],
    ):
        self.archive_room_dir = Path(status_dir).absolute() / "archive-room"
        self.path = self.archive_room_dir / "manager.json"
        self._clock = clock

    def _default_legacy(self) -> dict[str, Any]:
        now = self._clock()
        updated_at = now.isoformat() if hasattr(now, "isoformat") else str(now or "")
        return {
            "agentId": ARCHIVE_MANAGER_ROLE.stable_id,
            "name": ARCHIVE_MANAGER_ROLE.display_name,
            "emoji": ARCHIVE_MANAGER_ROLE.emoji,
            "providerKind": ARCHIVE_MANAGER_ROLE.provider_kind,
            "status": "missing",
            "label": "未接入",
            "phase": ARCHIVE_MANAGER_PHASE,
            "paused": False,
            "autoCreated": False,
            "createdAt": None,
            "updatedAt": updated_at,
            "lastAction": "",
            "lastError": "",
            "recentActivity": [],
        }

    def load_legacy(self) -> dict[str, Any]:
        data: Mapping[str, Any] = {}
        try:
            if self.path.is_symlink():
                raise UnsafeProfilePathError("archive manager state must not be a symbolic link")
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, Mapping):
                data = loaded
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError, json.JSONDecodeError):
            data = {}
        state = self._default_legacy()
        allowed = set(state) | {
            "workspace", "profileFiles", "profileVersion", "profileUpdatedAt",
            "reconciledAt", "communicationSkill",
        }
        state.update({key: value for key, value in data.items() if key in allowed})
        if not isinstance(state.get("recentActivity"), list):
            state["recentActivity"] = []
        state["recentActivity"] = state["recentActivity"][-ARCHIVE_MANAGER_ACTIVITY_LIMIT:]
        return state

    def load(self, role: SystemAgentRole = ARCHIVE_MANAGER_ROLE) -> SystemAgentLifecycleState:
        if role.role_key != ARCHIVE_MANAGER_ROLE.role_key:
            raise ValueError("ArchiveManagerStateRepository only accepts archive_manager")
        return SystemAgentLifecycleState.from_mapping(
            role,
            self.load_legacy(),
            now=self._clock(),
            activity_limit=ARCHIVE_MANAGER_ACTIVITY_LIMIT,
        )

    def legacy_mapping(self, state: SystemAgentLifecycleState) -> dict[str, Any]:
        return {
            "agentId": state.agent_id,
            "name": state.name,
            "emoji": state.emoji,
            "providerKind": state.provider_kind,
            "status": state.status.value,
            "label": archive_manager_label(state),
            "phase": ARCHIVE_MANAGER_PHASE,
            "paused": state.paused,
            "autoCreated": state.auto_created,
            "createdAt": state.created_at or None,
            "updatedAt": state.updated_at or None,
            "lastAction": archive_manager_legacy_action(state, state.last_action),
            "lastError": state.last_error,
            "recentActivity": _legacy_activity(state),
            **({"workspace": state.workspace} if state.workspace else {}),
            **({"profileFiles": list(state.profile_files)} if state.profile_files else {}),
            **({"profileVersion": state.profile_version} if state.profile_version else {}),
            **({"profileUpdatedAt": state.profile_updated_at} if state.profile_updated_at else {}),
            **({"reconciledAt": state.reconciled_at} if state.reconciled_at else {}),
            **({"communicationSkill": state.to_mapping()["communicationSkill"]} if state.communication_skill else {}),
        }

    def _write_payload(self, payload: Mapping[str, Any]) -> None:
        if self.archive_room_dir.is_symlink() or self.path.is_symlink():
            raise UnsafeProfilePathError("archive manager state path must not be a symbolic link")
        self.archive_room_dir.mkdir(parents=True, exist_ok=True)
        descriptor = -1
        temporary = ""
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".manager.", suffix=".tmp", dir=self.archive_room_dir,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                descriptor = -1
                json.dump(dict(payload), output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o666, follow_symlinks=False)
            if self.path.is_symlink():
                raise UnsafeProfilePathError("archive manager state target became a symbolic link")
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
        if role.role_key != ARCHIVE_MANAGER_ROLE.role_key or state.role_key != role.role_key:
            raise ValueError("archive manager state role mismatch")
        self._write_payload(self.legacy_mapping(state))
        return state

    def save_legacy(self, state: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._default_legacy()
        allowed = set(payload) | {
            "workspace", "profileFiles", "profileVersion", "profileUpdatedAt",
            "reconciledAt", "communicationSkill",
        }
        payload.update({key: value for key, value in state.items() if key in allowed})
        activity = payload.get("recentActivity")
        payload["recentActivity"] = (
            activity[-ARCHIVE_MANAGER_ACTIVITY_LIMIT:] if isinstance(activity, list) else []
        )
        if not payload.get("updatedAt"):
            payload["updatedAt"] = self._default_legacy()["updatedAt"]
        self._write_payload(payload)
        return payload


class ArchiveManagerProfilePort:
    """Renders the legacy template through the generic safe Profile engine."""

    def __init__(
        self,
        template_path: str | os.PathLike[str],
        openclaw_home: str | os.PathLike[str],
        *,
        compatibility_sync: Callable[[str], Mapping[str, Any]] | None = None,
    ):
        self.template_path = Path(template_path).absolute()
        self.openclaw_home = Path(openclaw_home).resolve(strict=False)
        self._compatibility_sync = compatibility_sync

    @property
    def uses_compatibility_sync(self) -> bool:
        return self._compatibility_sync is not None

    def render(self) -> RenderedSystemAgentProfile:
        if self.template_path.is_symlink():
            raise UnsafeProfilePathError("archive manager profile template must not be a symbolic link")
        version = extract_template_version(
            self.template_path.read_text(encoding="utf-8"),
            ARCHIVE_MANAGER_ROLE.version_marker,
        )
        return load_and_render_profile(
            self.template_path,
            ARCHIVE_MANAGER_ROLE,
            tokens={
                "ARCHIVE_MANAGER_NAME": ARCHIVE_MANAGER_ROLE.display_name,
                "ARCHIVE_MANAGER_EMOJI": ARCHIVE_MANAGER_ROLE.emoji,
                "ARCHIVE_MANAGER_AGENT_ID": ARCHIVE_MANAGER_ROLE.stable_id,
                "ARCHIVE_MANAGER_PROFILE_VERSION": version,
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
        if role.role_key != ARCHIVE_MANAGER_ROLE.role_key:
            raise ValueError("ArchiveManagerProfilePort only accepts archive_manager")
        if self._compatibility_sync is not None:
            result = self._compatibility_sync(agent.id)
            if not isinstance(result, Mapping) or not result.get("ok"):
                detail = result.get("error") if isinstance(result, Mapping) else "invalid Profile result"
                raise RuntimeError(str(detail or "Archive manager Profile synchronization failed"))
            files = tuple(str(item) for item in result.get("profileFiles", ()) if str(item))
            updated = bool(result.get("updated"))
            return ProfileSyncResult(
                workspace=str(result.get("workspace") or workspace),
                version=str(result.get("profileVersion") or ""),
                updated=updated,
                written_files=files if updated else (),
                unchanged_files=() if updated else files,
            )
        safe_workspace = self.workspace_for(agent.id, workspace)
        return sync_profile_files(
            self.openclaw_home,
            safe_workspace,
            self.render(),
            version_marker=role.version_marker,
        )

    def synchronize_legacy(
        self,
        agent_id: str,
        configured_workspace: str | os.PathLike[str] | None = None,
    ) -> dict[str, Any]:
        try:
            effective_id = agent_id or ARCHIVE_MANAGER_ROLE.stable_id
            workspace = self.workspace_for(effective_id, configured_workspace)
            agent = ProviderAgent(
                id=effective_id,
                name=ARCHIVE_MANAGER_ROLE.display_name,
                provider_kind=ARCHIVE_MANAGER_ROLE.provider_kind,
                workspace=str(workspace),
            )
            result = self.synchronize(ARCHIVE_MANAGER_ROLE, agent, workspace)
            return {
                "ok": True,
                "profileFiles": list(ARCHIVE_MANAGER_ROLE.required_files),
                "workspace": result.workspace,
                "profileVersion": result.version,
                "updated": result.updated,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class ArchiveManagerProviderPort:
    """OpenClaw-shaped provider adapter with all runtime callbacks injected."""

    def __init__(
        self,
        *,
        list_agents: Callable[[bool], list[Mapping[str, Any]]],
        create_agent: Callable[[Mapping[str, Any], int], Mapping[str, Any]],
        profile_port: ArchiveManagerProfilePort,
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
        return tuple(
            ProviderAgent.from_mapping(agent, default_provider_kind=role.provider_kind)
            for agent in self._list_agents(force_refresh)
            if isinstance(agent, Mapping) and self._matches(role, agent)
        )

    def create(self, role: SystemAgentRole) -> ProviderAgent:
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
            raise RuntimeError(str(detail or "OpenClaw agent creation failed"))
        agent_id = str(result.get("agentId") or role.stable_id).strip()
        return ProviderAgent(
            id=agent_id,
            name=role.display_name,
            provider_kind=role.provider_kind,
            workspace=str(workspace),
            raw={**dict(result), "statusKey": agent_id, "workspace": str(workspace)},
        )

    def resolve_workspace(self, agent: ProviderAgent) -> Path:
        if self._profile_port.uses_compatibility_sync and agent.workspace:
            # The compatibility callback validates and resolves the workspace.
            # This also preserves existing dependency-injection tests that replace
            # the callback with a fully synthetic filesystem result.
            return Path(agent.workspace)
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


class ArchiveManagerLifecycleAdapter:
    """Legacy-shaped delegates backed by ``SystemAgentLifecycleService``."""

    def __init__(
        self,
        lifecycle: SystemAgentLifecycleService,
        repository: ArchiveManagerStateRepository,
    ):
        self.lifecycle = lifecycle
        self.repository = repository

    def create_if_missing(self) -> SystemAgentLifecycleState:
        return self.lifecycle.reconcile(ARCHIVE_MANAGER_ROLE)

    def profile_check_on_startup(self) -> SystemAgentLifecycleState:
        return self.create_if_missing()

    def pause(self) -> SystemAgentLifecycleState:
        return self.lifecycle.pause(ARCHIVE_MANAGER_ROLE)

    def resume(self) -> SystemAgentLifecycleState:
        return self.lifecycle.resume(ARCHIVE_MANAGER_ROLE)

    def public_state(self, *, ensure: bool = True) -> dict[str, Any]:
        if not ensure:
            state = self.repository.load_legacy()
            return {
                "agentId": state.get("agentId") or ARCHIVE_MANAGER_ROLE.stable_id,
                "name": state.get("name") or ARCHIVE_MANAGER_ROLE.display_name,
                "emoji": state.get("emoji") or ARCHIVE_MANAGER_ROLE.emoji,
                "providerKind": state.get("providerKind") or ARCHIVE_MANAGER_ROLE.provider_kind,
                "status": state.get("status") or "missing",
                "label": state.get("label") or "未接入",
                "phase": ARCHIVE_MANAGER_PHASE,
                "paused": bool(state.get("paused")),
                "autoCreated": bool(state.get("autoCreated")),
                "createdAt": state.get("createdAt"),
                "updatedAt": state.get("updatedAt"),
                "profileVersion": state.get("profileVersion") or "",
                "profileUpdatedAt": state.get("profileUpdatedAt"),
                "communicationSkill": state.get("communicationSkill"),
                "lastAction": state.get("lastAction") or "",
                "lastError": state.get("lastError") or "",
                "recentActivity": (state.get("recentActivity") or [])[-ARCHIVE_MANAGER_PUBLIC_ACTIVITY_LIMIT:],
            }
        state = self.create_if_missing()
        return {
            "agentId": state.agent_id,
            "name": state.name,
            "emoji": state.emoji,
            "providerKind": state.provider_kind,
            "status": state.status.value,
            "label": archive_manager_label(state),
            "phase": ARCHIVE_MANAGER_PHASE,
            "paused": state.paused,
            "autoCreated": state.auto_created,
            "createdAt": state.created_at or None,
            "updatedAt": state.updated_at or None,
            "profileVersion": state.profile_version,
            "profileUpdatedAt": state.profile_updated_at or None,
            "communicationSkill": (
                state.to_mapping()["communicationSkill"]
                if state.communication_skill else None
            ),
            "lastAction": archive_manager_legacy_action(state, state.last_action),
            "lastError": state.last_error,
            "recentActivity": _legacy_activity(state)[-ARCHIVE_MANAGER_PUBLIC_ACTIVITY_LIMIT:],
        }

    def legacy_state(self, *, ensure: bool = True) -> dict[str, Any]:
        if not ensure:
            return self.repository.load_legacy()
        return self.repository.legacy_mapping(self.create_if_missing())

    def is_archive_manager(self, candidate: Any) -> bool:
        state = self.repository.load_legacy()
        values: tuple[str, ...]
        if isinstance(candidate, Mapping):
            values = tuple(
                value
                for key in ("id", "agentId", "statusKey", "name")
                if (value := str(candidate.get(key) or "").strip())
            )
        else:
            value = str(candidate or "").strip()
            values = (value,) if value else ()
        return any(
            ARCHIVE_MANAGER_ROLE.matches_identity(
                value,
                state.get("agentId"),
                state.get("name"),
            )
            for value in values
        )

    def agent_meta(self, candidate: Any) -> dict[str, Any]:
        if not self.is_archive_manager(candidate):
            return {}
        state = self.repository.load_legacy()
        return {
            "systemRole": ARCHIVE_MANAGER_ROLE.role_key,
            "systemAgent": True,
            "assignable": ARCHIVE_MANAGER_ROLE.assignable,
            "deletable": ARCHIVE_MANAGER_ROLE.deletable,
            "meetingEligible": ARCHIVE_MANAGER_ROLE.meeting_eligible,
            "archiveManager": True,
            "archiveManagerStatus": state.get("status") or "missing",
            "archiveManagerPaused": bool(state.get("paused")),
            "archiveManagerLabel": state.get("label") or "未接入",
        }

    def update(self, action: str) -> SystemAgentLifecycleState:
        normalized = str(action or "").strip().lower()
        if normalized == "pause":
            return self.pause()
        if normalized == "resume":
            return self.resume()
        raise ValueError("archive manager action must be pause or resume")
