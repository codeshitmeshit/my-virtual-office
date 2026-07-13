"""Static and performance gates for extracted Meeting-domain services."""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CHANGE = ROOT / "openspec" / "changes" / "archive" / "2026-07-13-extract-meeting-and-collaboration-services"
SERVICES = [
    APP / "services" / name for name in (
        "meeting_lifecycle.py", "meeting_requests.py", "meeting_action_items.py",
        "meeting_notifications.py", "meeting_callbacks.py",
    )
]


def test_services_do_not_import_server_handler_or_transport_types():
    forbidden_names = {"server", "OfficeHandler", "BaseHTTPRequestHandler", "HTTPServer", "ThreadingHTTPServer"}
    for path in SERVICES:
        tree = ast.parse(path.read_text())
        imported = set()
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imported.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module: imported.add(node.module.split(".")[0])
            if isinstance(node, ast.Name): names.add(node.id)
        assert not (forbidden_names & (imported | names)), (path, forbidden_names & (imported | names))


def test_services_never_write_meeting_json_directly():
    forbidden_calls = {"open", "write_text", "write_bytes", "dump", "dumps", "replace", "rename", "unlink"}
    for path in SERVICES:
        tree = ast.parse(path.read_text())
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call): continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in forbidden_calls: calls.append((node.lineno, name))
        assert calls == [], (path, calls)


def test_server_meeting_request_paths_no_longer_use_legacy_store_helpers():
    tree = ast.parse((APP / "server.py").read_text())
    migrated = {
        "_handle_meeting_request_create", "_meeting_request_list_filtered", "_handle_meeting_request_detail",
        "_handle_meeting_request_confirm", "_handle_meeting_request_reject", "_meeting_request_resolve_task_blocker",
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in migrated:
            called = {
                call.func.id for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            }
            assert not ({"_load_meeting_request_store", "_save_meeting_request_store"} & called), node.name


def test_final_performance_result_uses_fixed_sizes_and_one_conversion_write():
    result = json.loads((CHANGE / "performance-final.json").read_text())
    assert result["schema"] == 2 and result["method"] == "3 warmups, 20 measured runs"
    assert set(result["fixtures"]) == {"1", "20", "100"}
    for size, fixture in result["fixtures"].items():
        assert fixture["meetings"] == int(size)
        assert fixture["operations"]["loadUnified"]["runs"] == 20
        assert fixture["operations"]["saveUnified"]["p95Ms"] > 0
        assert fixture["unifiedBytes"] > 0
    observed = result["observedRequestConversion"]
    assert observed == {"notificationCalls": 1, "providerCalls": 0, "unifiedUpdates": 1}
    assert result["targetUnifiedRequestConversionWrites"] == 1


def test_extracted_histories_have_explicit_bounds():
    sources = "\n".join(path.read_text() for path in SERVICES)
    for bound in ("[-100:]", "[:-1000]", "[:-100]"):
        assert bound in sources
