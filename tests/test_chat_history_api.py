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

    def test_html_entrypoint_revalidates_cached_asset_versions(self):
        handler = object.__new__(server.OfficeHandler)
        handler.path = "/"
        handler.send_header = mock.Mock()
        with mock.patch.object(server.http.server.SimpleHTTPRequestHandler, "end_headers"):
            handler.end_headers()
        handler.send_header.assert_any_call("Cache-Control", "no-cache")

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

    def test_feishu_image_history_keeps_one_attachment_and_hides_transport_details(self):
        normalize = self.require("_normalize_chat_history_message")
        request = self.request("codex")
        path = "/private/vo/feishu-chat-attachments/resource-12345678-1234-1234-1234-123456789abc.jpg"
        attachment = {
            "type": "image",
            "fileKey": "img_v3_example",
            "name": "resource-12345678-1234-1234-1234-123456789abc.jpg",
            "path": path,
            "mimeType": "image/jpeg",
        }
        message = normalize(request, {
            "id": "feishu-image",
            "direction": "request",
            "text": (
                "![image](img_v3_example)\n他在说什么\n\n"
                "图片附件已同步到 VO。\n"
                f"文件名：{attachment['name']}\n本地路径：{path}"
            ),
            "attachments": [attachment],
            "metadata": {"sourceApp": "feishu", "messageType": "image"},
        }, source="agent-platform-communications")

        self.assertEqual(message["text"], "他在说什么")
        self.assertEqual(message["media"], [])
        self.assertEqual(message["attachments"], [attachment])

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

    def test_communication_direction_infers_user_and_assistant_roles(self):
        normalize = self.require("_normalize_chat_history_message")
        request = self.request("codex")
        user_message = normalize(request, {
            "id": "request-1",
            "direction": "request",
            "from": {"id": "user", "name": "User", "providerKind": "human"},
            "to": {"id": "codex-local", "name": "Codex", "providerKind": "codex"},
            "text": "hello",
            "ts": 1,
        }, source="agent-platform-communications")
        assistant_message = normalize(request, {
            "id": "reply-1",
            "direction": "reply",
            "from": {"id": "codex-local", "name": "Codex", "providerKind": "codex"},
            "to": {"id": "user", "name": "User", "providerKind": "human"},
            "text": "hi",
            "ts": 2,
        }, source="agent-platform-communications")
        self.assertEqual(user_message["role"], "user")
        self.assertEqual(assistant_message["role"], "assistant")

    def test_communication_history_exposes_idempotency_key_for_optimistic_reconciliation(self):
        normalize = self.require("_normalize_chat_history_message")
        request = self.request("codex")
        message = normalize(request, {
            "id": "request-optimistic",
            "direction": "request",
            "from": {"id": "user", "providerKind": "human"},
            "to": {"id": "codex-local", "providerKind": "codex"},
            "text": "same text",
            "ts": 10,
            "metadata": {"idempotencyKey": "office-exact-request"},
        }, source="agent-platform-communications")
        self.assertEqual(message["idempotencyKey"], "office-exact-request")
        self.assertIn("idempotencyKey", message)

    def test_codex_user_communication_is_idempotent_across_run_fallback(self):
        old_status_dir = server.STATUS_DIR
        old_roster = server.get_roster
        agent = {
            "id": "codex-local",
            "statusKey": "codex-local",
            "providerAgentId": "local",
            "providerKind": "codex",
            "name": "Codex",
        }
        with tempfile.TemporaryDirectory() as status_dir:
            server.STATUS_DIR = status_dir
            server.get_roster = lambda: [agent]
            body = {
                "fromType": "human",
                "fromDisplayName": "User",
                "sourceApp": "virtual-office",
                "sourceSurface": "chat-window",
                "idempotencyKey": "office-run-fallback-same-request",
            }
            try:
                with mock.patch.object(server, "_publish_feishu_chat_comm_event"):
                    first = server._append_codex_user_comm_event(agent, "codex-local", "conv", "你好", body)
                    fallback = server._append_codex_user_comm_event(agent, "codex-local", "conv", "你好", body)
                self.assertEqual(fallback["id"], first["id"])
                history = server._load_comm_history(limit=20, conversation_id="conv", agent_id="codex-local")
                requests = [row for row in history if row.get("direction") == "request"]
                self.assertEqual(len(requests), 1)
            finally:
                server.STATUS_DIR = old_status_dir
                server.get_roster = old_roster

    def test_comm_history_includes_only_selected_agent_feishu_cross_conversation(self):
        request = self.request("codex")
        matches = self.require("_chat_history_comm_event_matches")

        def event(event_id, conversation_id, source_app="virtual-office", agent_id="codex-local", **extra):
            row = {
                "id": event_id,
                "type": "message",
                "conversationId": conversation_id,
                "from": {"id": "user", "providerKind": "human", "sourceApp": source_app},
                "to": {"id": agent_id, "providerKind": "codex"},
                "metadata": {"sourceApp": source_app},
                "visibleInOffice": True,
            }
            row.update(extra)
            return row

        self.assertTrue(matches(request, event("same", "conv-1")))
        self.assertTrue(matches(request, event("feishu", "feishu-dm:one", source_app="feishu")))
        self.assertTrue(matches(request, event("feishu-metadata", "external", source_app="feishu")))
        self.assertFalse(matches(request, event("other-agent", "feishu-dm:two", source_app="feishu", agent_id="codex-other")))
        self.assertFalse(matches(request, event("other-conversation", "conv-2")))
        self.assertFalse(matches(request, event(
            "delivery", "feishu-dm:one", source_app="feishu",
            type="operation", operation="feishu_delivery",
        )))
        self.assertFalse(matches(request, event("hidden", "feishu-dm:one", source_app="feishu", visibleInOffice=False)))

    def test_comm_history_page_merges_feishu_rows_with_stable_pagination(self):
        request = self.request("codex")
        rows = [
            {
                "id": "same-conversation", "type": "message", "direction": "request",
                "conversationId": "conv-1", "from": {"id": "user", "providerKind": "human"},
                "to": {"id": "codex-local", "providerKind": "codex"}, "text": "same", "ts": 1,
            },
            {
                "id": "feishu-request", "type": "message", "direction": "request",
                "conversationId": "feishu-dm:one", "from": {"id": "user", "providerKind": "human", "sourceApp": "feishu"},
                "to": {"id": "codex-local", "providerKind": "codex"}, "metadata": {"sourceApp": "feishu"},
                "text": "from feishu", "ts": 2,
            },
            {
                "id": "feishu-reply", "type": "message", "direction": "reply",
                "conversationId": "feishu-dm:one", "from": {"id": "codex-local", "providerKind": "codex"},
                "to": {"id": "user", "providerKind": "human", "sourceApp": "feishu"}, "metadata": {"channel": "feishu"},
                "text": "to feishu", "ts": 3,
            },
            {
                "id": "unrelated", "type": "message", "direction": "request",
                "conversationId": "conv-2", "from": {"id": "user", "providerKind": "human"},
                "to": {"id": "codex-local", "providerKind": "codex"}, "text": "unrelated", "ts": 4,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "communications.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")
            with mock.patch.object(server, "_comm_log_path", return_value=path):
                page = self.require("_chat_history_comm_page")(request, 3)
        self.assertEqual([row["id"] for row in page["messages"]], [
            "same-conversation", "feishu-request", "feishu-reply",
        ])
        self.assertFalse(page["hasMore"])
        self.assertEqual([row["epochMs"] for row in page["messages"]], [1000, 2000, 3000])

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

    def test_codex_provider_history_is_isolated_by_conversation(self):
        request = self.request("codex")
        rows = [
            {"id": "current", "role": "assistant", "text": "current", "ts": 3, "conversationId": "conv-1"},
            {"id": "other", "role": "assistant", "text": "other", "ts": 2, "conversationId": "conv-2"},
            {"id": "legacy", "role": "assistant", "text": "legacy", "ts": 1},
        ]
        with mock.patch.object(server, "_get_codex_agent", return_value={"profile": "local"}), \
             mock.patch.object(server, "_load_codex_history", return_value=rows), \
             mock.patch.object(server, "_chat_history_comm_page", return_value={"messages": [], "hasMore": False}), \
             mock.patch.object(server, "_history_session_metrics", return_value={}):
            pages, _ = self.require("_load_chat_history_source_pages")(request)
        self.assertEqual([message["id"] for message in pages[0]["messages"]], ["current"])

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
