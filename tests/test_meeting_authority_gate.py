import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="meeting-authority-import-"))
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"

import server
from services.meeting_repository import empty_store


def startup_status(status_dir: Path):
    env = {
        **os.environ, "PYTHONPATH": str(APP), "VO_STATUS_DIR": str(status_dir),
        "VO_HERMES_ENABLED": "0", "VO_CODEX_ENABLED": "0", "VO_CLAUDE_CODE_ENABLED": "0",
    }
    code = "import json,server; print(json.dumps(server._meeting_domain_authority_status(),sort_keys=True))"
    completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_startup_initializes_empty_unified_store(tmp_path):
    status = startup_status(tmp_path)
    assert status["ok"] is True and status["state"] == "unified"
    assert json.loads((tmp_path / "meeting-domain.json").read_text())["schemaVersion"] == 1


def test_startup_reports_migration_required_without_creating_unified(tmp_path):
    (tmp_path / "meeting-requests.json").write_text(json.dumps({"requests": {"r1": {"id": "r1"}}}))
    status = startup_status(tmp_path)
    assert status["code"] == "meeting_store_migration_required" and status["_status"] == 409
    assert not (tmp_path / "meeting-domain.json").exists()


def test_startup_reports_invalid_and_unknown_unified_versions(tmp_path):
    (tmp_path / "meeting-domain.json").write_text("{broken")
    status = startup_status(tmp_path)
    assert status["code"] == "meeting_store_invalid" and status["_status"] == 500
    data = empty_store(); data["schemaVersion"] = 99
    (tmp_path / "meeting-domain.json").write_text(json.dumps(data))
    status = startup_status(tmp_path)
    assert status["code"] == "meeting_store_invalid" and status["_status"] == 500


def test_http_meeting_routes_fail_before_body_or_business_dispatch_when_migration_required(tmp_path, monkeypatch):
    (tmp_path / "meeting-requests.json").write_text(json.dumps({"requests": {"r1": {"id": "r1"}}}))
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    server._MEETING_DOMAIN_REPOSITORIES.clear()
    handler = object.__new__(server.OfficeHandler)
    handler.path = "/api/meetings/executable/create"
    handler.headers = {"Content-Length": "999999"}
    handler.rfile = io.BytesIO(b"")
    captured = []
    handler._send_json = lambda payload, status=200, **kwargs: captured.append((status, payload))
    handler.do_POST()
    assert captured == [(409, {
        "error": "Meeting store is not ready", "ok": False,
        "code": "meeting_store_migration_required", "_status": 409,
    })]


def test_http_store_status_is_read_only_diagnostic(tmp_path, monkeypatch):
    (tmp_path / "meeting-domain.json").write_text("{broken")
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    server._MEETING_DOMAIN_REPOSITORIES.clear()
    handler = object.__new__(server.OfficeHandler)
    handler.path = "/api/meetings/store-status"
    captured = []
    handler._send_json = lambda payload, status=200, **kwargs: captured.append((status, payload))
    handler.do_GET()
    assert captured[0][0] == 500
    assert captured[0][1]["code"] == "meeting_store_invalid"
