#!/usr/bin/env python3
"""HTTP boundary coverage for browser-visible settings save outcomes."""

import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-settings-http-"))

import server  # noqa: E402


def test_management_token_challenge_is_readable_from_dedicated_loopback_origin():
    captured = {}

    class Handler:
        @staticmethod
        def _management_request_allowed():
            return False

        @staticmethod
        def _send_json(payload, status=200, **kwargs):
            captured.update(payload=payload, status=status, kwargs=kwargs)

    rejected = server.OfficeHandler._reject_untrusted_management_request(Handler())

    assert rejected is True
    assert captured["status"] == 403
    assert captured["payload"]["code"] == "management_token_required"
    assert captured["kwargs"]["allow_origin"] == "*"
