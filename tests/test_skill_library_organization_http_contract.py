from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-skill-org-http-contract-")
)

import server  # noqa: E402
from server_routes import skill_library_organization  # noqa: E402
from services.skill_library_catalog import CatalogRevisionConflict  # noqa: E402
from services.skill_library_organization_admin import (  # noqa: E402
    SkillOrganizationMutationError,
)
from services.skill_library_organization_runs import (  # noqa: E402
    SkillOrganizationStartError,
)


def handler(path, raw=b"", token=None):
    instance = object.__new__(server.OfficeHandler)
    instance.path = path
    instance.headers = {"Content-Length": str(len(raw))}
    if token is not None:
        instance.headers["X-VO-Management-Token"] = token
    instance.rfile = io.BytesIO(raw)
    instance.wfile = io.BytesIO()
    instance.status = None
    instance.send_response = lambda status, *args, **kwargs: setattr(
        instance, "status", status
    )
    instance.send_header = lambda _key, _value: None
    instance.end_headers = lambda: None
    return instance


def payload(instance):
    return json.loads(instance.wfile.getvalue() or b"{}")


class Runtime:
    def __init__(self):
        self.calls = []
        self.error = None

    def library_projection(self):
        return {
            "skills": [],
            "categories": [],
            "catalogRevision": 0,
            "organization": None,
            "archiveManager": {"status": "idle"},
        }

    def start_run(self):
        self.calls.append("start")
        if self.error:
            raise self.error
        return {"ok": True, "runId": "run-1", "status": "running", "_status": 202}

    def dismiss(self):
        self.calls.append("dismiss")
        if self.error:
            raise self.error
        return {"ok": True}

    def correct_skill(self, slug, body):
        self.calls.append(("correct", slug, body))
        if self.error:
            raise self.error
        return {"ok": True, "skill": slug}


@pytest.mark.parametrize(
    "path",
    [
        "/api/skills-library/organization/runs",
        "/api/skills-library/organization/dismiss",
        "/api/skills-library/alpha/category",
    ],
)
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_management_auth_rejects_before_body_parsing_or_runtime(
    monkeypatch, path, token
):
    runtime = Runtime()
    monkeypatch.setattr(
        skill_library_organization, "_runtime_provider", lambda: runtime
    )
    instance = handler(path, b"not-json", token=token)

    server.OfficeHandler.do_POST(instance)

    assert instance.status == 403
    assert payload(instance)["code"] == "management_token_required"
    assert instance.rfile.tell() == 0
    assert runtime.calls == []


def test_valid_owner_token_dispatches_all_mutations(monkeypatch):
    runtime = Runtime()
    monkeypatch.setattr(
        skill_library_organization, "_runtime_provider", lambda: runtime
    )
    token = server._MANAGEMENT_TOKEN

    start = handler(
        "/api/skills-library/organization/runs", b"{}", token=token
    )
    dismiss = handler(
        "/api/skills-library/organization/dismiss", b"{}", token=token
    )
    correction_body = json.dumps(
        {"categoryId": "development-testing", "expectedRevision": 2}
    ).encode()
    correction = handler(
        "/api/skills-library/alpha/category",
        correction_body,
        token=token,
    )

    server.OfficeHandler.do_POST(start)
    server.OfficeHandler.do_POST(dismiss)
    server.OfficeHandler.do_POST(correction)

    assert start.status == 202
    assert dismiss.status == correction.status == 200
    assert runtime.calls == [
        "start",
        "dismiss",
        (
            "correct",
            "alpha",
            {"categoryId": "development-testing", "expectedRevision": 2},
        ),
    ]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (
            SkillOrganizationStartError(
                "archive_manager_busy", "Archive manager is busy"
            ),
            409,
            "archive_manager_busy",
        ),
        (
            SkillOrganizationStartError(
                "archive_manager_unavailable", "Archive manager is unavailable"
            ),
            409,
            "archive_manager_unavailable",
        ),
        (
            SkillOrganizationStartError(
                "skill_organization_disabled",
                "Skill Library organization is disabled",
                status=404,
            ),
            404,
            "skill_organization_disabled",
        ),
        (
            SkillOrganizationMutationError(
                "category_not_found", "Category was not found", status=404
            ),
            404,
            "category_not_found",
        ),
        (
            CatalogRevisionConflict(2, 3),
            409,
            "catalog_revision_conflict",
        ),
    ],
)
def test_domain_errors_have_stable_http_contract(
    monkeypatch, error, status, code
):
    runtime = Runtime()
    runtime.error = error
    monkeypatch.setattr(
        skill_library_organization, "_runtime_provider", lambda: runtime
    )
    body = json.dumps(
        {"categoryId": "development-testing", "expectedRevision": 2}
    ).encode()
    instance = handler(
        "/api/skills-library/alpha/category",
        body,
        token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(instance)

    assert instance.status == status
    assert payload(instance)["code"] == code


def test_authorized_invalid_json_returns_validation_error(monkeypatch):
    runtime = Runtime()
    monkeypatch.setattr(
        skill_library_organization, "_runtime_provider", lambda: runtime
    )
    instance = handler(
        "/api/skills-library/alpha/category",
        b"not-json",
        token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(instance)

    assert instance.status == 400
    assert payload(instance)["code"] == "invalid_json"
    assert runtime.calls == []


def test_live_get_uses_additive_organization_projection(monkeypatch):
    runtime = Runtime()
    monkeypatch.setattr(
        skill_library_organization, "_runtime_provider", lambda: runtime
    )
    instance = handler("/api/skills-library")

    server.OfficeHandler.do_GET(instance)

    assert instance.status == 200
    assert payload(instance) == runtime.library_projection()
