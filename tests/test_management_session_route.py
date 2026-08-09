from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from server_routes import management_session  # noqa: E402


class Handler:
    def __init__(self, allowed: bool):
        self.allowed = allowed
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def _management_request_allowed(self):
        return self.allowed

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass


def test_management_session_probe_rejects_missing_token_without_mutation():
    handler = Handler(False)

    handled = management_session.handle_get(
        handler, urllib.parse.urlparse(management_session.GET_PATH)
    )

    assert handled is True
    assert handler.status == 403
    assert handler.headers["Cache-Control"] == "no-store"
    assert json.loads(handler.wfile.getvalue()) == {
        "ok": False,
        "authenticated": False,
        "code": "management_token_required",
        "error": "A valid Virtual Office management token is required",
    }


def test_management_session_probe_accepts_valid_token():
    handler = Handler(True)

    management_session.handle_get(
        handler, urllib.parse.urlparse(management_session.GET_PATH)
    )

    assert handler.status == 200
    assert json.loads(handler.wfile.getvalue()) == {
        "ok": True,
        "authenticated": True,
    }

