"""Archive-manager callbacks used by Skills Library organization."""

from __future__ import annotations

from typing import Any, Callable, Mapping


class SkillLibraryArchiveManagerAdapter:
    """Translate organization work into existing archive-manager semantics."""

    def __init__(
        self,
        *,
        load_state: Callable[[], dict[str, Any]],
        save_state: Callable[[dict[str, Any]], object],
        public_state: Callable[[], Mapping[str, Any]],
        append_activity: Callable[..., object],
        call_agent: Callable[[str, str, int], object],
        set_presence: Callable[[str, str, str], object] = (
            lambda _agent_id, _state, _reason: None
        ),
        default_agent_id: str = "archive-manager",
    ):
        self.load_state = load_state
        self.save_state = save_state
        self.public_state = public_state
        self.append_activity = append_activity
        self.call_agent = call_agent
        self.set_presence = set_presence
        self.default_agent_id = default_agent_id

    def manager_state(self) -> Mapping[str, Any]:
        return self.public_state()

    def call(self, prompt: str, timeout_seconds: int) -> object:
        state = self.public_state()
        agent_id = str(state.get("agentId") or self.default_agent_id)
        return self.call_agent(agent_id, prompt, timeout_seconds)

    def mark_working(self, label: str) -> None:
        state = self.load_state()
        state["status"] = "working"
        state["label"] = label
        state["lastError"] = ""
        self.save_state(state)
        self.set_presence(
            str(state.get("agentId") or self.default_agent_id),
            "working",
            label,
        )

    def finalize(self, error: BaseException | None) -> None:
        state = self.load_state()
        if state.get("status") != "working":
            return
        if error is not None:
            state["status"] = "error"
            state["label"] = "档案管理员工作失败"
            state["lastError"] = str(error)
            presence = "offline"
        else:
            state["status"] = "paused" if state.get("paused") else "idle"
            state["label"] = "已暂停" if state.get("paused") else "已接入"
            state["lastError"] = ""
            presence = "break" if state.get("paused") else "idle"
        self.save_state(state)
        self.set_presence(
            str(state.get("agentId") or self.default_agent_id),
            presence,
            "" if error is None else "Skill Library organization failed",
        )

    def append_terminal(self, summary: Mapping[str, Any]) -> None:
        state = self.load_state()
        outcome = str(summary.get("status") or "failed")
        successful = outcome in {"completed", "resolved"}
        assigned = int(summary.get("assignedCount") or 0)
        failures = int(summary.get("failureCount") or 0)
        message = (
            f"技能库整理完成：已归类 {assigned} 个 Skill"
            if successful
            else f"技能库整理结束：已归类 {assigned} 个，失败 {failures} 个"
        )
        self.append_activity(
            state,
            "skill_library_organization",
            "ok" if successful else "error",
            message,
            error="" if successful else "skill organization incomplete",
        )
        self.save_state(state)
