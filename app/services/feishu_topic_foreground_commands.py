"""Foreground command boundary for Feishu notification topic conversations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence


MAX_ARGUMENT = 240
MAX_CONVERSATION_ID = 240
MAX_MESSAGE_ID = 300
MAX_REPLY = 2_000
MAX_SURFACE = 80
MAX_AGENT_ID = 160
MAX_CONTEXT_ITEMS = 12
MAX_CONTEXT_TEXT = 8_000
MAX_HERE_TITLE = 48


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _compact_inline_text(value: Any, limit: int) -> str:
    text = re.sub(r"https?://\S+", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n,，。；;：:")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" \t\r\n,，。；;：:") + "..."


def _here_context_title(record: Mapping[str, Any]) -> str:
    for key in ("text", "reply", "summary", "title"):
        title = _compact_inline_text(record.get(key), MAX_HERE_TITLE)
        if title:
            return title
    return "VO /here 上下文"


@dataclass(frozen=True)
class ForegroundCommand:
    name: str
    argument: str = ""


def parse_foreground_command(
    text: Any,
    attachments: Sequence[Mapping[str, Any]] | None = None,
) -> ForegroundCommand | None:
    """Parse notification-topic foreground commands without claiming ordinary chat."""

    if attachments:
        return None
    candidate = str(text or "").strip()
    if candidate == "/here":
        return ForegroundCommand("/here")
    if candidate == "/change":
        return ForegroundCommand("/change")
    prefix = "/change "
    if candidate.startswith(prefix):
        argument = _text(candidate[len(prefix):], MAX_ARGUMENT)
        return ForegroundCommand("/change", argument) if argument else None
    return None


@dataclass(frozen=True)
class ForegroundCommandContext:
    surface: str
    source_message_id: str
    conversation_id: str = ""
    topic_conversation_id: str = ""
    chat_type: str = ""
    source_meta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        surface: Any,
        source_message_id: Any,
        conversation_id: Any = "",
        topic_conversation_id: Any = "",
        chat_type: Any = "",
        source_meta: Mapping[str, Any] | None = None,
    ) -> "ForegroundCommandContext":
        return cls(
            surface=_text(surface, MAX_SURFACE).lower(),
            source_message_id=_text(source_message_id, MAX_MESSAGE_ID),
            conversation_id=_text(conversation_id, MAX_CONVERSATION_ID),
            topic_conversation_id=_text(topic_conversation_id, MAX_CONVERSATION_ID),
            chat_type=_text(chat_type, 40).lower(),
            source_meta=dict(source_meta or {}),
        )

    @property
    def is_topic(self) -> bool:
        return self.surface == "feishu-notification-topic" and bool(self.topic_conversation_id)


@dataclass(frozen=True)
class ForegroundCommandResult:
    ok: bool
    status: str
    command: str
    reply: str
    changed: bool = False
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "ok": bool(self.ok),
            "status": _text(self.status, 80),
            "command": _text(self.command, 40),
            "reply": _text(self.reply, MAX_REPLY),
            "changed": bool(self.changed),
        }
        if self.data:
            result["data"] = dict(self.data)
        return result


@dataclass(frozen=True)
class HereContextSelection:
    ok: bool
    status: str
    previous: Mapping[str, Any] = field(default_factory=dict)
    context: tuple[Mapping[str, Any], ...] = ()
    reply: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "status": self.status,
            "previous": dict(self.previous),
            "context": [dict(item) for item in self.context],
            "reply": self.reply,
        }


def _record_message_text(record: Mapping[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), Mapping) else {}
    for key in ("text", "reply", "feishuReply"):
        value = _text(record.get(key), MAX_CONTEXT_TEXT)
        if value:
            return value
    return _text(payload.get("text"), MAX_CONTEXT_TEXT)


def _record_role(record: Mapping[str, Any]) -> str:
    event = _text(record.get("event"), 80)
    state = _text(record.get("state"), 80)
    if event == "turn_completed" or state in {"completed", "agent_completed"}:
        return "assistant"
    return "user"


def _record_conversation_id(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("conversationId")
        or record.get("topicConversationId")
        or ((record.get("payload") or {}) if isinstance(record.get("payload"), Mapping) else {}).get("conversationId"),
        MAX_CONVERSATION_ID,
    )


def _record_message_id(record: Mapping[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), Mapping) else {}
    return _text(record.get("sourceMessageId") or record.get("messageId") or payload.get("messageId"), MAX_MESSAGE_ID)


def select_here_context(
    records: Sequence[Mapping[str, Any]],
    *,
    current_source_message_id: Any = "",
    conversation_id: Any = "",
    limit: int = MAX_CONTEXT_ITEMS,
) -> HereContextSelection:
    """Select the immediately preceding usable record and bounded related context."""

    target_conversation = _text(conversation_id, MAX_CONVERSATION_ID)
    current_message = _text(current_source_message_id, MAX_MESSAGE_ID)
    usable: list[dict[str, Any]] = []
    for raw in records if isinstance(records, Sequence) else []:
        if not isinstance(raw, Mapping):
            continue
        if target_conversation and _record_conversation_id(raw) != target_conversation:
            continue
        message_id = _record_message_id(raw)
        text = _record_message_text(raw)
        if not text:
            continue
        usable.append({
            "messageId": message_id,
            "role": _record_role(raw),
            "text": text,
            "event": _text(raw.get("event") or raw.get("kind") or raw.get("state"), 80),
        })
    if current_message:
        current_indexes = [index for index, item in enumerate(usable) if item.get("messageId") == current_message]
        if current_indexes:
            usable = usable[:current_indexes[0]]
        else:
            usable = [item for item in usable if item.get("messageId") != current_message]
    if not usable:
        return HereContextSelection(False, "no_context", reply="没有找到可用于 /here 的上一条消息。")
    bounded_limit = max(1, min(int(limit or MAX_CONTEXT_ITEMS), MAX_CONTEXT_ITEMS))
    context = tuple(usable[-bounded_limit:])
    return HereContextSelection(True, "success", previous=context[-1], context=context)


class HereBranchPort(Protocol):
    def create_branch(self, command: ForegroundCommand, context: ForegroundCommandContext) -> Mapping[str, Any]: ...


class TopicAgentCatalogPort(Protocol):
    def choices(self) -> Sequence[Mapping[str, Any]]: ...

    def resolve(self, name: str) -> Mapping[str, Any] | None: ...


class TopicAgentConfigPort(Protocol):
    def get_agent(self, topic_conversation_id: str) -> str: ...

    def set_agent(self, topic_conversation_id: str, agent_id: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class TopicAgentChoice:
    label: str
    agent_id: str
    aliases: tuple[str, ...] = ()

    @classmethod
    def create(cls, value: Mapping[str, Any]) -> "TopicAgentChoice | None":
        agent_id = _text(
            value.get("agentId") or value.get("id") or value.get("statusKey") or value.get("key"),
            MAX_AGENT_ID,
        )
        label = _text(value.get("label") or value.get("name") or value.get("displayName") or agent_id, 80)
        if not label or not agent_id:
            return None
        raw_aliases = value.get("aliases") if isinstance(value.get("aliases"), Sequence) and not isinstance(value.get("aliases"), (str, bytes)) else ()
        aliases = tuple(
            alias
            for alias in (_text(item, 80) for item in raw_aliases)
            if alias and alias not in {label, agent_id}
        )
        return cls(label, agent_id, aliases)

    def to_dict(self) -> dict[str, Any]:
        result = {"label": self.label, "agentId": self.agent_id}
        if self.aliases:
            result["aliases"] = list(self.aliases)
        return result


class StaticTopicAgentCatalog:
    def __init__(self, choices: Sequence[Mapping[str, Any]]) -> None:
        normalized: list[TopicAgentChoice] = []
        seen_agents: set[str] = set()
        for item in choices:
            choice = TopicAgentChoice.create(item if isinstance(item, Mapping) else {})
            if not choice or choice.agent_id in seen_agents:
                continue
            normalized.append(choice)
            seen_agents.add(choice.agent_id)
        self._choices = tuple(normalized)

    def choices(self) -> Sequence[Mapping[str, Any]]:
        return [choice.to_dict() for choice in self._choices]

    def resolve(self, name: str) -> Mapping[str, Any] | None:
        target = _text(name, MAX_AGENT_ID)
        if not target:
            return None
        for choice in self._choices:
            if target in {choice.label, choice.agent_id, *choice.aliases}:
                return choice.to_dict()
        return None


class HereBranchService:
    """Build and send /here notification branches through an injected notification entrypoint."""

    def __init__(
        self,
        *,
        records_loader: Callable[[ForegroundCommandContext], Sequence[Mapping[str, Any]]],
        notification_sender: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        self._records_loader = records_loader
        self._notification_sender = notification_sender

    def create_branch(self, command: ForegroundCommand, context: ForegroundCommandContext) -> Mapping[str, Any]:
        if command.name != "/here":
            return {"ok": False, "status": "unsupported", "reply": "不支持该命令。"}
        records = self._records_loader(context)
        selection = select_here_context(
            records,
            current_source_message_id=context.source_message_id,
            conversation_id=context.topic_conversation_id or context.conversation_id,
        )
        if not selection.ok:
            return {"ok": False, "status": selection.status, "reply": selection.reply}
        agent_id = _text(
            context.source_meta.get("representativeAgentId")
            or context.source_meta.get("agentId")
            or context.source_meta.get("pinnedAgentId"),
            160,
        )
        conversation_id = context.topic_conversation_id or context.conversation_id
        if not conversation_id or not agent_id:
            return {"ok": False, "status": "missing_context", "reply": "缺少创建 /here 通知话题所需的会话或 Agent 信息。"}
        previous_text = _text(selection.previous.get("text"), MAX_CONTEXT_TEXT)
        summary = previous_text[:500]
        title = _here_context_title(selection.previous)
        intent = {
            "id": f"here:{context.source_message_id}",
            "type": "notification",
            "target": "feishu-here-branch",
            "title": title,
            "summary": summary,
            "related": {
                "type": "conversation",
                "id": conversation_id,
                "title": title,
            },
            "details": {
                "来源": context.surface,
                "上一条记录": previous_text,
            },
            "topicContext": {
                "classification": "long_running_diversion",
                "conversationId": conversation_id,
                "agentId": agent_id,
                "title": title,
                "summary": summary,
                "requestText": previous_text,
                "goal": "Continue from a /here context branch.",
                "parentSourceMessageId": context.source_message_id,
                "parentSurface": context.surface,
                "context": [dict(item) for item in selection.context],
            },
            "sender": dict(context.source_meta.get("sender") or {}),
        }
        send_result = dict(self._notification_sender(intent) or {})
        ok = bool(send_result.get("ok"))
        status = _text(send_result.get("status") or ("success" if ok else "delivery_failed"), 80)
        message_id = _text(send_result.get("messageId") or ((send_result.get("record") or {}) if isinstance(send_result.get("record"), Mapping) else {}).get("messageId"), MAX_MESSAGE_ID)
        reply = "已发送到通知话题。" if ok else _text(send_result.get("message") or send_result.get("error") or "发送通知话题失败。", MAX_REPLY)
        return {
            "ok": ok,
            "status": status,
            "reply": reply,
            "messageId": message_id,
            "notificationIntent": intent,
            "sendResult": send_result,
        }


class FeishuTopicForegroundCommandService:
    """Single owner for /here and /change command behavior before topic dispatch."""

    def __init__(
        self,
        *,
        here_branch: HereBranchPort | None = None,
        agent_catalog: TopicAgentCatalogPort | None = None,
        agent_config: TopicAgentConfigPort | None = None,
    ) -> None:
        self._here_branch = here_branch
        self._agent_catalog = agent_catalog
        self._agent_config = agent_config

    def parse(
        self,
        text: Any,
        attachments: Sequence[Mapping[str, Any]] | None = None,
    ) -> ForegroundCommand | None:
        return parse_foreground_command(text, attachments)

    def execute(
        self,
        command: ForegroundCommand,
        context: ForegroundCommandContext,
    ) -> ForegroundCommandResult:
        if command.name == "/here":
            return self._execute_here(command, context)
        if command.name == "/change":
            return self._execute_change(command, context)
        return ForegroundCommandResult(False, "unsupported", command.name, "不支持该命令。")

    def _execute_here(
        self,
        command: ForegroundCommand,
        context: ForegroundCommandContext,
    ) -> ForegroundCommandResult:
        if self._here_branch is None:
            return ForegroundCommandResult(False, "unavailable", command.name, "/here 暂不可用。")
        outcome = dict(self._here_branch.create_branch(command, context) or {})
        ok = bool(outcome.get("ok"))
        reply = _text(outcome.get("reply") or outcome.get("error") or "已发送到通知话题。", MAX_REPLY)
        return ForegroundCommandResult(
            ok,
            _text(outcome.get("status") or ("success" if ok else "failed"), 80),
            command.name,
            reply,
            changed=ok,
            data={key: outcome[key] for key in ("notificationId", "messageId", "topicId") if outcome.get(key)},
        )

    def _execute_change(
        self,
        command: ForegroundCommand,
        context: ForegroundCommandContext,
    ) -> ForegroundCommandResult:
        if not context.is_topic:
            return ForegroundCommandResult(
                False,
                "unsupported_location",
                command.name,
                "/change 只能在已激活的通知话题中使用。",
            )
        if self._agent_catalog is None or self._agent_config is None:
            return ForegroundCommandResult(False, "unavailable", command.name, "/change 暂不可用。")
        if not command.argument:
            choices = [dict(item) for item in self._agent_catalog.choices()]
            if not choices:
                return ForegroundCommandResult(
                    False,
                    "agent_catalog_empty",
                    command.name,
                    "当前没有可切换的 Agent。",
                )
            current = self._agent_config.get_agent(context.topic_conversation_id)
            lines = ["可用 Agent："]
            for item in choices:
                label = _text(item.get("label") or item.get("name"), 80)
                agent_id = _text(item.get("agentId") or item.get("id") or item.get("key"), MAX_AGENT_ID)
                if label and agent_id:
                    suffix = "（当前）" if current and agent_id == current else ""
                    lines.append(f"- {label}: `{agent_id}`{suffix}")
            return ForegroundCommandResult(True, "choices", command.name, "\n".join(lines), data={"currentAgentId": current})
        resolved = self._agent_catalog.resolve(command.argument)
        if not resolved:
            return ForegroundCommandResult(
                False,
                "unsupported_agent",
                command.name,
                "不支持该 Agent，请输入 `/change` 查看可用选项。",
            )
        agent_id = _text(resolved.get("agentId") or resolved.get("id") or resolved.get("key"), MAX_AGENT_ID)
        if not agent_id:
            return ForegroundCommandResult(False, "unsupported_agent", command.name, "不支持该 Agent。")
        outcome = dict(self._agent_config.set_agent(context.topic_conversation_id, agent_id) or {})
        ok = outcome.get("ok", True) is not False
        label = _text(resolved.get("label") or agent_id, 80)
        reply = _text(outcome.get("reply") or f"已将当前话题 Agent 切换为 {label}: `{agent_id}`。", MAX_REPLY)
        return ForegroundCommandResult(
            bool(ok),
            _text(outcome.get("status") or ("success" if ok else "failed"), 80),
            command.name,
            reply,
            changed=bool(ok),
            data={"agentId": agent_id},
        )
