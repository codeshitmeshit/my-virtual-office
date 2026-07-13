import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tests" / "generate_provider_inventory.py"
CHANGE_EVIDENCE = ROOT / "openspec" / "changes" / "extract-provider-services-and-finish-modularization" / "evidence"
EVIDENCE = CHANGE_EVIDENCE / "current"
BASELINE_EVIDENCE = CHANGE_EVIDENCE / "baseline"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_provider_inventory", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProviderBaselineInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = load_generator()
        cls.artifacts = {
            name: json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
            for name in cls.generator.outputs()
        }

    def test_generated_artifacts_are_exactly_reproducible(self):
        expected = self.generator.outputs()
        self.assertEqual(set(expected), set(self.artifacts))
        for name, value in expected.items():
            self.assertEqual(value, self.artifacts[name], name)

    def test_all_supported_provider_paths_are_frozen(self):
        matrix = self.artifacts["provider-capability-matrix.json"]
        actual = {(item["providerKind"], item["providerPath"]) for item in matrix["paths"]}
        self.assertEqual(
            actual,
            {
                ("openclaw", "gateway"),
                ("codex", "app-server/bridge"),
                ("claude-code", "claude-code-cli"),
                ("hermes", "api"),
                ("hermes", "desktop"),
                ("hermes", "gateway-platform"),
            },
        )

    def test_public_event_aliases_include_lifecycle_replay_and_approval(self):
        aliases = self.artifacts["provider-event-alias-manifest.json"]["aliases"]
        required = {
            "run.started", "run.completed", "run.failed", "run.cancelled",
            "message.delta", "reasoning.available", "tool.started", "tool.completed",
            "tool.failed", "session.metrics", "approval.required", "approval.request",
            "approval.resolved", "provider.snapshot", "provider.heartbeat", "history.recovered",
        }
        self.assertTrue(required.issubset(aliases), sorted(required - set(aliases)))

    def test_current_state_authorities_and_transport_routes_are_visible(self):
        inventory = self.artifacts["provider-caller-writer-map.json"]
        authorities = inventory["stateAuthorities"]
        for name in (
            "PROVIDER_RUN_REPOSITORY", "PROVIDER_EVENT_JOURNAL", "PROVIDER_RUN_COORDINATOR",
            "PROVIDER_CONVERSATION_SERVICE", "HERMES_APPROVAL_SERVICE",
        ):
            self.assertIn(name, authorities)
            self.assertTrue(authorities[name]["writers"], name)
        for obsolete in ("PROVIDER_RUN_BRIDGE", "CLAUDE_CODE_STREAM_RUNS", "HERMES_ACTIVE_RUNS", "HERMES_APPROVAL_PENDING", "_CODEX_RUN_IDEMPOTENCY", "_PROVIDER_RUN_IDEMPOTENCY"):
            self.assertNotIn(obsolete, authorities)
        routes = {item["path"] for item in inventory["routes"]}
        for route in (
            "/api/provider/events", "/api/codex/runs", "/api/claude-code/runs",
            "/api/hermes/runs", "/api/codex/approval/respond", "/api/hermes/approval/respond",
        ):
            self.assertIn(route, routes)

    def test_current_approval_bounds_show_hermes_migrated_and_remaining_risk(self):
        report = self.artifacts["provider-approval-queue-bounds.json"]
        unbounded = {item["state"] for item in report["authorities"] if item["bounded"] is False}
        self.assertEqual(unbounded, set())
        hermes = next(item for item in report["authorities"] if item["state"] == "HERMES_APPROVAL_SERVICE")
        self.assertEqual((hermes["maxItems"], hermes["maxPerScope"]), (1000, 100))
        self.assertIn("explicit aggregate bounds", report["requiredFinalState"])

    def test_transport_delegate_candidates_do_not_claim_business_ownership(self):
        delegates = self.artifacts["provider-transport-delegate-candidates.json"]
        self.assertGreaterEqual(len(delegates["candidates"]), 6)
        forbidden = ("registry", "idempotency", "approval state", "conversation state")
        for item in delegates["candidates"]:
            allowed = item["allowed"].lower()
            self.assertFalse(any(term in allowed for term in forbidden), item)

    def test_characterization_manifest_covers_every_required_baseline_dimension(self):
        manifest_path = BASELINE_EVIDENCE / "provider-characterization-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        command_ids = {item["id"] for item in manifest["commands"]}
        self.assertEqual(len(command_ids), len(manifest["commands"]))
        for command in manifest["commands"]:
            executable = command["command"][0]
            if "/" in executable:
                self.assertTrue((ROOT / executable).exists(), command)
            for arg in command["command"][1:]:
                if arg.startswith("tests/"):
                    self.assertTrue((ROOT / arg).exists(), command)
        scenario_ids = {item["id"] for item in manifest["scenarios"]}
        self.assertEqual(
            scenario_ids,
            {
                "route-request-response-status", "run-start-poll-terminal", "run-failure-timeout-unavailable",
                "conversation-continuation-reset-isolation", "approval-registration-decision-replay", "cancellation",
                "sse-after-last-event-heartbeat-recovery", "concurrent-scopes", "project-meeting-feishu-callers",
                "fixed-capacity-performance", "generated-ownership-evidence",
            },
        )
        for scenario in manifest["scenarios"]:
            self.assertTrue(set(scenario["commands"]).issubset(command_ids), scenario)
        self.assertEqual(
            {item["id"] for item in manifest["knownBaselineRisks"]},
            {"terminal-race-no-cas", "approval-aggregate-unbounded", "whole-journal-replay-scan", "mutable-run-dict-exposure"},
        )


if __name__ == "__main__":
    unittest.main()
