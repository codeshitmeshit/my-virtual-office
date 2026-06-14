import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from feishu_sync import _message_row_to_activity


def test_assistant_reasoning_is_emitted_as_thinking_activity():
    row = {
        "id": 42,
        "role": "assistant",
        "content": "",
        "reasoning": "fallback reasoning",
        "reasoning_content": "真实思考内容",
        "reasoning_details": None,
        "tool_calls": None,
        "tool_call_id": None,
        "tool_name": None,
        "timestamp": 1234.5,
    }

    assert _message_row_to_activity(row) == [{
        "type": "thinking",
        "id": "hermes-msg-42-thinking",
        "message_row_id": 42,
        "text": "真实思考内容",
        "ts": 1234,
    }]


def test_assistant_reasoning_and_tool_call_are_both_emitted():
    row = {
        "id": 43,
        "role": "assistant",
        "content": "",
        "reasoning": "准备调用工具",
        "reasoning_content": None,
        "reasoning_details": None,
        "tool_calls": '[{"id":"call-1","function":{"name":"terminal","arguments":"{\\"command\\":\\"pwd\\"}"}}]',
        "tool_call_id": None,
        "tool_name": None,
        "timestamp": 1235,
    }

    events = _message_row_to_activity(row)

    assert [event["type"] for event in events] == ["thinking", "tool_call"]
    assert events[1]["tool_name"] == "terminal"
    assert events[1]["tool_call_id"] == "call-1"
