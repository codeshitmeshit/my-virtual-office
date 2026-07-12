"""Cross-entry sensitive-data and trusted-boundary regression matrix."""

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-sensitive-coverage-import-"))

import server


def test_shared_redactor_removes_canaries_absolute_paths_and_bounds_text():
    raw = (
        'Authorization: Bearer bearer-canary\nAuthorization: Basic basic-canary\n{"api_key":"json-canary"} '
        'password=plain-canary client_secret=client-canary private_key=key-canary '
        'Cookie: session=cookie-canary\n/secret\n/Users/private project/secrets.txt\n'
        'C:\\private\\secret.txt\n\\\\server\\share\\unc-canary.txt\n'
        + ("x" * 13000)
    )
    safe = server._project_execution_redact(raw)
    for canary in (
        "bearer-canary", "basic-canary", "json-canary", "plain-canary", "client-canary", "key-canary",
        "cookie-canary", "/secret", "/Users/private", "C:\\private", "unc-canary",
    ):
        assert canary not in safe
    assert "[REDACTED]" in safe
    assert "[ABSOLUTE_PATH]" in safe
    assert safe.endswith("...[truncated]")
    assert len(safe) <= server._PROJECT_EXECUTION_MAX_TEXT + len("\n...[truncated]")


def test_schedule_logger_dto_uses_shared_sanitized_error_shape():
    safe = server._project_schedule_sanitize_result({
        "ok": False,
        "error": "api_key=cron-canary /private/workspace/repo/file.py",
        "providerMetadata": {"token": "metadata-canary"},
        "raw": "artifact-content-canary",
    })
    serialized = str(safe)
    assert "cron-canary" not in serialized
    assert "/private/workspace" not in serialized
    assert "metadata-canary" not in serialized
    assert "artifact-content-canary" not in serialized
    assert set(safe) <= {"ok", "error"}
