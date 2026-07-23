#!/usr/bin/env python3
"""Emit a content-free standard-chat compatibility snapshot for one app tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_dir.resolve()))
    os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-standard-chat-snapshot-")
    os.environ["VO_HERMES_ENABLED"] = "0"
    os.environ["VO_CODEX_ENABLED"] = "0"
    import server

    observations = []
    for provider in ("codex", "claude-code", "hermes", "gateway"):
        query = {"providerKind": [provider], "agentId": [f"{provider}-agent"], "limit": ["2"]}
        if provider == "gateway":
            query["sessionKey"] = ["agent:gateway-agent:fixture"]
        else:
            query["conversationId"] = ["conversation-fixture"]
        request = server._parse_chat_history_request(query)
        conversation = request.conversation_id or request.session_key
        rich = server._normalize_chat_history_message(
            request,
            {
                "id": f"{provider}-rich",
                "role": "assistant",
                "timestamp": "2026-07-10T05:00:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "fixture answer"},
                        {"type": "image", "url": "fixture.png", "mimeType": "image/png"},
                        {"type": "toolCall", "id": "call", "name": "read", "arguments": {"path": "fixture"}},
                        {"type": "toolResult", "toolCallId": "call", "result": "done"},
                    ]
                },
                "attachments": [{"type": "file", "name": "fixture.txt"}],
                "thinking": "provider supplied reasoning",
                "reasoningTokens": 7,
                "approval": {"id": "approval", "status": "pending"},
                "status": "done",
                "idempotencyKey": "fixture-key",
            },
            source=provider,
        )
        rows = [
            server._normalize_chat_history_message(
                request,
                {"id": f"{provider}-{index}", "role": "assistant", "text": f"item-{index}", "epochMs": index},
                source=provider,
            )
            for index in range(1, 6)
        ]
        provider_copy = dict(rows[-1])
        communication_copy = {**rows[-1], "text": "communication copy", "source": "agent-platform-communications"}
        messages, cursor, has_more = server._merge_chat_history_source_pages(
            [
                {"messages": rows, "hasMore": False},
                {"messages": [communication_copy], "hasMore": False},
            ],
            None,
            2,
        )
        observations.append(
            {
                "id": f"standard-chat-{provider}",
                "provider": "openclaw" if provider == "gateway" else provider,
                "surface": "standard-chat",
                "dimension": "history",
                "values": {
                    "dtoFields": sorted(rich),
                    "richDigest": digest(rich),
                    "messageCount": len(messages),
                    "orderDigest": digest([item["id"] for item in messages]),
                    "winnerSource": messages[-1]["source"],
                    "winnerDigest": digest(messages[-1]),
                    "hasMore": has_more,
                    "cursorRoundTrip": list(server._decode_chat_history_cursor(cursor)),
                    "conversationDigest": digest(conversation),
                    "pageLimit": request.limit,
                },
            }
        )
    print(json.dumps({"schema": 1, "contentPolicy": "content-free", "observations": observations}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
