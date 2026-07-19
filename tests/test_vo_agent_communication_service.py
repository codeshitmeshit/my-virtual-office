"""Focused contracts for the shared VO Agent communication application service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.vo_agent_communication import (
    VOAgentCommunicationError,
    VOAgentCommunicationPorts,
    VOAgentCommunicationService,
    require_reply,
)


SENDER = {
    "id": "hr",
    "providerKind": "openclaw",
    "name": "HR",
    "emoji": "👩‍💼",
}
TARGET = {
    "id": "codex-local",
    "providerKind": "codex",
    "name": "Codex",
    "emoji": "⚡",
}


def _service(*, agents=None, codex_result=None):
    agents = agents or {"hr": SENDER, "codex-local": TARGET}
    events = []
    provider_calls = []
    presence = []

    def append_event(event):
        saved = {**event, "id": f"event-{len(events) + 1}"}
        events.append(saved)
        return saved

    def agent_ref(ai_id):
        agent = agents[ai_id]
        return {
            "id": agent["id"],
            "nativeId": agent["id"],
            "providerKind": agent["providerKind"],
            "name": agent["name"],
            "emoji": agent.get("emoji", ""),
        }

    def call_codex(body):
        provider_calls.append(dict(body))
        return dict(codex_result or {"ok": True, "status": "completed", "reply": "收到"})

    ports = VOAgentCommunicationPorts(
        lookup_agent=lambda ai_id: agents.get(ai_id),
        agent_ref=agent_ref,
        archive_guard=lambda _target, _message: None,
        source_metadata=lambda _body: {},
        append_event=append_event,
        add_provider_guidance=lambda prompt: prompt + "\nVO-GUIDANCE",
        set_presence=lambda *args: presence.append(args),
        call_codex=call_codex,
        call_claude_code=lambda _body: {"ok": False, "error": "unexpected"},
        call_agent=lambda *_args: "unexpected",
    )
    return VOAgentCommunicationService(ports), events, provider_calls, presence


def test_hr_message_uses_visible_vo_events_and_provider_routing():
    service, events, calls, presence = _service()

    result = service.send({
        "fromAgentId": "hr",
        "toAgentId": "codex-local",
        "message": "请提交今日工作",
        "conversationId": "hr:daily:codex-local",
        "sourceSurface": "human-resources",
    })

    assert result["ok"] is True
    assert result["reply"] == "收到"
    assert [event["direction"] for event in events] == ["request", "reply"]
    assert events[0]["from"]["id"] == "hr"
    assert events[0]["to"]["id"] == "codex-local"
    assert calls[0]["conversationId"] == "hr:daily:codex-local"
    assert "[A2A from=hr" in calls[0]["message"]
    assert "VO-GUIDANCE" in calls[0]["message"]
    assert presence == [
        ("codex-local", "working", "Replying to OpenClaw: HR 👩‍💼"),
        ("codex-local", "idle", ""),
    ]


def test_non_ready_openclaw_sender_fails_before_history_and_provider():
    blocked = {**SENDER, "communicationSkill": {"ready": False, "status": "missing"}}
    service, events, calls, _presence = _service(agents={"hr": blocked, "codex-local": TARGET})

    result = service.send({
        "fromAgentId": "hr",
        "toAgentId": "codex-local",
        "message": "介绍自己",
    })

    assert result["ok"] is False
    assert result["code"] == "communication_skill_not_ready"
    assert result["_status"] == 409
    assert events == []
    assert calls == []


@pytest.mark.parametrize(
    ("provider_result", "expected_code"),
    [
        ({"ok": False, "status": "timeout", "error": "timed out"}, "agent_communication_timeout"),
        ({"ok": False, "status": "busy", "error": "busy"}, "agent_communication_busy"),
        ({"ok": True, "status": "completed", "reply": ""}, "agent_communication_empty_reply"),
        ({"ok": False, "status": "failed", "errorCode": "provider_denied", "error": "denied"}, "provider_denied"),
    ],
)
def test_provider_failures_have_stable_codes(provider_result, expected_code):
    service, events, _calls, _presence = _service(codex_result=provider_result)

    result = service.send({
        "fromAgentId": "hr",
        "toAgentId": "codex-local",
        "message": "介绍自己",
    })

    assert result["ok"] is False
    assert result["code"] == expected_code
    assert len(events) == 2
    with pytest.raises(VOAgentCommunicationError) as raised:
        require_reply(result)
    assert raised.value.code == expected_code
    assert raised.value.status == result["status"]


def test_http_and_hr_wiring_share_the_application_service_boundary():
    root = Path(__file__).resolve().parents[1]
    module_source = (root / "app/services/vo_agent_communication.py").read_text(encoding="utf-8")
    server_source = (root / "app/server.py").read_text(encoding="utf-8")
    hr_start = server_source.index("def _hr_ask_agent(")
    hr_end = server_source.index("\ndef _hr_ask_agent_for_information", hr_start)
    handler_start = server_source.index("def _handle_agent_platform_comm_send(body):")
    handler_end = server_source.index("\ndef _handle_agent_platform_comm_history", handler_start)

    assert "import server" not in module_source
    assert "http.server" not in module_source
    assert "_vo_agent_communication_service().send" in server_source[hr_start:hr_end]
    assert "_vo_agent_communication_service().send" in server_source[handler_start:handler_end]
    assert "_handle_agent_platform_comm_send" not in server_source[hr_start:hr_end]
