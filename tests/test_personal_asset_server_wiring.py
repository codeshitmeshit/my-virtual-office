from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"


def test_server_uses_only_thin_personal_asset_runtime_and_route_delegation():
    source = SERVER.read_text(encoding="utf-8")
    assert "personal_asset_http_service.PersonalAssetHTTPRoutes.handles(request_path)" in source
    assert "def _get_personal_asset_runtime():" in source
    assert "def _handle_personal_asset_get(" in source
    assert "def _handle_personal_asset_post(" in source
    assert "PersonalAssetAgentAuthRequest(" in source
    assert 'os.path.join(STATUS_DIR, "personal-assets.json")' not in source
    assert "PersonalAssetStore(" not in source
    runtime_block = source.split("def _get_personal_asset_runtime():", 1)[1].split(
        "def _get_agent_management_runtime():", 1
    )[0]
    assert "_get_hr_application_runtime" not in runtime_block


def test_existing_human_decision_routes_remain_present():
    source = SERVER.read_text(encoding="utf-8")
    assert 'request_path == "/api/agent/human-decisions"' in source
    assert "HUMAN_DECISION_WORKFLOW.create(" in source
    assert "decisions_loader=HUMAN_DECISION_WORKFLOW.snapshot" in source
