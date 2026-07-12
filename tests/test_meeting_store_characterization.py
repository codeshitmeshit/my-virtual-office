"""Static and storage characterization for the Meeting consolidation change."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"


EXPECTED_WRITERS = {
    "_save_exec_meeting_store": {
        "_meeting_complete_live_advisories", "_meeting_active_projection", "_meeting_history_projection",
        "_handle_executable_meeting_action_item", "_handle_executable_meeting_create",
        "_handle_executable_meeting_detail", "_handle_executable_meeting_conflict_action",
        "_handle_executable_meeting_transition", "_handle_executable_meeting_intervention",
        "_handle_executable_meeting_agenda_change", "_handle_executable_meeting_arbitration",
        "_handle_executable_meeting_moderator_takeover", "_handle_executable_meeting_targeted_question",
        "_handle_executable_meeting_end_with_moderator", "_handle_executable_meeting_run",
        "_handle_executable_meeting_reconcile",
    },
    "_save_meeting_request_store": {
        "_handle_meeting_request_create", "_handle_meeting_request_confirm",
        "_handle_meeting_request_reject", "_meeting_request_resolve_task_blocker",
    },
}

EXPECTED_READERS = {
    "_load_exec_meeting_store": {
        "_meeting_complete_live_advisories", "_meeting_active_projection", "_meeting_history_projection",
        "_handle_executable_meeting_action_item", "_handle_executable_meeting_create",
        "_handle_executable_meeting_detail", "_handle_executable_meeting_events",
        "_handle_executable_meeting_conflict_action", "_handle_executable_meeting_transition",
        "_handle_executable_meeting_intervention", "_handle_executable_meeting_agenda_change",
        "_handle_executable_meeting_arbitration", "_handle_executable_meeting_moderator_takeover",
        "_handle_executable_meeting_targeted_question", "_handle_executable_meeting_end_with_moderator",
        "_handle_executable_meeting_run", "_handle_executable_meeting_reconcile",
    },
    "_load_meeting_request_store": {
        "_handle_meeting_request_create", "_meeting_request_list_filtered", "_handle_meeting_request_detail",
        "_handle_meeting_request_confirm", "_handle_meeting_request_reject",
        "_meeting_request_resolve_task_blocker",
    },
}

REQUIRED_DOMAIN_FUNCTIONS = {
    "projectLinkage": {
        "_project_execution_block_for_meeting_request", "_project_execution_update_meeting_blocker",
        "_meeting_request_resolve_task_blocker", "_project_execution_apply_meeting_result",
        "_project_execution_apply_meeting_output_to_task", "_handle_project_execution_meeting_blocker_action",
    },
    "callbacks": {"_handle_feishu_card_action", "_dispatch_feishu_meeting_request_action", "_record_feishu_card_action"},
    "notifications": {"_send_meeting_request_notification", "_send_meeting_failure_notification", "_mark_feishu_notification"},
    "recovery": {"_handle_executable_meeting_reconcile", "_rebuild_exec_meeting_occupancy"},
}

def callers(target: str) -> set[str]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == target
            for call in ast.walk(node)
        ):
            found.add(node.name)
    return found


def test_every_legacy_meeting_store_writer_is_in_the_migration_inventory():
    for target, expected in EXPECTED_WRITERS.items():
        assert callers(target) == expected


def test_every_legacy_reader_and_cross_domain_boundary_is_in_the_inventory():
    for target, expected in EXPECTED_READERS.items():
        assert callers(target) == expected
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for names in REQUIRED_DOMAIN_FUNCTIONS.values():
        assert names <= defined
    source = SERVER.read_text(encoding="utf-8")
    assert source.count('"executable-meetings.json"') == 1
    assert source.count('"meeting-requests.json"') == 1


def test_generated_meeting_call_inventory_matches_every_definition_and_edge():
    generated = subprocess.check_output(
        [sys.executable, "tests/generate_meeting_inventory.py"], cwd=ROOT, text=True,
    )
    tracked = ROOT / "openspec/changes/extract-meeting-and-collaboration-services/meeting-call-inventory.json"
    assert json.loads(generated) == json.loads(tracked.read_text(encoding="utf-8"))


def test_characterization_manifest_points_to_executable_test_functions():
    manifest = json.loads((
        ROOT / "openspec/changes/extract-meeting-and-collaboration-services/characterization-manifest.json"
    ).read_text(encoding="utf-8"))
    assert len(manifest["nodeIds"]) == 10
    for node_id in manifest["nodeIds"]:
        path, function_name = node_id.split("::", 1)
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert function_name in functions, f"missing {path}::{function_name}"


def test_baseline_artifact_has_fixed_fixtures_and_two_write_conversion_contract():
    artifact = json.loads((
        ROOT / "openspec" / "changes" / "extract-meeting-and-collaboration-services"
        / "performance-baseline.json"
    ).read_text(encoding="utf-8"))
    assert sorted(artifact["fixtures"]) == ["1", "100", "20"]
    observed = artifact["observedRequestConversion"]
    assert observed == {"executable": 1, "requests": 3, "total": 4, "providerCalls": 0}
    assert artifact["targetUnifiedRequestConversionWrites"] == 1
    for fixture in artifact["fixtures"].values():
        for name in ("loadExecutable", "saveExecutable", "loadRequests", "saveRequests"):
            assert fixture["operations"][name]["runs"] == 20
            assert fixture["operations"][name]["warmups"] == 3
