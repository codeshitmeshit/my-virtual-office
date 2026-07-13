import threading
import unittest

from app.services.provider_registry import ProviderRunRepository


class Clock:
    def __init__(self, value=1_000):
        self.value = value

    def __call__(self):
        return self.value


class ProviderRunRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.ids = iter(f"id-{index}" for index in range(1000))
        self.repo = ProviderRunRepository(clock_ms=self.clock, id_factory=lambda: next(self.ids))

    def reserve(self, **overrides):
        values = {"provider_kind": "codex", "agent_id": "agent", "conversation_id": "conv", "idempotency_key": "key"}
        values.update(overrides)
        return self.repo.reserve_start(**values)

    def test_duplicate_scope_is_reserved_atomically_once(self):
        barrier = threading.Barrier(21)
        results = []

        def reserve():
            barrier.wait()
            results.append(self.reserve())

        threads = [threading.Thread(target=reserve) for _ in range(20)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(len({result.token.run_id for result in results}), 1)

    def test_independent_scopes_do_not_share_runs(self):
        results = [self.reserve(agent_id=f"agent-{index}", idempotency_key="same") for index in range(100)]
        self.assertTrue(all(result.created for result in results))
        self.assertEqual(len({result.token.run_id for result in results}), 100)

    def test_snapshots_are_copies_and_legacy_event_queue_is_discarded(self):
        result = self.repo.reserve_start(provider_kind="codex", agent_id="agent", run_id="run", meta={"nested": {"value": 1}, "events": object()})
        snapshot = self.repo.get("run")
        snapshot["nested"]["value"] = 2
        self.assertEqual(self.repo.get("run")["nested"]["value"], 1)
        self.assertNotIn("events", snapshot)
        self.assertEqual(result.token.version, 1)

    def test_launch_failure_is_terminal_and_duplicate_observes_result(self):
        reservation = self.reserve()
        transition = self.repo.complete(reservation.token.run_id, {"ok": False, "status": "failed", "error": "launch failed"}, generation=reservation.token.generation)
        self.assertTrue(transition.applied)
        duplicate = self.reserve()
        self.assertFalse(duplicate.created)
        self.assertEqual(duplicate.snapshot["result"]["error"], "launch failed")

    def test_late_completion_cannot_overwrite_terminal_result(self):
        reservation = self.reserve()
        first = self.repo.complete(reservation.token.run_id, {"ok": True, "status": "completed", "value": "first"}, generation=reservation.token.generation)
        late = self.repo.complete(reservation.token.run_id, {"ok": False, "status": "failed", "value": "late"}, generation=reservation.token.generation)
        self.assertTrue(first.applied)
        self.assertTrue(late.stale)
        self.assertEqual(self.repo.get(reservation.token.run_id)["result"]["value"], "first")

    def test_cancel_and_complete_race_has_one_terminal_winner(self):
        reservation = self.reserve()
        claim, cancel_token = self.repo.claim_cancel(reservation.token.run_id, generation=reservation.token.generation)
        self.assertTrue(claim.applied)
        barrier = threading.Barrier(3)
        results = []

        def complete():
            barrier.wait()
            results.append(self.repo.complete(reservation.token.run_id, {"ok": True, "status": "completed"}, generation=reservation.token.generation))

        def cancel():
            barrier.wait()
            results.append(self.repo.complete_cancel(reservation.token.run_id, cancel_token))

        threads = [threading.Thread(target=complete), threading.Thread(target=cancel)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(result.applied for result in results), 1)
        self.assertIn(self.repo.get(reservation.token.run_id)["result"]["status"], {"completed", "cancelled"})

    def test_stale_cleanup_generation_cannot_remove_new_owner(self):
        first = self.reserve(run_id="shared")
        self.repo.complete("shared", {"ok": True, "status": "completed"}, generation=first.token.generation)
        self.clock.value += 600_001
        self.assertTrue(self.repo.clear("shared", generation=first.token.generation, require_expired=True))
        second = self.repo.reserve_start(provider_kind="codex", agent_id="agent-2", run_id="shared")
        self.assertNotEqual(first.token.generation, second.token.generation)
        self.assertFalse(self.repo.clear("shared", generation=first.token.generation))
        self.assertEqual(self.repo.get("shared")["agentId"], "agent-2")

    def test_prune_is_bounded_and_keeps_unexpired_active_runs(self):
        reservations = [self.repo.reserve_start(provider_kind="codex", agent_id=str(index), run_id=f"run-{index}") for index in range(5)]
        for reservation in reservations[:4]:
            self.repo.complete(reservation.token.run_id, {"ok": True, "status": "completed"}, generation=reservation.token.generation)
        self.clock.value += 600_001
        first = self.repo.prune(max_items=2)
        self.assertEqual(first["runs"], 2)
        self.assertIsNotNone(self.repo.get("run-4"))
        second = self.repo.prune(max_items=10)
        self.assertEqual(second["runs"], 2)

    def test_terminal_reservation_retains_done_result_for_late_streams(self):
        snapshot = self.repo.reserve_start(provider_kind="codex", agent_id="agent", run_id="done-run", meta={"done": True, "result": {"ok": True, "status": "completed"}}).snapshot
        self.assertTrue(snapshot["terminal"])
        self.assertTrue(snapshot["done"])
        self.assertEqual(snapshot["terminalEventName"], "run.completed")
        self.assertEqual(snapshot["cleanupDeadline"], self.clock.value + 600_000)


if __name__ == "__main__":
    unittest.main()
