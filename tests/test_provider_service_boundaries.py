import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-provider-boundaries-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")


class ProviderServiceBoundaryTests(unittest.TestCase):
    def test_provider_services_do_not_import_server_http_or_concrete_adapters(self):
        for name in ("provider_registry.py", "provider_events.py", "provider_ports.py", "provider_runs.py", "provider_approvals.py", "provider_conversations.py"):
            path = APP / "services" / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add(node.module or "")
            forbidden = [value for value in imports if value in {"server", "http", "http.server"} or value.startswith("providers") or value.startswith("app.providers")]
            self.assertEqual(forbidden, [], (name, forbidden))

    def test_repository_journal_and_transport_are_the_only_runtime_authorities(self):
        source = (APP / "server.py").read_text(encoding="utf-8")
        self.assertIn("PROVIDER_RUN_REPOSITORY = ProviderRunRepository", source)
        self.assertIn("PROVIDER_EVENT_JOURNAL = ProviderEventJournal", source)
        self.assertIn("PROVIDER_RUN_COORDINATOR = ProviderRunCoordinator(PROVIDER_RUN_REPOSITORY, PROVIDER_EVENT_JOURNAL)", source)
        self.assertIn("PROVIDER_SSE_TRANSPORT = _provider_sse_transport_for(PROVIDER_RUN_REPOSITORY, PROVIDER_EVENT_JOURNAL)", source)
        self.assertNotIn("class ProviderRunBridge", source)
        for obsolete in ("_CODEX_RUN_IDEMPOTENCY", "_PROVIDER_RUN_IDEMPOTENCY", "CLAUDE_CODE_STREAM_RUNS", "HERMES_ACTIVE_RUNS", "HERMES_APPROVAL_PENDING"):
            self.assertNotIn(obsolete, source)

    def test_runtime_authorities_are_services_not_compatibility_maps(self):
        import server

        self.assertIsInstance(server.PROVIDER_RUN_REPOSITORY, server.ProviderRunRepository)
        self.assertIsInstance(server.PROVIDER_EVENT_JOURNAL, server.ProviderEventJournal)
        self.assertIsInstance(server.HERMES_APPROVAL_SERVICE, server.ProviderApprovalService)

    def test_codex_start_uses_shared_coordinator_without_legacy_launch_authority(self):
        source = (APP / "server.py").read_text(encoding="utf-8")
        body = source[source.index("def _handle_codex_run_start"):source.index("def _handle_codex_run_events")]
        self.assertIn("PROVIDER_RUN_COORDINATOR.start", body)
        self.assertIn("CallableProviderAdapter", body)
        self.assertIn("_handle_codex_chat(run_body)", body)
        self.assertNotIn("_CODEX_RUN_IDEMPOTENCY", body)
        self.assertNotIn("PROVIDER_RUN_BRIDGE.remember", body)
        self.assertNotIn("threading.Thread", body)

    def test_claude_start_uses_shared_coordinator_without_legacy_launch_authority(self):
        source = (APP / "server.py").read_text(encoding="utf-8")
        body = source[source.index("def _handle_claude_code_run_start"):source.index("def _handle_claude_code_run_events")]
        self.assertIn("PROVIDER_RUN_COORDINATOR.start", body)
        self.assertIn("CallableProviderAdapter", body)
        self.assertIn("_handle_claude_code_chat(run_body)", body)
        self.assertNotIn("_PROVIDER_RUN_IDEMPOTENCY", body)
        self.assertNotIn("_register_provider_run_idempotency", body)
        self.assertNotIn("_remember_claude_code_stream_run", body)
        self.assertNotIn("threading.Thread", body)

    def test_hermes_api_and_desktop_runs_use_shared_coordinator(self):
        source = (APP / "server.py").read_text(encoding="utf-8")
        api_start = source[source.index("def _handle_hermes_run_start"):source.index("def _handle_hermes_run_events")]
        desktop_start = source[source.index("def _handle_hermes_desktop_run_start"):source.index("def _test_hermes_api")]
        run_events = source[source.index("def _handle_hermes_run_events"):source.index("def _handle_hermes_run_stop")]
        for body in (api_start, desktop_start):
            self.assertIn("PROVIDER_RUN_COORDINATOR.start", body)
            self.assertIn("CallableProviderAdapter", body)
            self.assertNotIn("_PROVIDER_RUN_IDEMPOTENCY", body)
            self.assertNotIn("PROVIDER_RUN_BRIDGE.remember", body)
            self.assertNotIn("threading.Thread", body)
        self.assertNotIn("_remember_hermes_active_run", desktop_start)
        self.assertNotIn("def _handle_hermes_desktop_run_events", source)
        self.assertNotIn("_handle_hermes_desktop_run_events", run_events)
        self.assertIn("PROVIDER_SSE_TRANSPORT.stream_run", run_events)

    def test_hermes_approval_callers_use_bounded_fenced_service(self):
        source = (APP / "server.py").read_text(encoding="utf-8")
        remember = source[source.index("def _remember_hermes_approval_pending"):source.index("def _get_hermes_approval_pending")]
        respond = source[source.index("def _handle_hermes_approval_respond"):source.index("def _hermes_stream_event_payload")]
        self.assertIn("HERMES_APPROVAL_SERVICE.register", remember)
        self.assertIn("HERMES_APPROVAL_SERVICE.resolve", respond)
        self.assertNotIn("HERMES_APPROVAL_PENDING", remember)
        self.assertNotIn("_resolve_hermes_approval_pending", respond)

    def test_provider_adapters_cannot_mutate_repository_or_journal_internals(self):
        forbidden = ("PROVIDER_RUN_REPOSITORY", "PROVIDER_EVENT_JOURNAL", "ProviderRunRepository", "._runs", "._idempotency", "._by_id")
        offenders = []
        for path in sorted((APP / "providers").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    offenders.append((path.name, token))
        self.assertEqual(offenders, [])

    def test_sse_transport_is_read_only_over_business_state(self):
        source = (APP / "provider_sse_transport.py").read_text(encoding="utf-8")
        for forbidden in ("ProviderRunCoordinator", ".reserve_start(", ".update(", ".complete(", ".claim_cancel(", ".publish("):
            self.assertNotIn(forbidden, source)
        self.assertIn("repository.snapshots()", source)
        self.assertIn("journal.wait_for_run_events", source)
        self.assertIn("journal.wait_for_conversation_events", source)

    def test_approved_server_sse_delegates_contain_no_business_logic(self):
        source = (APP / "server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: ast.get_source_segment(source, node) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        expected = {
            "_handle_codex_run_events": 'PROVIDER_SSE_TRANSPORT.stream_run(handler, run_id, "Codex")',
            "_handle_claude_code_run_events": 'PROVIDER_SSE_TRANSPORT.stream_run(handler, run_id, "Claude Code")',
            "_handle_hermes_run_events": 'PROVIDER_SSE_TRANSPORT.stream_run(handler, run_id, "Hermes")',
        }
        for name, call in expected.items():
            body = functions[name]
            self.assertIn(call, body)
            self.assertNotIn("if ", body)
            self.assertNotIn("for ", body)


if __name__ == "__main__":
    unittest.main()
