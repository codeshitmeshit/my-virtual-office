"""Focused contracts for the shared VO Agent communication application service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.services.vo_agent_communication import (
    VOAgentCommunicationError,
    VOAgentCommunicationPorts,
    VOAgentCommunicationService,
    require_reply,
)
from app.services.human_decision_chat_continuation import ContinuationDispatchRequest


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
CLAUDE_TARGET = {
    "id": "claude-code-local",
    "providerKind": "claude-code",
    "name": "Claude Code",
    "emoji": "🧠",
}
OPENCLAW_TARGET = {
    "id": "main",
    "providerKind": "openclaw",
    "name": "OpenClaw",
    "emoji": "🦅",
}


def _service(*, agents=None, codex_result=None, archive_result=None, agent_reply="收到"):
    agents = agents or {"hr": SENDER, "codex-local": TARGET}
    events = []
    provider_calls = []
    presence = []
    followups = []

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

    def call_claude_code(body):
        provider_calls.append(dict(body))
        return {"ok": True, "status": "completed", "reply": "收到"}

    def call_agent(*args):
        provider_calls.append({
            "agentId": args[0],
            "message": args[1],
            "timeoutSec": args[2],
            "projectId": args[3],
            "taskId": args[4],
        })
        return agent_reply

    ports = VOAgentCommunicationPorts(
        lookup_agent=lambda ai_id: agents.get(ai_id),
        agent_ref=agent_ref,
        archive_guard=lambda _target, _message: archive_result,
        source_metadata=lambda _body: {},
        append_event=append_event,
        add_provider_guidance=lambda prompt: prompt + "\nVO-GUIDANCE",
        set_presence=lambda *args: presence.append(args),
        call_codex=call_codex,
        call_claude_code=call_claude_code,
        call_agent=call_agent,
        schedule_deferred_followup=lambda payload: followups.append(dict(payload)) or {"ok": True, "status": "scheduled"},
    )
    return VOAgentCommunicationService(ports), events, provider_calls, presence, followups


def test_hr_message_uses_visible_vo_events_and_provider_routing():
    service, events, calls, presence, _followups = _service()

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
    assert "<agent_platform_message_prompt>" in calls[0]["message"]
    assert '<from id="hr"' in calls[0]["message"]
    assert "<original_channel_interim_notice>" in calls[0]["message"]
    assert "cross-VO communication" in calls[0]["message"]
    assert "VO-GUIDANCE" in calls[0]["message"]
    assert presence == [
        ("codex-local", "working", "Replying to OpenClaw: HR 👩‍💼"),
        ("codex-local", "idle", ""),
    ]


def test_non_ready_openclaw_sender_fails_before_history_and_provider():
    blocked = {**SENDER, "communicationSkill": {"ready": False, "status": "missing"}}
    service, events, calls, _presence, _followups = _service(agents={"hr": blocked, "codex-local": TARGET})

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
    service, events, _calls, _presence, _followups = _service(codex_result=provider_result)

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


def test_feishu_timeout_is_deferred_without_authorizing_sender_fallback():
    service, events, _calls, _presence, followups = _service(codex_result={
        "ok": False,
        "status": "timeout",
        "error": "timed out",
        "activeConversationId": "main__codex__market",
        "activeStatus": "running",
    })

    result = service.send({
        "fromAgentId": "hr",
        "toAgentId": "codex-local",
        "message": "请研究这家公司",
        "conversationId": "main__codex__market",
        "sourceApp": "feishu",
        "sourceSurface": "feishu-dm",
        "sourceMessageId": "om-1",
        "feishuChatId": "oc-1",
        "timeoutSec": 90,
    })

    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["deferred"] is True
    assert result["code"] == "agent_communication_deferred"
    assert result["activeConversationId"] == "main__codex__market"
    assert result["activeStatus"] == "running"
    assert result["deferredFollowup"]["status"] == "scheduled"
    assert followups[0]["requestEventId"] == events[0]["id"]
    assert followups[0]["sourceContext"]["sourceMessageId"] == "om-1"
    assert "不要代替目标 Agent 输出业务结论" in result["reply"]
    assert "Do not answer the delegated business question yourself" in result["callerInstruction"]
    assert events[-1]["ok"] is False
    assert events[-1]["metadata"]["deferredTimeout"]["reason"] == "target_agent_timeout"


def test_feishu_timeout_defers_when_source_context_is_nested_in_metadata():
    service, events, calls, _presence, _followups = _service(codex_result={
        "ok": False,
        "status": "timeout",
        "error": "timed out",
    })

    result = service.send({
        "fromAgentId": "hr",
        "toAgentId": "codex-local",
        "message": "请研究这家公司",
        "conversationId": "main__codex__market",
        "timeoutSec": 90,
        "metadata": {
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceLabel": "Feishu DM",
            "sourceMessageId": "om-1",
            "feishuChatId": "oc-1",
            "chatType": "p2p",
        },
    })

    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["deferred"] is True
    assert calls[0]["timeoutSec"] == 90
    assert events[0]["metadata"]["sourceApp"] == "feishu"
    assert events[0]["metadata"]["sourceSurface"] == "feishu-dm"
    assert events[-1]["metadata"]["deferredTimeout"]["timeoutSec"] == 90


def test_openclaw_agent_timeout_is_deferred_for_feishu_followup():
    service, events, calls, _presence, followups = _service(
        agents={"hr": SENDER, "main": OPENCLAW_TARGET},
        agent_reply="[ERROR] Agent call timed out",
    )

    result = service.send({
        "fromAgentId": "hr",
        "toAgentId": "main",
        "message": "请研究美团",
        "conversationId": "codex__research__meituan",
        "sourceApp": "feishu",
        "sourceSurface": "feishu-dm",
        "sourceMessageId": "om-timeout",
        "feishuChatId": "oc-1",
        "timeoutSec": 90,
    })

    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["deferred"] is True
    assert result["activeConversationId"] == "codex__research__meituan"
    assert result["activeStatus"] == "running"
    assert calls[0]["agentId"] == "main"
    assert followups[0]["requestEventId"] == events[0]["id"]
    assert followups[0]["agentId"] == "main"
    assert followups[0]["providerResult"]["status"] == "timeout"
    assert events[-1]["metadata"]["deferredTimeout"]["followup"]["status"] == "scheduled"


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


def test_trusted_human_decision_resume_reuses_original_conversation_and_prompt():
    service, events, calls, _presence, _followups = _service()
    request = ContinuationDispatchRequest(
        decision_id="decision-1",
        agent_id="codex-local",
        conversation_id="conversation-1",
        source_message_id="human-decision-resume:decision-1",
        source="human-decision-resume",
        prompt="<human_decision_chat_resume><task>继续</task></human_decision_chat_resume>",
    )

    result = service.send_trusted_resume(request)

    assert result["ok"] is True
    assert result["conversationId"] == "conversation-1"
    assert calls[0]["agentId"] == "codex-local"
    assert calls[0]["conversationId"] == "conversation-1"
    assert calls[0]["sourceMessageId"] == "human-decision-resume:decision-1"
    assert calls[0]["message"] == request.prompt
    assert [event["conversationId"] for event in events] == ["conversation-1", "conversation-1"]
    assert events[0]["metadata"]["sourceMessageId"] == "human-decision-resume:decision-1"
    assert events[0]["metadata"]["source"] == "human-decision-resume"
    assert events[1]["text"] == "收到"


def test_trusted_human_decision_resume_rejects_unknown_agent_before_history():
    service, events, calls, _presence, _followups = _service()
    request = ContinuationDispatchRequest(
        decision_id="decision-1",
        agent_id="missing",
        conversation_id="conversation-1",
        source_message_id="human-decision-resume:decision-1",
        source="human-decision-resume",
        prompt="<human_decision_chat_resume></human_decision_chat_resume>",
    )

    result = service.send_trusted_resume(request)

    assert result == {
        "ok": False,
        "error": "Target agent 'missing' not found",
        "_status": 404,
    }
    assert events == []
    assert calls == []


def test_trusted_human_decision_resume_does_not_treat_archive_guard_as_dispatch():
    service, events, calls, _presence, _followups = _service(
        archive_result={"reply": "Agent 已归档", "status": "archived"},
    )
    request = ContinuationDispatchRequest(
        decision_id="decision-1",
        agent_id="codex-local",
        conversation_id="conversation-1",
        source_message_id="human-decision-resume:decision-1",
        source="human-decision-resume",
        prompt="<human_decision_chat_resume></human_decision_chat_resume>",
    )

    result = service.send_trusted_resume(request)

    assert result == {
        "ok": False,
        "error": "Target agent is unavailable for continuation",
        "code": "agent_communication_unavailable",
        "status": "archived",
        "_status": 409,
    }
    assert len(events) == 1
    assert calls == []
