"""Downstream executor adapter for confirmed Agent Management commands."""

from __future__ import annotations

from typing import Callable, Mapping


class AgentManagementCommandExecutor:
    """Map confirmed product actions onto injected legacy operation ports."""

    _FIELD_BY_ACTION = {
        "provider": "providerKind",
        "branch": "branch",
        "workspace": "workspace",
        "assignment": "assignment",
        "binding": "providerAgentId",
    }

    def __init__(
        self,
        *,
        create_agent: Callable[[dict[str, object]], Mapping[str, object]],
        delete_agent: Callable[[dict[str, object]], Mapping[str, object]],
        update_agent: Callable[[str, dict[str, object]], object],
    ):
        for name, callback in (
            ("create_agent", create_agent),
            ("delete_agent", delete_agent),
            ("update_agent", update_agent),
        ):
            if not callable(callback):
                raise TypeError(f"{name} must be callable")
        self._create_agent = create_agent
        self._delete_agent = delete_agent
        self._update_agent = update_agent

    def execute(
        self,
        action: str,
        target_ai_id: str,
        _before: object,
        after: object,
    ) -> Mapping[str, object]:
        after_payload = after if isinstance(after, dict) else {}
        if action == "create":
            return self._create_agent(after_payload)
        if action == "delete":
            return self._delete_agent({"id": target_ai_id})
        field = self._FIELD_BY_ACTION.get(action)
        if field is None:
            return {
                "ok": False,
                "code": "agent_management_action_invalid",
                "_status": 400,
            }
        value = after_payload.get(field)
        if value is None:
            return {
                "ok": False,
                "code": "agent_management_change_invalid",
                "_status": 400,
            }
        self._update_agent(target_ai_id, {field: value})
        return {
            "ok": True,
            "targetAiId": target_ai_id,
            "action": action,
            "value": value,
        }
