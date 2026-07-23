from __future__ import annotations

import json
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.conversation_timeline import ConversationTimelineService, TimelineScope
from services.openclaw_timeline_source import OpenClawWorkflowTimelineSource, TAIL_BYTES


def resolver(data, agent_id, session_key):
    return data.get(f"agent:{agent_id}:{session_key}") or data.get(session_key)


def make_source(tmp_path, *, key="wf-project-attempt", status="running", session_file="session.jsonl"):
    sessions_dir = tmp_path / "agents" / "agent" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "sessions.json").write_text(
        json.dumps({f"agent:agent:{key}": {"sessionId": "session", "sessionFile": session_file, "status": status}}),
        encoding="utf-8",
    )
    return sessions_dir, OpenClawWorkflowTimelineSource(ConversationTimelineService(), sessions_dir, resolver)


def test_structured_transcript_uses_shared_blocks_and_keeps_tool_summary(tmp_path):
    sessions_dir, source = make_source(tmp_path)
    rows = [
        {"message": {"role": "user", "content": "question", "timestamp": 1}},
        {"message": {"role": "assistant", "content": [
            {"type": "text", "text": "answer"},
            {"type": "reasoning", "text": "checked"},
            {"type": "image", "url": "image.png", "mimeType": "image/png"},
            {"type": "toolCall", "id": "call", "name": "read", "arguments": {"path": "/tmp/file.txt"}},
            {"type": "toolResult", "toolCallId": "call", "result": "done"},
            {"type": "tool_result", "id": "failed", "name": "write", "error": "denied"},
        ], "timestamp": 2}},
    ]
    (sessions_dir / "session.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    scope = TimelineScope.create("openclaw", "agent", "agent", "attempt")
    messages = source.read_messages(scope, "wf-project-attempt")
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assistant = messages[1]
    assert assistant["text"] == "answer"
    assert assistant["thinking"] == "checked"
    assert assistant["reasoningStatus"] == "done"
    assert assistant["media"] == [{"type": "image", "url": "image.png", "mimeType": "image/png"}]
    assert assistant["tools"][0]["name"] == "Reading file.txt"
    assert assistant["tools"][0]["canonicalName"] == "read"
    assert assistant["tools"][0]["result"] == "done"
    assert assistant["tools"][1]["status"] == "error"
    assert source.is_active("agent", "wf-project-attempt") is True


def test_malformed_json_and_non_message_rows_are_ignored(tmp_path):
    sessions_dir, source = make_source(tmp_path)
    (sessions_dir / "session.jsonl").write_text(
        "not-json\n" + json.dumps({"type": "metadata"}) + "\n" + json.dumps({"message": {"role": "assistant", "content": "ok"}}) + "\n",
        encoding="utf-8",
    )
    scope = TimelineScope.create("openclaw", "agent", "agent", "attempt")
    assert [message["text"] for message in source.read_messages(scope, "wf-project-attempt")] == ["ok"]


def test_tail_read_is_bounded_and_drops_partial_old_record(tmp_path):
    sessions_dir, source = make_source(tmp_path)
    old = json.dumps({"message": {"role": "assistant", "content": "old"}}) + "\n"
    padding = "x" * (TAIL_BYTES + 100) + "\n"
    recent = json.dumps({"message": {"role": "assistant", "content": "recent"}}) + "\n"
    (sessions_dir / "session.jsonl").write_text(old + padding + recent, encoding="utf-8")
    scope = TimelineScope.create("openclaw", "agent", "agent", "attempt")
    assert [message["text"] for message in source.read_messages(scope, "wf-project-attempt")] == ["recent"]


def test_session_and_path_isolation_rejects_foreign_attempt_or_file(tmp_path):
    sessions_dir, source = make_source(tmp_path)
    (sessions_dir / "session.jsonl").write_text(json.dumps({"message": {"role": "assistant", "content": "own"}}) + "\n", encoding="utf-8")
    scope = TimelineScope.create("openclaw", "agent", "agent", "attempt")
    assert source.read_messages(scope, "wf-project-other") == []

    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps({"message": {"role": "assistant", "content": "foreign"}}), encoding="utf-8")
    data = json.loads((sessions_dir / "sessions.json").read_text(encoding="utf-8"))
    data["agent:agent:wf-project-attempt"]["sessionFile"] = str(outside)
    (sessions_dir / "sessions.json").write_text(json.dumps(data), encoding="utf-8")
    assert source.read_messages(scope, "wf-project-attempt") == []
