"""Stable project and deletion protection errors for VO system-Agent roles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .system_agent_roles import ARCHIVE_MANAGER_ROLE, SystemAgentRole


@dataclass(frozen=True, slots=True)
class SystemAgentPolicyError:
    code: str
    message: str
    status: int
    role_key: str
    operation: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "error": self.message,
            "code": self.code,
            "systemRole": self.role_key,
            "operation": self.operation,
            "_status": self.status,
        }


def assignment_error(
    role: SystemAgentRole | None,
    *,
    scope: str = "task",
) -> SystemAgentPolicyError | None:
    if role is None or role.assignable:
        return None
    normalized_scope = str(scope or "task").strip().lower()
    if role.role_key == ARCHIVE_MANAGER_ROLE.role_key:
        message = (
            "档案管理员不能作为普通项目默认执行或审查 AI"
            if normalized_scope in {"project", "project_defaults", "template"}
            else "档案管理员不能被分配普通项目任务"
        )
        return SystemAgentPolicyError(
            "archive_manager_not_assignable",
            message,
            400,
            role.role_key,
            "project_assignment",
        )
    return SystemAgentPolicyError(
        "system_agent_not_assignable",
        f"{role.display_name} 是 VO 系统角色，不能被分配普通项目工作",
        400,
        role.role_key,
        "project_assignment",
    )


def deletion_error(role: SystemAgentRole | None) -> SystemAgentPolicyError | None:
    if role is None or role.deletable:
        return None
    if role.role_key == ARCHIVE_MANAGER_ROLE.role_key:
        return SystemAgentPolicyError(
            "archive_manager_cannot_delete",
            "档案管理员是系统角色，不能删除；可以在档案室暂停。",
            403,
            role.role_key,
            "agent_deletion",
        )
    return SystemAgentPolicyError(
        "system_agent_cannot_delete",
        f"{role.display_name} 是 VO 系统角色，不能删除；请使用人事管理中的暂停控制。",
        403,
        role.role_key,
        "agent_deletion",
    )


def meeting_error(role: SystemAgentRole | None) -> SystemAgentPolicyError | None:
    if role is None or role.meeting_eligible:
        return None
    if role.role_key == ARCHIVE_MANAGER_ROLE.role_key:
        return SystemAgentPolicyError(
            "archive_manager_not_meeting_participant",
            "档案管理员是系统档案角色，不能作为普通会议参与者；请在档案室进行归档维护。",
            400,
            role.role_key,
            "meeting_participation",
        )
    return SystemAgentPolicyError(
        "system_agent_not_meeting_eligible",
        f"{role.display_name} 当前系统角色不允许参加会议",
        400,
        role.role_key,
        "meeting_participation",
    )
