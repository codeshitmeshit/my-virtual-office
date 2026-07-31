"""Publish HR directory responsibilities into the VO entry skill."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from services.hr_directory import HRDirectoryQuery, SafeDirectoryEntry
from services.hr_repository import HRRepository


ROUTING_START = "<!-- HR_AGENT_ROUTING_START -->"
ROUTING_END = "<!-- HR_AGENT_ROUTING_END -->"


class HRAgentRoutingSkillError(ValueError):
    code = "hr_agent_routing_skill_failed"


@dataclass(frozen=True, slots=True)
class HRAgentRoutingSkillPublishResult:
    changed: bool
    entries: int
    path: str


def _clean(value: object, limit: int = 600) -> str:
    text = str(value or "").replace("\r", " ").strip()
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "..."
    return text


def _entry_line(entry: SafeDirectoryEntry) -> str:
    status = []
    if entry.availability:
        status.append(f"availability={_clean(entry.availability, 80)}")
    if entry.readiness:
        status.append(f"readiness={_clean(entry.readiness, 80)}")
    suffix = f" ({', '.join(status)})" if status else ""
    introduction = _clean(entry.introduction, 700) or "HR 尚未发布职责介绍。"
    return f"- `{_clean(entry.ai_id, 160)}` {_clean(entry.name, 160)}{suffix}: {introduction}"


def render_agent_routing_section(entries: tuple[SafeDirectoryEntry, ...]) -> str:
    ready = tuple(
        entry
        for entry in entries
        if entry.ai_id != "hr"
        and entry.availability not in {"offline", "unavailable", "disabled", "deleted", "unreachable"}
        and entry.readiness == "ready"
    )
    lines = [
        ROUTING_START,
        "### 2.6 HR 同步的 Agent 职责路由表",
        "",
        "下面内容由 HR 名录同步、手动补全信息和新人自我介绍流程生成。主入口选择目标 Agent 时，应优先结合用户意图与这些职责介绍判断，而不是只在用户明确点名角色时才转交。",
        "",
    ]
    if ready:
        lines.extend(_entry_line(entry) for entry in sorted(ready, key=lambda item: item.ai_id))
    else:
        lines.append("- 当前 HR 尚未发布可用于自动路由的 Agent 职责介绍；只能按 `/api/agents` 的名称、role 和用户明确指向谨慎选择。")
    lines.extend(
        [
            "",
            ROUTING_END,
        ]
    )
    return "\n".join(lines)


def _all_entries(repository: HRRepository) -> tuple[SafeDirectoryEntry, ...]:
    query = HRDirectoryQuery(repository)
    items: list[SafeDirectoryEntry] = []
    cursor = None
    while True:
        page = query.list(limit=100, cursor=cursor)
        items.extend(page.items)
        if page.next_cursor is None:
            return tuple(items)
        cursor = page.next_cursor


def replace_routing_section(skill_text: str, section: str) -> str:
    if ROUTING_START in skill_text and ROUTING_END in skill_text:
        before, rest = skill_text.split(ROUTING_START, 1)
        _old, after = rest.split(ROUTING_END, 1)
        return before.rstrip() + "\n\n" + section.strip() + "\n" + after
    anchor = "### 3. 路由到专用 VO Skill"
    if anchor in skill_text:
        return skill_text.replace(anchor, section.strip() + "\n\n" + anchor, 1)
    return skill_text.rstrip() + "\n\n" + section.strip() + "\n"


def publish_agent_routing_skill(
    repository: HRRepository,
    *,
    skill_path: str | Path,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> HRAgentRoutingSkillPublishResult:
    if not isinstance(repository, HRRepository):
        raise HRAgentRoutingSkillError("repository must be an HRRepository")
    path = Path(skill_path)
    if path.name != "SKILL.md" or not path.is_file() or path.is_symlink():
        raise HRAgentRoutingSkillError("skill_path must point to a regular SKILL.md")
    current = path.read_text(encoding="utf-8")
    entries = _all_entries(repository)
    rendered = replace_routing_section(current, render_agent_routing_section(entries))
    if rendered == current:
        return HRAgentRoutingSkillPublishResult(False, len(entries), str(path))
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{new_id()}.tmp")
    try:
        temp_path.write_text(rendered, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return HRAgentRoutingSkillPublishResult(True, len(entries), str(path))
