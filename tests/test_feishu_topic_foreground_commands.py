from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.feishu_topic_foreground_commands import (
    FeishuTopicForegroundCommandService,
    ForegroundCommandContext,
    HereBranchService,
    StaticTopicAgentCatalog,
    parse_foreground_command,
    select_here_context,
)
import services.feishu_topic_foreground_commands as foreground_module


class HereBranch:
    def __init__(self):
        self.calls = []

    def create_branch(self, command, context):
        self.calls.append((command, context))
        return {
            "ok": True,
            "status": "success",
            "reply": "已发送到通知话题。",
            "messageId": "om-branch",
        }


class AgentCatalog:
    def __init__(self):
        self.items = [
            {"label": "码头蓝点薯条", "agentId": "agent-detail"},
            {"label": "欧阳文骏", "agentId": "agent-pro", "aliases": ["professional"]},
        ]

    def choices(self):
        return list(self.items)

    def resolve(self, name):
        normalized = str(name or "").strip()
        for item in self.items:
            aliases = [str(value) for value in item.get("aliases", [])]
            if normalized in {item["agentId"], item["label"], *aliases}:
                return item
        return None


class AgentConfig:
    def __init__(self):
        self.current = {}
        self.set_calls = []

    def get_agent(self, topic_conversation_id):
        return self.current.get(topic_conversation_id, "")

    def set_agent(self, topic_conversation_id, agent_id):
        self.set_calls.append((topic_conversation_id, agent_id))
        self.current[topic_conversation_id] = agent_id
        return {"ok": True, "status": "success"}


@pytest.mark.parametrize(
    "text, expected_name, expected_argument",
    [
        ("/here", "/here", ""),
        ("  /change  ", "/change", ""),
        ("/change agent-pro", "/change", "agent-pro"),
        ("/change   agent-pro  ", "/change", "agent-pro"),
    ],
)
def test_parse_foreground_commands(text, expected_name, expected_argument):
    command = parse_foreground_command(text)
    assert command is not None
    assert command.name == expected_name
    assert command.argument == expected_argument


@pytest.mark.parametrize("text", ["/here now", "/new", "hello", ""])
def test_parse_foreground_commands_preserves_ordinary_chat(text):
    assert parse_foreground_command(text) is None


def test_parse_foreground_commands_rejects_attachment_commands():
    assert parse_foreground_command("/here", [{"name": "context.txt"}]) is None
    assert parse_foreground_command("/change agent-pro", [{"name": "context.txt"}]) is None


def test_here_delegates_to_branch_port_with_bounded_context():
    here = HereBranch()
    service = FeishuTopicForegroundCommandService(here_branch=here)
    context = ForegroundCommandContext.create(
        surface="feishu-dm",
        source_message_id="om-source",
        conversation_id="conversation-main",
        source_meta={"sender": {"openId": "ou"}},
    )

    result = service.execute(parse_foreground_command("/here"), context)

    assert result.ok is True
    assert result.status == "success"
    assert result.changed is True
    assert result.data["messageId"] == "om-branch"
    assert here.calls[0][1].conversation_id == "conversation-main"


def test_change_requires_activated_notification_topic():
    service = FeishuTopicForegroundCommandService(agent_catalog=AgentCatalog(), agent_config=AgentConfig())
    context = ForegroundCommandContext.create(surface="feishu-dm", source_message_id="om-source")

    result = service.execute(parse_foreground_command("/change"), context)

    assert result.ok is False
    assert result.status == "unsupported_location"
    assert "通知话题" in result.reply


def test_change_lists_choices_with_current_topic_agent():
    config = AgentConfig()
    config.current["topic-conversation"] = "agent-pro"
    service = FeishuTopicForegroundCommandService(agent_catalog=AgentCatalog(), agent_config=config)
    context = ForegroundCommandContext.create(
        surface="feishu-notification-topic",
        source_message_id="om-source",
        topic_conversation_id="topic-conversation",
    )

    result = service.execute(parse_foreground_command("/change"), context)

    assert result.ok is True
    assert result.status == "choices"
    assert "码头蓝点薯条" in result.reply
    assert "`agent-pro`（当前）" in result.reply
    assert result.data["currentAgentId"] == "agent-pro"


def test_change_lists_clear_configuration_message_when_agent_catalog_empty():
    service = FeishuTopicForegroundCommandService(
        agent_catalog=StaticTopicAgentCatalog([]),
        agent_config=AgentConfig(),
    )
    context = ForegroundCommandContext.create(
        surface="feishu-notification-topic",
        source_message_id="om-source",
        topic_conversation_id="topic-conversation",
    )

    result = service.execute(parse_foreground_command("/change"), context)

    assert result.ok is False
    assert result.status == "agent_catalog_empty"
    assert "Agent" in result.reply


def test_change_updates_only_current_topic_agent():
    config = AgentConfig()
    service = FeishuTopicForegroundCommandService(agent_catalog=AgentCatalog(), agent_config=config)
    context = ForegroundCommandContext.create(
        surface="feishu-notification-topic",
        source_message_id="om-source",
        topic_conversation_id="topic-conversation",
    )

    result = service.execute(parse_foreground_command("/change professional"), context)

    assert result.ok is True
    assert result.changed is True
    assert result.data["agentId"] == "agent-pro"
    assert config.set_calls == [("topic-conversation", "agent-pro")]


def test_change_rejects_unknown_agent_without_mutation():
    config = AgentConfig()
    service = FeishuTopicForegroundCommandService(agent_catalog=AgentCatalog(), agent_config=config)
    context = ForegroundCommandContext.create(
        surface="feishu-notification-topic",
        source_message_id="om-source",
        topic_conversation_id="topic-conversation",
    )

    result = service.execute(parse_foreground_command("/change missing"), context)

    assert result.ok is False
    assert result.status == "unsupported_agent"
    assert config.set_calls == []


def test_static_topic_agent_catalog_bounds_deduplicates_and_resolves_aliases():
    catalog = StaticTopicAgentCatalog([
        {"label": "更详细", "agentId": "agent-detail", "aliases": ["detail"]},
        {"label": "重复", "agentId": "agent-detail"},
        {"label": "", "agentId": ""},
        {"label": "更专业" * 100, "agentId": "agent-pro" * 50, "aliases": ["professional", "更专业" * 100]},
    ])

    choices = catalog.choices()

    assert len(choices) == 2
    assert choices[0] == {"label": "更详细", "agentId": "agent-detail", "aliases": ["detail"]}
    assert len(choices[1]["label"]) == 80
    assert len(choices[1]["agentId"]) == 160
    assert catalog.resolve("detail")["agentId"] == "agent-detail"
    assert catalog.resolve("professional")["agentId"] == choices[1]["agentId"]
    assert catalog.resolve("missing") is None


def test_select_here_context_uses_previous_main_chat_record_and_bounded_context():
    records = [
        {"event": "turn_completed", "sourceMessageId": f"om-{index}", "conversationId": "main", "text": f"user-{index}", "reply": f"reply-{index}"}
        for index in range(20)
    ]
    records.append({"event": "user_message", "sourceMessageId": "om-here", "conversationId": "main", "text": "/here"})

    selection = select_here_context(records, current_source_message_id="om-here", conversation_id="main")

    assert selection.ok is True
    assert selection.previous["messageId"] == "om-19"
    assert selection.previous["text"] == "user-19"
    assert len(selection.context) == 12
    assert selection.context[0]["messageId"] == "om-8"


def test_select_here_context_reads_topic_message_records():
    records = [
        {
            "kind": "topic-message",
            "messageId": "topic-1",
            "conversationId": "topic-conversation",
            "payload": {"text": "topic question"},
        },
        {
            "kind": "topic-message",
            "messageId": "topic-2",
            "conversationId": "topic-conversation",
            "reply": "topic answer",
        },
        {
            "kind": "topic-message",
            "messageId": "topic-here",
            "conversationId": "topic-conversation",
            "payload": {"text": "/here"},
        },
    ]

    selection = select_here_context(
        records,
        current_source_message_id="topic-here",
        conversation_id="topic-conversation",
    )

    assert selection.ok is True
    assert selection.previous["messageId"] == "topic-2"
    assert selection.previous["text"] == "topic answer"
    assert [item["messageId"] for item in selection.context] == ["topic-1", "topic-2"]


def test_select_here_context_filters_other_conversations_and_rejects_empty_context():
    records = [
        {"event": "turn_completed", "sourceMessageId": "other-1", "conversationId": "other", "text": "other"},
        {"event": "user_message", "sourceMessageId": "here", "conversationId": "main", "text": "/here"},
    ]

    selection = select_here_context(records, current_source_message_id="here", conversation_id="main")

    assert selection.ok is False
    assert selection.status == "no_context"
    assert "上一条消息" in selection.reply


def test_here_branch_service_sends_unified_notification_intent_with_topic_context():
    sent = []

    def sender(intent):
        sent.append(intent)
        return {"ok": True, "status": "sent", "messageId": "om-notification"}

    service = HereBranchService(
        records_loader=lambda _context: [
            {"event": "turn_completed", "sourceMessageId": "om-prev", "conversationId": "main", "text": "上一条问题", "reply": "上一条回答"},
            {"event": "user_message", "sourceMessageId": "om-here", "conversationId": "main", "text": "/here"},
        ],
        notification_sender=sender,
    )
    context = ForegroundCommandContext.create(
        surface="feishu-dm",
        source_message_id="om-here",
        conversation_id="main",
        source_meta={
            "representativeAgentId": "agent-a",
            "sender": {"openId": "ou-human"},
        },
    )

    result = service.create_branch(parse_foreground_command("/here"), context)

    assert result["ok"] is True
    assert result["messageId"] == "om-notification"
    assert sent[0]["id"] == "here:om-here"
    assert sent[0]["topicContext"]["classification"] == "long_running_diversion"
    assert sent[0]["topicContext"]["conversationId"] == "main"
    assert sent[0]["topicContext"]["agentId"] == "agent-a"
    assert sent[0]["title"] == "上一条问题"
    assert sent[0]["related"]["title"] == "上一条问题"
    assert sent[0]["topicContext"]["title"] == "上一条问题"
    assert sent[0]["sender"] == {"openId": "ou-human"}


def test_here_branch_service_summarizes_context_title_from_previous_record():
    sent = []
    service = HereBranchService(
        records_loader=lambda _context: [
            {
                "event": "turn_completed",
                "sourceMessageId": "om-prev",
                "conversationId": "main",
                "text": (
                    "我的判断：不建议现在一把卖出腾讯，默认更像持有。"
                    "https://example.test/research 如果仓位很重，可以分批减仓。"
                ),
            },
            {"event": "user_message", "sourceMessageId": "om-here", "conversationId": "main", "text": "/here"},
        ],
        notification_sender=lambda intent: sent.append(intent) or {"ok": True, "status": "sent"},
    )
    context = ForegroundCommandContext.create(
        surface="feishu-dm",
        source_message_id="om-here",
        conversation_id="main",
        source_meta={"representativeAgentId": "agent-a"},
    )

    result = service.create_branch(parse_foreground_command("/here"), context)

    assert result["ok"] is True
    assert sent[0]["title"] == "我的判断：不建议现在一把卖出腾讯，默认更像持有。 如果仓位很重，可以分批减仓"
    assert sent[0]["topicContext"]["title"] == sent[0]["title"]
    assert "http" not in sent[0]["title"]


def test_here_branch_service_does_not_send_without_previous_context():
    sent = []
    service = HereBranchService(
        records_loader=lambda _context: [
            {"event": "user_message", "sourceMessageId": "om-here", "conversationId": "main", "text": "/here"},
        ],
        notification_sender=lambda intent: sent.append(intent) or {"ok": True},
    )
    context = ForegroundCommandContext.create(
        surface="feishu-dm",
        source_message_id="om-here",
        conversation_id="main",
        source_meta={"representativeAgentId": "agent-a"},
    )

    result = service.create_branch(parse_foreground_command("/here"), context)

    assert result["ok"] is False
    assert result["status"] == "no_context"
    assert sent == []


def test_here_branch_service_requires_agent_and_conversation_before_sending():
    sent = []
    service = HereBranchService(
        records_loader=lambda _context: [
            {"event": "turn_completed", "sourceMessageId": "om-prev", "conversationId": "main", "text": "上一条问题"},
        ],
        notification_sender=lambda intent: sent.append(intent) or {"ok": True},
    )
    context = ForegroundCommandContext.create(surface="feishu-dm", source_message_id="om-here")

    result = service.create_branch(parse_foreground_command("/here"), context)

    assert result["ok"] is False
    assert result["status"] == "missing_context"
    assert sent == []


def test_here_branch_service_reports_notification_delivery_failure():
    sent = []

    def sender(intent):
        sent.append(intent)
        return {"ok": False, "status": "network_error", "error": "blocked"}

    service = HereBranchService(
        records_loader=lambda _context: [
            {"event": "turn_completed", "sourceMessageId": "om-prev", "conversationId": "main", "text": "上一条问题"},
            {"event": "user_message", "sourceMessageId": "om-here", "conversationId": "main", "text": "/here"},
        ],
        notification_sender=sender,
    )
    context = ForegroundCommandContext.create(
        surface="feishu-dm",
        source_message_id="om-here",
        conversation_id="main",
        source_meta={"representativeAgentId": "agent-a"},
    )

    result = service.create_branch(parse_foreground_command("/here"), context)

    assert result["ok"] is False
    assert result["status"] == "network_error"
    assert result["reply"] == "blocked"
    assert sent and sent[0]["topicContext"]["agentId"] == "agent-a"


def test_here_branch_service_does_not_call_low_level_feishu_senders():
    source = inspect.getsource(foreground_module)

    assert "send_feishu_notification" not in source
    assert "send_feishu_markdown_message" not in source
    assert "send_feishu_text_message" not in source
    assert "_notification_sender" in inspect.getsource(HereBranchService.create_branch)


def test_change_state_access_stays_behind_agent_config_port():
    source = inspect.getsource(FeishuTopicForegroundCommandService._execute_change)

    assert "set_agent(" in source
    assert "get_agent(" in source
    assert "open(" not in source
    assert "json.dump" not in source
