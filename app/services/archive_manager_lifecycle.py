"""Archive Room compatibility adapter for the shared system-Agent lifecycle."""

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
from .system_agent_roles import ARCHIVE_MANAGER_ROLE, SystemAgentRole


ARCHIVE_MANAGER_PHASE = "phase-4"
ARCHIVE_MANAGER_ACTIVITY_LIMIT = 12


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


def _legacy_activity(state: SystemAgentLifecycleState) -> list[dict[str, Any]]:
    result = []
    for activity in state.recent_activity[-ARCHIVE_MANAGER_ACTIVITY_LIMIT:]:
        item = activity.to_mapping()
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

    def load(self, role: SystemAgentRole = ARCHIVE_MANAGER_ROLE) -> SystemAgentLifecycleState:
        if role.role_key != ARCHIVE_MANAGER_ROLE.role_key:
            raise ValueError("ArchiveManagerStateRepository only accepts archive_manager")
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
        return SystemAgentLifecycleState.from_mapping(
            role,
            data,
            now=self._clock(),
            activity_limit=ARCHIVE_MANAGER_ACTIVITY_LIMIT,
        )

    def _payload(self, state: SystemAgentLifecycleState) -> dict[str, Any]:
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
            "lastAction": state.last_action,
            "lastError": state.last_error,
            "recentActivity": _legacy_activity(state),
            **({"workspace": state.workspace} if state.workspace else {}),
            **({"profileFiles": list(state.profile_files)} if state.profile_files else {}),
            **({"profileVersion": state.profile_version} if state.profile_version else {}),
            **({"profileUpdatedAt": state.profile_updated_at} if state.profile_updated_at else {}),
            **({"reconciledAt": state.reconciled_at} if state.reconciled_at else {}),
            **({"communicationSkill": state.to_mapping()["communicationSkill"]} if state.communication_skill else {}),
        }

    def save(
        self,
        role: SystemAgentRole,
        state: SystemAgentLifecycleState,
    ) -> SystemAgentLifecycleState:
        if role.role_key != ARCHIVE_MANAGER_ROLE.role_key or state.role_key != role.role_key:
            raise ValueError("archive manager state role mismatch")
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
                json.dump(self._payload(state), output, ensure_ascii=False, indent=2)
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
        return state


class ArchiveManagerProfilePort:
    """Renders the legacy template through the generic safe Profile engine."""

    def __init__(
        self,
        template_path: str | os.PathLike[str],
        openclaw_home: str | os.PathLike[str],
    ):
        self.template_path = Path(template_path).absolute()
        self.openclaw_home = Path(openclaw_home).absolute()

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
        safe_workspace = self.workspace_for(agent.id, workspace)
        return sync_profile_files(
            self.openclaw_home,
            safe_workspace,
            self.render(),
            version_marker=role.version_marker,
        )


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
        state = self.create_if_missing() if ensure else self.repository.load()
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
            "communicationSkill": dict(state.communication_skill) if state.communication_skill else None,
            "lastAction": state.last_action,
            "lastError": state.last_error,
            "recentActivity": _legacy_activity(state),
        }

    def is_archive_manager(self, candidate: Any) -> bool:
        state = self.repository.load()
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
            ARCHIVE_MANAGER_ROLE.matches_identity(value, state.agent_id, state.name)
            for value in values
        )

    def agent_meta(self, candidate: Any) -> dict[str, Any]:
        if not self.is_archive_manager(candidate):
            return {}
        state = self.repository.load()
        return {
            "systemRole": ARCHIVE_MANAGER_ROLE.role_key,
            "assignable": ARCHIVE_MANAGER_ROLE.assignable,
            "archiveManager": True,
            "archiveManagerStatus": state.status.value,
            "archiveManagerPaused": state.paused,
            "archiveManagerLabel": archive_manager_label(state),
        }

    def update(self, action: str) -> SystemAgentLifecycleState:
        normalized = str(action or "").strip().lower()
        if normalized == "pause":
            return self.pause()
        if normalized == "resume":
            return self.resume()
        raise ValueError("archive manager action must be pause or resume")
