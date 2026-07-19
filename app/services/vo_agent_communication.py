"""Provider-neutral Virtual Office Agent-to-Agent communication service.

The HTTP route and internal workflows (including HR) share this application
service.  Provider and persistence details are injected so this module remains
independent from the legacy server entry point and HTTP transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping


Agent = Mapping[str, Any]
Result = dict[str, Any]


@dataclass(frozen=True, slots=True)
class VOAgentCommunicationPorts:
    lookup_agent: Callable[[str], Agent | None]
    agent_ref: Callable[[str], Result]
    archive_guard: Callable[[str, str], Result | None]
    source_metadata: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    append_event: Callable[[Mapping[str, Any]], Result]
    add_provider_guidance: Callable[[str], str]
    set_presence: Callable[[str, str, str], None]
    call_codex: Callable[[Mapping[str, Any]], Result]
    call_claude_code: Callable[[Mapping[str, Any]], Result]
    call_agent: Callable[[str, str, int, str, str], str]


class VOAgentCommunicationError(RuntimeError):
    """Typed failure raised when an internal caller requires a reply."""

    def __init__(self, result: Mapping[str, Any]):
        self.result = dict(result)
        self.code = str(
            result.get("code")
            or result.get("errorCode")
            or "agent_communication_failed"
        )
        self.status = str(result.get("status") or "execution_failed")
        super().__init__(str(result.get("error") or result.get("reply") or self.code))


def require_reply(result: Mapping[str, Any]) -> str | None:
    """Return a successful reply or raise a stable, inspectable failure."""

    if not result.get("ok"):
        raise VOAgentCommunicationError(result)
    reply = result.get("reply")
    return str(reply) if reply is not None else None


class VOAgentCommunicationService:
    """Send visible office-mediated messages through injected provider ports."""

    def __init__(self, ports: VOAgentCommunicationPorts):
        self._ports = ports

    @staticmethod
    def _failure_code(provider_result: Mapping[str, Any] | None, reply: Any) -> str:
        provider_result = provider_result or {}
        explicit = provider_result.get("errorCode") or provider_result.get("code")
        if explicit:
            return str(explicit)
        status = str(provider_result.get("status") or "").strip().lower()
        if status == "timeout":
            return "agent_communication_timeout"
        if status == "busy":
            return "agent_communication_busy"
        if status == "empty_reply" or not str(reply or "").strip():
            return "agent_communication_empty_reply"
        return "agent_communication_execution_failed"

    def send(self, body: Mapping[str, Any]) -> Result:
        from_type = str(body.get("fromType") or body.get("senderType") or "agent").strip().lower()
        from_agent_id = str(body.get("fromAgentId") or body.get("from") or "").strip()
        to_agent_id = str(body.get("toAgentId") or body.get("to") or "").strip()
        message = str(body.get("message") or body.get("text") or "").strip()
        is_human_source = from_type in {"human", "user", "chat", "ui"}
        if not from_agent_id and not is_human_source:
            return {"ok": False, "error": "fromAgentId is required", "_status": 400}
        if not to_agent_id:
            return {"ok": False, "error": "toAgentId is required", "_status": 400}
        if not message:
            return {"ok": False, "error": "message is required", "_status": 400}

        to_agent = self._ports.lookup_agent(to_agent_id)
        if not to_agent:
            return {"ok": False, "error": f"Target agent '{to_agent_id}' not found", "_status": 404}
        from_agent = None if is_human_source else self._ports.lookup_agent(from_agent_id)
        if not is_human_source and not from_agent:
            return {"ok": False, "error": f"Sender agent '{from_agent_id}' not found", "_status": 404}
        if from_agent and from_agent.get("providerKind", "openclaw") == "openclaw":
            communication_skill = from_agent.get("communicationSkill")
            if isinstance(communication_skill, dict) and communication_skill.get("ready") is False:
                return {
                    "ok": False,
                    "error": f"Sender agent '{from_agent_id}' communication skill is not ready",
                    "code": "communication_skill_not_ready",
                    "status": communication_skill.get("status") or "not_ready",
                    "communicationSkill": communication_skill,
                    "_status": 409,
                }

        archive_guard = self._ports.archive_guard(to_agent_id, message)
        source_app = str(body.get("sourceApp") or body.get("app") or "virtual-office").strip() or "virtual-office"
        source_surface = str(body.get("sourceSurface") or body.get("surface") or "agent-platform").strip() or "agent-platform"
        source_label = str(body.get("sourceLabel") or "").strip()
        if is_human_source:
            display_name = str(body.get("fromDisplayName") or body.get("displayName") or body.get("fromName") or "User").strip() or "User"
            native_id = str(body.get("fromId") or body.get("fromUserId") or "user").strip() or "user"
            from_ref = {
                "id": native_id,
                "nativeId": native_id,
                "providerKind": "human",
                "providerType": "chat-window",
                "name": display_name,
                "emoji": "",
                "sourceApp": source_app,
                "sourceSurface": source_surface,
                "sourceLabel": source_label,
            }
        else:
            from_ref = self._ports.agent_ref(from_agent_id)
        to_ref = self._ports.agent_ref(to_agent_id)
        conversation_id = str(body.get("conversationId") or body.get("threadId") or f"{from_ref['id']}__{to_ref['id']}").strip()
        metadata = dict(body.get("metadata")) if isinstance(body.get("metadata"), dict) else {}
        metadata.setdefault("sourceApp", source_app)
        metadata.setdefault("sourceSurface", source_surface)
        metadata.update({key: value for key, value in self._ports.source_metadata(body).items() if value})
        if source_label:
            metadata.setdefault("sourceLabel", source_label)
        timeout = int(body.get("timeoutSec") or body.get("timeout") or 600)

        inbound = self._ports.append_event({
            "type": "message",
            "direction": "request",
            "conversationId": conversation_id,
            "from": from_ref,
            "to": to_ref,
            "text": message,
            "metadata": metadata,
            "visibleInOffice": True,
        })
        if archive_guard:
            outbound = self._ports.append_event({
                "type": "message",
                "direction": "reply",
                "conversationId": conversation_id,
                "from": to_ref,
                "to": from_ref,
                "text": archive_guard["reply"],
                "inReplyTo": inbound["id"],
                "metadata": metadata,
                "visibleInOffice": True,
                "ok": True,
            })
            return {
                "ok": True,
                "conversationId": conversation_id,
                "messageId": inbound["id"],
                "replyMessageId": outbound["id"],
                "from": from_ref,
                "to": to_ref,
                "reply": archive_guard["reply"],
                "status": archive_guard["status"],
                "modifiedFiles": [],
                "needsHumanIntervention": False,
                "activeConversationId": "",
                "activeStatus": "",
            }

        provider_prefixes = {
            "openclaw": "OpenClaw",
            "hermes": "Hermes",
            "codex": "Codex",
            "claude-code": "Claude Code",
        }
        if is_human_source:
            sender_label = from_ref.get("name") or "User"
            pretty_surface = source_label or (
                "Virtual Office Chat"
                if source_app == "virtual-office" and source_surface in {"chat-window", "chat"}
                else f"{source_app.replace('-', ' ').title()} {source_surface.replace('-', ' ').title()}".strip()
            )
            envelope_source = pretty_surface
        else:
            provider_kind = str(from_ref.get("providerKind") or "").lower()
            provider_label = provider_prefixes.get(provider_kind, str(from_ref.get("providerKind") or "Agent").replace("-", " ").title())
            base_name = f"{from_ref.get('name') or from_ref['id']} {from_ref.get('emoji') or ''}".strip()
            sender_label = f"{provider_label}: {base_name}" if provider_label else base_name
            envelope_source = "My Virtual Office AgentPlatform-to-AgentPlatform Communications"
        target_prompt = (
            f"[A2A from={from_ref['id']} name={json.dumps(sender_label)} to={to_ref['id']} isUser={'true' if is_human_source else 'false'} sourceApp={json.dumps(source_app)} sourceSurface={json.dumps(source_surface)}]\n"
            f"Message from {sender_label} via {envelope_source}.\n\n"
            f"{message}\n\n"
            "Reply directly to the sender. Keep the reply concise unless detail is needed."
        )
        target_prompt = self._ports.add_provider_guidance(target_prompt)

        self._ports.set_presence(to_ref["id"], "working", f"Replying to {sender_label}")
        provider_result: Result | None = None
        try:
            provider_kind = str(to_ref.get("providerKind") or "").lower()
            if provider_kind == "codex":
                provider_result = self._ports.call_codex({
                    "agentId": to_ref["id"],
                    "message": target_prompt,
                    "timeoutSec": timeout,
                    "conversationId": conversation_id,
                    "fromType": "human" if is_human_source else "agent",
                })
                reply = provider_result.get("reply") or provider_result.get("error") or ""
                ok = bool(provider_result.get("ok"))
            elif provider_kind == "claude-code":
                provider_result = self._ports.call_claude_code({
                    "agentId": to_ref["id"],
                    "message": target_prompt,
                    "timeoutSec": timeout,
                    "conversationId": conversation_id,
                    "fromType": "human" if is_human_source else "agent",
                })
                reply = provider_result.get("reply") or provider_result.get("error") or ""
                ok = bool(provider_result.get("ok"))
            else:
                reply = self._ports.call_agent(
                    to_ref["id"], target_prompt, timeout,
                    "agent-platform-communications", conversation_id,
                )
                ok = not str(reply or "").startswith("[ERROR]")
            if ok and not str(reply or "").strip():
                ok = False
                if provider_result is not None:
                    provider_result["status"] = "empty_reply"
        except Exception as exc:
            reply = f"[ERROR] {exc}"
            ok = False
        finally:
            self._ports.set_presence(to_ref["id"], "idle", "")

        outbound_metadata = dict(metadata)
        if provider_result:
            outbound_metadata["codex"] = {
                "status": provider_result.get("status"),
                "errorCode": provider_result.get("errorCode"),
                "threadId": provider_result.get("threadId"),
                "turnId": provider_result.get("turnId"),
                "modifiedFiles": provider_result.get("modifiedFiles") or [],
                "needsHumanIntervention": bool(provider_result.get("needsHumanIntervention")),
                "durationMs": provider_result.get("durationMs"),
            }
        outbound = self._ports.append_event({
            "type": "message",
            "direction": "reply",
            "conversationId": conversation_id,
            "from": to_ref,
            "to": from_ref,
            "text": reply,
            "inReplyTo": inbound["id"],
            "metadata": outbound_metadata,
            "visibleInOffice": True,
            "ok": ok,
        })

        status = provider_result.get("status") if provider_result else (
            "completed" if ok else ("empty_reply" if not str(reply or "").strip() else "execution_failed")
        )
        result = {
            "ok": ok,
            "conversationId": conversation_id,
            "messageId": inbound["id"],
            "replyMessageId": outbound["id"],
            "from": from_ref,
            "to": to_ref,
            "reply": reply,
            "status": status,
            "modifiedFiles": provider_result.get("modifiedFiles") if provider_result else [],
            "needsHumanIntervention": bool(provider_result and provider_result.get("needsHumanIntervention")),
            "activeConversationId": provider_result.get("activeConversationId", "") if provider_result else "",
            "activeStatus": provider_result.get("activeStatus", "") if provider_result else "",
        }
        if not ok:
            result["code"] = self._failure_code(provider_result, reply)
        return result
