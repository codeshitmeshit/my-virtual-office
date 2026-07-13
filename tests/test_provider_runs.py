import threading
import time
import unittest

from app.services.provider_events import ProviderEventJournal
from app.services.provider_ports import AdapterCapabilities, AdapterEvent, AdapterResult, ProviderAdapterRegistry, RunCommand
from app.services.provider_registry import ProviderRunRepository
from app.services.provider_runs import ProviderRunCoordinator


class FakeAdapter:
    provider_kind = "codex"
    provider_path = "fake"
    capabilities = AdapterCapabilities(background_run=True, streaming_events=True, cancel=True)

    def __init__(self, *, delay=0, result=None, fail=None):
        self.delay = delay
        self.result = result or {"ok": True, "status": "completed", "reply": "done"}
        self.fail = fail
        self.launches = 0
        self.cancels = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, command, emit, cancel_event):
        self.launches += 1
        self.started.set()
        emit(AdapterEvent("message.delta", {"delta": "part"}, {"turnId": "turn-1"}))
        if self.delay:
            self.release.wait(self.delay)
        if self.fail:
            raise self.fail
        return AdapterResult(self.result, {"reply": self.result.get("reply", ""), "status": self.result.get("status", "")})

    def cancel(self, command, snapshot, payload):
        self.cancels += 1
        self.release.set()
        return {"ok": True, "status": "cancelled", "providerPath": self.provider_path}


class ProviderRunCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.repo = ProviderRunRepository()
        self.journal = ProviderEventJournal()
        self.registry = ProviderAdapterRegistry()
        self.adapter = FakeAdapter()
        self.registry.register(self.adapter)
        self.coordinator = ProviderRunCoordinator(self.repo, self.journal, self.registry)

    def command(self, **values):
        defaults = {"provider_kind": "codex", "provider_path": "fake", "agent_id": "agent", "conversation_id": "conv", "idempotency_key": "key", "timeout_sec": 1}
        defaults.update(values)
        return RunCommand(**defaults)

    def wait_terminal(self, run_id, timeout=2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            snapshot = self.repo.get(run_id)
            if snapshot and snapshot.get("terminal"):
                return snapshot
            time.sleep(0.005)
        self.fail("run did not become terminal")

    def test_fake_adapter_progress_and_completion(self):
        outcome = self.coordinator.start(self.command())
        snapshot = self.wait_terminal(outcome.run_id)
        self.assertEqual(snapshot["result"]["reply"], "done")
        self.assertEqual(snapshot["turnId"], "turn-1")
        self.assertEqual([item["event"] for item in self.journal.run_events_after(outcome.run_id)], ["run.started", "message.delta", "run.completed"])

    def test_concurrent_duplicate_starts_launch_adapter_once(self):
        self.adapter.delay = 1
        barrier = threading.Barrier(11)
        outcomes = []

        def start():
            barrier.wait()
            outcomes.append(self.coordinator.start(self.command()))

        threads = [threading.Thread(target=start) for _ in range(10)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(len({item.run_id for item in outcomes}), 1)
        self.assertEqual(sum(not item.duplicate for item in outcomes), 1)
        self.adapter.release.set()
        self.wait_terminal(outcomes[0].run_id)
        self.assertEqual(self.adapter.launches, 1)

    def test_different_scopes_run_in_parallel_without_repository_locking_adapter(self):
        adapters = []
        outcomes = []
        for index in range(20):
            adapter = FakeAdapter(delay=1)
            adapters.append(adapter)
            outcomes.append(self.coordinator.start(self.command(agent_id=f"agent-{index}", idempotency_key="same"), adapter=adapter))
        self.assertTrue(all(adapter.started.wait(0.5) for adapter in adapters))
        started = time.perf_counter()
        self.repo.snapshots()
        self.assertLess(time.perf_counter() - started, 0.05)
        for adapter in adapters:
            adapter.release.set()
        for outcome in outcomes:
            self.wait_terminal(outcome.run_id)

    def test_adapter_failure_is_bounded_and_terminal(self):
        adapter = FakeAdapter(fail=RuntimeError("failure with sk-abcdefghijklmnop and /Users/private/file"))
        outcome = self.coordinator.start(self.command(idempotency_key="failure"), adapter=adapter)
        snapshot = self.wait_terminal(outcome.run_id)
        self.assertEqual(snapshot["result"]["status"], "execution_failed")
        self.assertNotIn("sk-", snapshot["result"]["error"])
        self.assertNotIn("/Users/", snapshot["result"]["error"])
        self.assertEqual(self.journal.run_events_after(outcome.run_id)[-1]["event"], "run.failed")

    def test_targeted_failure_does_not_disable_unrelated_provider_scope(self):
        failed = self.coordinator.start(
            self.command(provider_kind="codex", agent_id="bad", idempotency_key="bad"),
            adapter=FakeAdapter(fail=ValueError("malformed response")),
        )
        healthy_adapter = FakeAdapter(result={"ok": True, "status": "completed", "reply": "healthy"})
        healthy_adapter.provider_kind = "hermes"
        healthy_adapter.provider_path = "api"
        healthy = self.coordinator.start(
            self.command(provider_kind="hermes", provider_path="api", agent_id="good", conversation_id="other", idempotency_key="good"),
            adapter=healthy_adapter,
        )
        failed_snapshot = self.wait_terminal(failed.run_id)
        healthy_snapshot = self.wait_terminal(healthy.run_id)
        self.assertEqual(failed_snapshot["result"]["status"], "execution_failed")
        self.assertEqual(healthy_snapshot["result"]["reply"], "healthy")
        self.assertEqual(self.journal.run_events_after(failed.run_id)[-1]["event"], "run.failed")
        self.assertEqual(self.journal.run_events_after(healthy.run_id)[-1]["event"], "run.completed")

    def test_timeout_cancels_once_and_late_result_is_fenced(self):
        adapter = FakeAdapter(delay=1)
        outcome = self.coordinator.start(self.command(idempotency_key="timeout", timeout_sec=0.02), adapter=adapter)
        snapshot = self.wait_terminal(outcome.run_id)
        self.assertEqual(snapshot["result"]["status"], "timeout")
        deadline = time.time() + 0.5
        while adapter.cancels != 1 and time.time() < deadline:
            time.sleep(0.005)
        self.assertEqual(adapter.cancels, 1)
        adapter.release.set()
        time.sleep(0.03)
        self.assertEqual(self.repo.get(outcome.run_id)["result"]["status"], "timeout")
        self.assertEqual(len([item for item in self.journal.run_events_after(outcome.run_id) if item["event"].startswith("run.") and item["event"] != "run.started"]), 1)

    def test_timeout_terminal_does_not_wait_for_blocking_cancel_hook(self):
        adapter = FakeAdapter(delay=1)
        cancel_release = threading.Event()

        def blocking_cancel(command, snapshot, payload):
            adapter.cancels += 1
            cancel_release.wait(1)
            adapter.release.set()
            return {"ok": True, "status": "cancelled"}

        adapter.cancel = blocking_cancel
        started = time.perf_counter()
        outcome = self.coordinator.start(self.command(idempotency_key="blocking-timeout", timeout_sec=0.02), adapter=adapter)
        snapshot = self.wait_terminal(outcome.run_id, timeout=0.2)
        elapsed = time.perf_counter() - started
        self.assertEqual(snapshot["result"]["status"], "timeout")
        self.assertLess(elapsed, 0.2)
        cancel_release.set()

    def test_cancel_and_complete_race_has_one_terminal_and_one_cancel_call(self):
        adapter = FakeAdapter(delay=1)
        outcome = self.coordinator.start(self.command(idempotency_key="cancel"), adapter=adapter)
        self.assertTrue(adapter.started.wait(0.5))
        results = []
        barrier = threading.Barrier(3)

        def cancel():
            barrier.wait()
            results.append(self.coordinator.cancel(outcome.run_id))

        threads = [threading.Thread(target=cancel), threading.Thread(target=cancel)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        snapshot = self.wait_terminal(outcome.run_id)
        self.assertEqual(adapter.cancels, 1)
        self.assertIn(snapshot["result"]["status"], {"completed", "cancelled"})
        terminals = [item for item in self.journal.run_events_after(outcome.run_id) if item["event"] in {"run.completed", "run.failed", "run.cancelled"}]
        self.assertEqual(len(terminals), 1)

    def test_unsupported_adapter_does_not_reserve_partial_state(self):
        with self.assertRaises(LookupError):
            self.coordinator.start(self.command(provider_path="missing"))
        self.assertEqual(self.repo.snapshots(), {})

    def test_explicit_adapter_without_background_capability_is_rejected_before_reservation(self):
        adapter = FakeAdapter()
        adapter.capabilities = AdapterCapabilities(background_run=False)
        with self.assertRaises(ValueError):
            self.coordinator.start(self.command(idempotency_key="unsupported-capability"), adapter=adapter)
        self.assertEqual(self.repo.snapshots(), {})

    def test_cancel_failure_becomes_failed_terminal_not_cancelled(self):
        adapter = FakeAdapter(delay=1)
        adapter.cancel = lambda command, snapshot, payload: {"ok": False, "status": "cancel_failed", "error": "stop unavailable", "_status": 500}
        outcome = self.coordinator.start(self.command(idempotency_key="cancel-failure"), adapter=adapter)
        self.assertTrue(adapter.started.wait(0.5))
        cancelled = self.coordinator.cancel(outcome.run_id)
        adapter.release.set()
        self.assertFalse(cancelled.result["ok"])
        snapshot = self.wait_terminal(outcome.run_id)
        self.assertEqual(snapshot["result"]["status"], "cancel_failed")
        terminals = [item["event"] for item in self.journal.run_events_after(outcome.run_id) if item["event"] in {"run.completed", "run.failed", "run.cancelled"}]
        self.assertEqual(terminals, ["run.failed"])

    def test_duplicate_completed_returns_existing_result_without_launch(self):
        first = self.coordinator.start(self.command(idempotency_key="completed"))
        self.wait_terminal(first.run_id)
        duplicate = self.coordinator.start(self.command(idempotency_key="completed"))
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(duplicate.snapshot["result"]["reply"], "done")
        self.assertEqual(self.adapter.launches, 1)

    def test_diagnostics_are_bounded_and_digest_run_ids(self):
        adapter = FakeAdapter(delay=1)
        outcome = self.coordinator.start(self.command(idempotency_key="diagnostic"), adapter=adapter)
        self.assertTrue(adapter.started.wait(0.5))
        diagnostics = self.coordinator.diagnostics()
        self.assertEqual(diagnostics["activeHandleCount"], 1)
        self.assertNotIn(outcome.run_id, diagnostics["activeRunDigests"])
        self.assertEqual(len(diagnostics["activeRunDigests"][0]), 12)
        adapter.release.set()
        self.wait_terminal(outcome.run_id)


if __name__ == "__main__":
    unittest.main()
