import threading
import time
import unittest

from app.services.provider_events import CANONICAL_EVENTS, ProviderEventJournal, canonical_event_name


class ProviderEventJournalTests(unittest.TestCase):
    def test_zero_and_one_event_queries(self):
        journal = ProviderEventJournal()
        self.assertEqual(journal.events_after(), [])
        item = journal.publish("codex", "agent", "conv", "run.started", {"status": "running"}, "run")
        self.assertEqual(item["id"], 1)
        self.assertEqual(journal.run_events_after("run", 0), [item])
        copy_item = journal.run_events_after("run", 0)[0]
        copy_item["data"]["status"] = "mutated"
        self.assertEqual(journal.run_events_after("run", 0)[0]["data"]["status"], "running")

    def test_4000_and_4001_eviction_keeps_indexes_consistent(self):
        journal = ProviderEventJournal(max_events=4000)
        for index in range(4001):
            journal.publish("codex", "agent", f"conv-{index % 2}", "message.delta", {"index": index}, f"run-{index % 3}")
        self.assertEqual(journal.stats()["retainedEvents"], 4000)
        self.assertEqual(journal.events_after(0)[0]["id"], 2)
        run_events = journal.run_events_after("run-0")
        self.assertTrue(all(item["id"] >= 2 and item["runId"] == "run-0" for item in run_events))
        conversation_events = journal.conversation_events_after("codex", "agent", "conv-0")
        self.assertTrue(all(item["id"] >= 2 and item["conversationId"] == "conv-0" for item in conversation_events))

    def test_terminal_event_is_deduped_and_canceled_alias_is_canonical(self):
        journal = ProviderEventJournal()
        first = journal.publish("codex", "agent", "conv", "run.canceled", {"status": "cancelled"}, "run")
        second = journal.publish("codex", "agent", "conv", "run.completed", {"ok": True}, "run")
        self.assertEqual(canonical_event_name("run.canceled"), "run.cancelled")
        self.assertEqual(first, second)
        self.assertEqual([item["event"] for item in journal.run_events_after("run")], ["run.cancelled"])

    def test_terminal_dedupe_survives_event_eviction_with_bounded_markers(self):
        journal = ProviderEventJournal(max_events=4)
        journal.publish("codex", "agent", "conv", "run.completed", {"ok": True}, "terminal-run")
        for index in range(4):
            journal.publish("codex", "agent", "conv", "message.delta", {"index": index}, f"run-{index}")
        self.assertEqual(journal.stats()["retainedEvents"], 4)
        self.assertEqual(journal.run_events_after("terminal-run"), [])
        duplicate = journal.publish("codex", "agent", "conv", "run.failed", {"ok": False}, "terminal-run")
        self.assertIsNone(duplicate)
        self.assertEqual(journal.next_event_id, 5)
        self.assertLessEqual(journal.stats()["terminalRuns"], 4)

    def test_frozen_event_aliases_are_preserved(self):
        required = {
            "approval.request", "clarify.request", "message.delta.text", "reasoning.delta",
            "run.native.started", "run.queued", "run.running", "run.stop_requested",
            "session.active_list", "session.create", "session.message", "session.resume", "session.tool",
            "sudo.request", "secret.request", "tool.call.start", "tool.generating", "tool.updated",
        }
        self.assertTrue(required.issubset(CANONICAL_EVENTS))
        for name in required:
            self.assertEqual(canonical_event_name(name), name)

    def test_malformed_oversized_and_sensitive_payloads_are_bounded(self):
        journal = ProviderEventJournal()
        item = journal.publish("codex", "agent", "conv", "unknown.native.event", {
            "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
            "api_key": "sk-abcdefghijklmnop",
            "path": "/Users/private/work/secret.txt",
            "embeddedPath": "failure at /Users/private/work/secret.txt",
            "text": "x" * 9000,
            "items": list(range(500)),
            "bad key": "drop",
            "nested": {"prompt": "private", "ok": "visible"},
        }, "run")
        self.assertEqual(item["event"], "provider.activity")
        data = item["data"]
        self.assertNotIn("authorization", data)
        self.assertNotIn("api_key", data)
        self.assertNotIn("bad key", data)
        self.assertNotIn("prompt", data["nested"])
        self.assertEqual(data["path"], "[redacted-path]")
        self.assertEqual(data["embeddedPath"], "[redacted-path]")
        self.assertLessEqual(len(data["text"]), 8192)
        self.assertEqual(len(data["items"]), 200)
        malformed = journal.publish("codex", "agent", "conv", "message.delta", "not-a-dict", "run-2")
        self.assertEqual(malformed["data"]["runId"], "run-2")

    def test_conversation_index_includes_unscoped_provider_events(self):
        journal = ProviderEventJournal()
        journal.publish("hermes", "agent", "", "provider.activity", {"kind": "global"})
        journal.publish("hermes", "agent", "conv", "message.delta", {"kind": "local"})
        self.assertEqual([item["data"]["kind"] for item in journal.conversation_events_after("hermes", "agent", "conv")], ["global", "local"])

    def test_wait_queries_wake_without_http_or_sse_types(self):
        journal = ProviderEventJournal()
        result = []

        def wait():
            result.extend(journal.wait_for_run_events("run", 0, timeout=1))

        thread = threading.Thread(target=wait)
        thread.start()
        time.sleep(0.01)
        journal.publish("codex", "agent", "conv", "run.started", {}, "run")
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]["event"], "run.started")

    def test_parallel_publish_has_global_monotonic_ids(self):
        journal = ProviderEventJournal()
        threads = [threading.Thread(target=journal.publish, args=("codex", f"agent-{i}", f"conv-{i}", "run.started", {"i": i}, f"run-{i}")) for i in range(100)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([item["id"] for item in journal.events_after()], list(range(1, 101)))


if __name__ == "__main__":
    unittest.main()
