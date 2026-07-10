#!/usr/bin/env python3
"""Contract tests for the provider-neutral chat history page helpers."""

import os
import sys
import tempfile
import json
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-chat-history-test-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")

import server


class ChatHistoryContractTest(unittest.TestCase):
    def require(self, name):
        self.assertTrue(hasattr(server, name), f"server.{name} is missing")
        return getattr(server, name)

    def test_utf8_fnv1a_vectors(self):
        history_hash = self.require("_chat_history_hash")
        self.assertEqual(history_hash(""), "811c9dc5")
        self.assertEqual(history_hash("hello"), "4f9f2cab")
        self.assertEqual(history_hash("聊天历史"), "2b992da3")
        self.assertEqual(history_hash("codex\x1fagent\x1fconv"), "4fe64f31")

    def test_cursor_round_trip_preserves_sort_tuple(self):
        encode = self.require("_encode_chat_history_cursor")
        decode = self.require("_decode_chat_history_cursor")
        cursor = encode(1720000000123, "message-42")
        self.assertNotIn("message-42", cursor)
        self.assertEqual(decode(cursor), (1720000000123, "message-42"))

    def test_invalid_cursor_has_stable_error_code(self):
        decode = self.require("_decode_chat_history_cursor")
        error_type = self.require("_ChatHistoryRequestError")
        with self.assertRaises(error_type) as caught:
            decode("not-a-cursor")
        self.assertEqual(caught.exception.code, "invalid_chat_history_cursor")
        self.assertEqual(caught.exception.status, 400)

    def test_request_validation_and_limit_clamping(self):
        parse = self.require("_parse_chat_history_request")
        request = parse({
            "providerKind": ["codex"],
            "agentId": ["codex-local"],
            "conversationId": ["conv-1"],
            "limit": ["500"],
        })
        self.assertEqual(request.provider_kind, "codex")
        self.assertEqual(request.agent_id, "codex-local")
        self.assertEqual(request.conversation_id, "conv-1")
        self.assertEqual(request.limit, 50)
        self.assertEqual(request.before, None)
        self.assertEqual(request.key, "codex\x1fcodex-local\x1fconv-1")

        minimum = parse({
            "providerKind": ["gateway"],
            "agentId": ["main"],
            "sessionKey": ["agent:main:main"],
            "limit": ["0"],
        })
        self.assertEqual(minimum.limit, 1)

    def test_request_rejects_provider_and_identifier_overflow(self):
        parse = self.require("_parse_chat_history_request")
        error_type = self.require("_ChatHistoryRequestError")
        with self.assertRaises(error_type) as provider_error:
            parse({"providerKind": ["unknown"], "agentId": ["main"]})
        self.assertEqual(provider_error.exception.code, "invalid_chat_history_request")

        with self.assertRaises(error_type) as agent_error:
            parse({"providerKind": ["gateway"], "agentId": ["a" * 161]})
        self.assertEqual(agent_error.exception.code, "invalid_chat_history_request")

        with self.assertRaises(error_type):
            parse({
                "providerKind": ["codex"],
                "agentId": ["codex-local"],
                "conversationId": ["c" * 257],
            })

        with self.assertRaises(error_type):
            parse({
                "providerKind": ["gateway"],
                "agentId": ["main"],
                "sessionKey": ["s" * 513],
            })

    def request(self, provider="codex", before=""):
        query = {
            "providerKind": [provider],
            "agentId": [f"{provider}-local" if provider != "gateway" else "main"],
            "limit": ["2"],
        }
        if provider == "gateway":
            query["sessionKey"] = ["agent:main:main"]
        else:
            query["conversationId"] = ["conv-1"]
        if before:
            query["before"] = [before]
        return self.require("_parse_chat_history_request")(query)

    def test_normalizes_rich_gateway_content(self):
        normalize = self.require("_normalize_chat_history_message")
        request = self.request("gateway")
        message = normalize(request, {
            "id": "entry-1",
            "timestamp": "2026-07-10T05:00:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hello **world**"},
                    {"type": "image", "url": "/tmp/image.png", "mimeType": "image/png"},
                    {"type": "toolCall", "id": "call-1", "name": "read", "arguments": {"path": "a.txt"}},
                    {"type": "toolResult", "toolCallId": "call-1", "result": "done"},
                ],
            },
        }, source="gateway")
        self.assertEqual(message["id"], "entry-1")
        self.assertEqual(message["role"], "assistant")
        self.assertEqual(message["text"], "hello **world**")
        self.assertEqual(message["media"][0]["url"], "/tmp/image.png")
        self.assertEqual(message["tools"][0]["id"], "call-1")
        self.assertEqual(message["tools"][0]["result"], "done")
        self.assertTrue(message["version"])

    def test_merge_pages_returns_newest_then_older_without_duplicates(self):
        normalize = self.require("_normalize_chat_history_message")
        merge = self.require("_merge_chat_history_source_pages")
        request = self.request("codex")
        rows = [normalize(request, {
            "id": f"m-{index}", "role": "assistant", "text": f"message {index}", "epochMs": index,
        }, source="codex") for index in range(1, 6)]
        latest, cursor, has_more = merge([
            {"messages": rows, "hasMore": False},
            {"messages": [rows[-1]], "hasMore": False},
        ], None, 2)
        self.assertEqual([item["id"] for item in latest], ["m-4", "m-5"])
        self.assertTrue(has_more)
        self.assertTrue(cursor)
        older_before = self.require("_decode_chat_history_cursor")(cursor)
        older, _, older_has_more = merge([{"messages": rows, "hasMore": False}], older_before, 2)
        self.assertEqual([item["id"] for item in older], ["m-2", "m-3"])
        self.assertTrue(older_has_more)

    def test_communication_copy_wins_dedupe(self):
        normalize = self.require("_normalize_chat_history_message")
        merge = self.require("_merge_chat_history_source_pages")
        request = self.request("hermes")
        provider = normalize(request, {
            "id": "shared", "role": "assistant", "text": "provider", "epochMs": 5,
        }, source="hermes")
        communication = normalize(request, {
            "id": "shared", "role": "assistant", "text": "communication", "epochMs": 5,
            "fromAgentId": "hermes-local", "toAgentId": "user",
        }, source="agent-platform-communications")
        page, _, _ = merge([
            {"messages": [provider], "hasMore": False},
            {"messages": [communication], "hasMore": False},
        ], None, 50)
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0]["text"], "communication")

    def test_handler_returns_page_and_session_for_every_provider(self):
        handle = self.require("_handle_chat_history_page")
        for provider in ("codex", "hermes", "claude-code", "gateway"):
            request = self.request(provider)
            message = self.require("_normalize_chat_history_message")(request, {
                "id": provider, "role": "assistant", "text": provider, "epochMs": 1,
            }, source=provider)
            query = {
                "providerKind": [provider],
                "agentId": [request.agent_id],
                "limit": ["2"],
            }
            if provider == "gateway":
                query["sessionKey"] = [request.session_key]
            else:
                query["conversationId"] = [request.conversation_id]
            with mock.patch.object(server, "_load_chat_history_source_pages", return_value=(
                [{"messages": [message], "hasMore": False}],
                {"sessionId": "session-1", "contextUsed": 10, "contextWindow": 100, "tokenUsage": {}},
            )):
                result = handle(query)
            self.assertTrue(result["ok"])
            self.assertEqual(result["messages"][0]["id"], provider)
            self.assertEqual(result["session"]["contextUsed"], 10)

    def test_jsonl_snapshot_cache_invalidates_and_is_thread_safe(self):
        load = self.require("_load_cached_chat_history_jsonl")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"id": "one"}) + "\n")
            self.assertEqual([row["id"] for row in load(path, "fixture", 1000)], ["one"])
            with open(path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"id": "two"}) + "\n")
            os.utime(path, None)
            self.assertEqual([row["id"] for row in load(path, "fixture", 1000)], ["one", "two"])

            results = []
            threads = [threading.Thread(target=lambda: results.append(load(path, "fixture", 1000))) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(results), 8)
            self.assertTrue(all(len(rows) == 2 for rows in results))

    def test_gateway_page_reads_exact_session_without_truncating(self):
        page_gateway = self.require("_page_openclaw_session_history")
        request = self.request("gateway")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "session.jsonl")
            long_text = "x" * 2500
            with open(path, "w", encoding="utf-8") as stream:
                for index in range(3):
                    stream.write(json.dumps({
                        "id": f"gateway-{index}",
                        "type": "message",
                        "timestamp": f"2026-07-10T05:00:0{index}Z",
                        "message": {"role": "assistant", "content": [{"type": "text", "text": long_text + str(index)}]},
                    }) + "\n")
            with mock.patch.object(server, "_openclaw_session_paths", return_value=(path, None, {"sessionId": "session-1"})):
                page = page_gateway(request, 3)
        self.assertEqual(len(page["messages"]), 3)
        self.assertGreater(len(page["messages"][-1]["text"]), 2500)

    def test_source_cache_limits_are_explicit(self):
        self.assertEqual(self.require("_CHAT_HISTORY_SOURCE_CACHE_ENTRY_LIMIT"), 32)
        self.assertEqual(self.require("_CHAT_HISTORY_SOURCE_CACHE_BYTE_LIMIT"), 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main(verbosity=2)
