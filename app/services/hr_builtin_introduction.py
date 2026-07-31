"""Built-in HR directory introduction."""

from __future__ import annotations

import json

from services.hr_repository import HRRepository
from services.system_agent_roles import HR_ROLE


HR_BUILTIN_INTRODUCTION = (
    "HR 是 Virtual Office 的人力资源协调 Agent，负责维护 Agent 名册、收集和发布各 Agent "
    "的公开能力简介、组织日报提交、汇总工作状态与阻塞，并为协作分工提供可查询的可信目录。"
    "其他 Agent 需要了解团队成员职责、同步日报、补齐公开资料、查看协作对象或追踪 HR 流程状态时，"
    "适合与 HR 协作。"
)


def hr_builtin_raw_response() -> str:
    return json.dumps(
        {
            "schemaVersion": 1,
            "agentAiId": HR_ROLE.stable_id,
            "identity": "Virtual Office Human Resources coordination Agent.",
            "responsibilities": [
                "Maintain the Agent directory and availability records.",
                "Collect, validate, and publish public Agent introductions.",
                "Coordinate daily report requests, assessment state, and HR activity history.",
                "Expose safe HR management and Agent-facing APIs for collaboration status.",
            ],
            "strengths": [
                "Directory governance and stable Agent identity tracking.",
                "Structured HR workflows with auditable activity records.",
                "Keeping public collaboration information separate from private raw responses.",
            ],
            "collaborationScenarios": [
                "When an Agent needs to find the right collaborator for a task.",
                "When HR information, daily reports, or availability state needs to be synchronized.",
                "When a user needs an overview of team readiness, missing information, or blockers.",
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def ensure_hr_builtin_introduction(repository: HRRepository) -> None:
    if not isinstance(repository, HRRepository):
        raise TypeError("repository must be an HRRepository")
    repository.upsert_agent(
        ai_id=HR_ROLE.stable_id,
        name=HR_ROLE.display_name,
        emoji=HR_ROLE.emoji,
        agent_kind="system",
        provider_kind=HR_ROLE.provider_kind,
        status="active",
        availability="available",
        source="hr-builtin",
    )
    current = repository.get_current_introduction(HR_ROLE.stable_id)
    if current is not None and current.introduction.strip():
        return
    expected_version = current.version if current is not None else 0
    repository.save_introduction(
        ai_id=HR_ROLE.stable_id,
        state="published",
        raw_response=hr_builtin_raw_response(),
        introduction=HR_BUILTIN_INTRODUCTION,
        source="hr-builtin",
        actor_id=HR_ROLE.stable_id,
        expected_version=expected_version,
    )
