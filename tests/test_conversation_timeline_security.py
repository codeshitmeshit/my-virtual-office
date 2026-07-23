from __future__ import annotations

import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.chat_history_timeline import ChatHistoryTimelineService
from services.conversation_timeline import ConversationTimelineService, TimelineScope
from services.conversation_timeline_public import MAX_VISIBLE_TEXT, sanitize_public_timeline_record
from services.conversation_timeline_sources import project_workflow_history


class Request:
    provider_kind = "codex"
    agent_id = "agent"
    conversation_id = "conversation"
    session_key = ""


def test_public_record_is_allowlisted_bounded_and_redacted_without_mutation():
    source = {
        "id": "message",
        "role": "assistant",
        "text": "visible",
        "nativeTranscript": "private",
        "authorization": "Bearer abcdefghijklmnop",
        "tools": [{
            "id": "tool",
            "name": "read",
            "arguments": {
                "path": "/Users/private/repo/secret.py",
                "token": "sk-abcdefghijklmnop",
                "nested": {"safe": "x"},
            },
            "rawResponse": "private",
        }],
        "attachments": [
            {"name": "safe.txt", "path": "/Users/private/safe.txt", "url": "relative.png", "secret": "drop"},
        ],
    }
    public = sanitize_public_timeline_record(source)
    assert "nativeTranscript" not in public
    assert "authorization" not in public
    assert public["tools"][0]["arguments"]["path"] == "[redacted-path]"
    assert "token" not in public["tools"][0]["arguments"]
    assert "rawResponse" not in public["tools"][0]
    assert public["attachments"] == [{"name": "safe.txt", "url": "relative.png"}]
    assert source["tools"][0]["arguments"]["path"].startswith("/Users/")


def test_visible_content_is_bounded_and_secret_bearing_content_is_redacted():
    assert len(sanitize_public_timeline_record({"text": "x" * (MAX_VISIBLE_TEXT + 1)})["text"]) == MAX_VISIBLE_TEXT
    assert sanitize_public_timeline_record({"thinking": "Bearer abcdefghijklmnop"})["thinking"] == "[redacted]"


def test_standard_history_keeps_its_compatibility_allowlist_and_project_history_uses_public_boundary():
    timeline = ConversationTimelineService()
    standard = ChatHistoryTimelineService(timeline).normalize_message(
        Request(),
        {
            "id": "standard",
            "text": "answer",
            "tools": [{"id": "tool", "arguments": {"authorization": "Bearer abcdefghijklmnop"}}],
            "attachments": [{"name": "one", "path": "/root/private"}],
            "nativeTranscript": "drop",
        },
        source="codex",
    )
    assert standard["tools"][0]["arguments"]["authorization"].startswith("Bearer ")
    assert standard["attachments"] == [{"name": "one", "path": "/root/private"}]
    assert "nativeTranscript" not in standard

    scope = TimelineScope.create("claude-code", "agent", "main", "conversation")
    project = project_workflow_history(
        timeline,
        scope,
        [{
            "id": "project",
            "role": "assistant",
            "text": "answer",
            "conversationId": "conversation",
            "status": "completed",
            "error": "warning",
            "secret": "drop",
            "tools": [{"id": "tool", "arguments": {"path": "/private/file"}}],
        }],
        source="claude-code",
    )[0]
    assert project["status"] == "completed"
    assert project["error"] == "warning"
    assert "secret" not in project
    assert project["tools"][0]["arguments"]["path"] == "[redacted-path]"
