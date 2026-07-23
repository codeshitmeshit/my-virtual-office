from __future__ import annotations

import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.codex_workflow_timeline_source import CodexWorkflowTimelineSource, MAX_LIVE_EVENTS
from services.conversation_timeline import ConversationTimelineService, TimelineScope


def make_source(communications=(), activity=()):
    calls = []

    def read_communications(conversation_id, limit):
        calls.append(("durable", conversation_id, limit))
        return communications

    def project_communication(row, agent_id):
        return dict(row)

    def read_activity(agent_id, conversation_id):
        calls.append(("live", agent_id, conversation_id))
        return activity

    source = CodexWorkflowTimelineSource(
        ConversationTimelineService(),
        read_communications,
        project_communication,
        read_activity,
    )
    return source, calls


def scope(conversation="attempt"):
    return TimelineScope.create("codex", "codex-agent", "", conversation)


def test_reasoning_delta_boundary_replace_duplicate_placeholder_and_terminal():
    activity = [
        {"id": "1", "type": "reasoning", "text": "first", "status": "running", "ts": 1, "operationId": "run"},
        {"id": "boundary", "type": "reasoning", "boundary": True, "ts": 2, "operationId": "run"},
        {"id": "2", "type": "reasoning", "text": "second", "ts": 3, "operationId": "run"},
        {"id": "2", "type": "reasoning", "text": "duplicate", "ts": 4, "operationId": "run"},
        {"id": "placeholder", "type": "reasoning", "text": "running", "ts": 5, "operationId": "run"},
        {"id": "3", "type": "reasoning", "replace": True, "text": "final", "status": "completed", "ts": 6, "operationId": "run"},
    ]
    source, calls = make_source(activity=activity)
    messages = source.read_messages(scope())
    assert calls == [("durable", "attempt", 50), ("live", "codex-agent", "attempt")]
    assert messages == [{
        "role": "assistant",
        "text": "",
        "thinking": "final",
        "reasoningStatus": "done",
        "ts": 6,
        "epochMs": 6,
        "fromAgentId": "codex-agent",
        "source": "codex-activity",
    }]


def test_durable_and_transient_records_keep_time_and_tool_order():
    communications = [
        {"role": "assistant", "text": "before", "epochMs": 10, "source": "agent-platform-communications"},
        {"role": "assistant", "text": "after", "epochMs": 30, "tools": [{"name": "read"}], "source": "agent-platform-communications"},
    ]
    activity = [{
        "id": "reasoning",
        "type": "reasoning",
        "text": "between",
        "status": "running",
        "ts": 20,
        "operationId": "run",
    }]
    source, _ = make_source(communications, activity)
    messages = source.read_messages(scope())
    assert [(item["text"], item.get("thinking", "")) for item in messages] == [
        ("before", ""),
        ("", "between"),
        ("after", ""),
    ]
    assert messages[-1]["tools"] == [{"name": "read"}]
    assert messages[1]["reasoningStatus"] == "running"


def test_attempt_isolation_rejects_foreign_durable_and_live_records():
    source, _ = make_source(
        communications=[
            {"conversationId": "other", "role": "assistant", "text": "foreign durable", "epochMs": 1},
            {"conversationId": "attempt", "role": "assistant", "text": "own", "epochMs": 2},
        ],
        activity=[
            {"conversationId": "other", "type": "reasoning", "text": "foreign live", "ts": 3},
            {"conversationId": "attempt", "agentId": "other", "type": "reasoning", "text": "foreign agent", "ts": 4},
        ],
    )
    assert [message["text"] for message in source.read_messages(scope())] == ["own"]


def test_live_event_read_is_bounded_and_non_reasoning_activity_is_not_fabricated():
    inspected = 0

    def events():
        nonlocal inspected
        for index in range(MAX_LIVE_EVENTS + 10):
            inspected += 1
            yield {"id": str(index), "type": "activity", "text": "not reasoning", "ts": index}

    source, _ = make_source(activity=events())
    assert source.read_messages(scope()) == []
    assert inspected == MAX_LIVE_EVENTS

    retained = [
        {"id": str(index), "type": "activity", "ts": index}
        for index in range(MAX_LIVE_EVENTS + 1)
    ]
    retained[-1] = {
        "id": "terminal",
        "type": "reasoning",
        "text": "settled",
        "status": "completed",
        "ts": MAX_LIVE_EVENTS,
    }
    tail_source, _ = make_source(activity=retained)
    assert tail_source.read_messages(scope())[0]["reasoningStatus"] == "done"
