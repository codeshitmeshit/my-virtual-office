from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-skill-organization-routes-")
)

import server  # noqa: E402
import server_routes  # noqa: E402
from server_routes import skill_library_organization  # noqa: E402
from services.skill_library_organization_runtime import (  # noqa: E402
    SkillLibraryOrganizationRuntime,
)


class Handler:
    def __init__(self, body=None):
        raw = b"" if body is None else json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, _key, _value):
        pass

    def end_headers(self):
        pass


def dispatch(method, path, body=None):
    handler = Handler(body)
    handled = server_routes.dispatch(
        handler, method, urllib.parse.urlparse(path)
    )
    assert handled is True
    return handler.status, json.loads(handler.wfile.getvalue() or b"{}")


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def library_projection(self):
        self.calls.append(("list",))
        return {
            "skills": [{"name": "alpha", "description": "old field"}],
            "categories": [{"id": "default", "name": "默认标签"}],
            "catalogRevision": 3,
            "organization": None,
            "archiveManager": {"status": "idle"},
        }

    def start_run(self):
        self.calls.append(("start",))
        return {"ok": True, "runId": "run-1", "status": "running", "_status": 202}

    def dismiss(self):
        self.calls.append(("dismiss",))
        return {"ok": True, "catalogRevision": 4}

    def correct_skill(self, slug, body):
        self.calls.append(("correct", slug, body))
        return {"ok": True, "skill": slug, "catalogRevision": 5}


def test_route_group_is_registered_before_legacy_skills_route():
    modules = list(server_routes.ROUTE_MODULES)
    assert skill_library_organization in modules
    assert modules.index(skill_library_organization) < modules.index(
        server_routes.skills
    )


def test_routes_dispatch_through_explicit_runtime(monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setattr(
        skill_library_organization, "_runtime_provider", lambda: runtime
    )

    list_status, listing = dispatch("GET", "/api/skills-library")
    start_status, started = dispatch(
        "POST", "/api/skills-library/organization/runs"
    )
    dismiss_status, dismissed = dispatch(
        "POST", "/api/skills-library/organization/dismiss", {}
    )
    correction_status, corrected = dispatch(
        "POST",
        "/api/skills-library/alpha%20skill/category",
        {"categoryId": "development-testing", "expectedRevision": 4},
    )

    assert list_status == 200
    assert listing["skills"][0]["description"] == "old field"
    assert start_status == 202
    assert started["runId"] == "run-1"
    assert dismiss_status == 200 and dismissed["catalogRevision"] == 4
    assert correction_status == 200 and corrected["skill"] == "alpha skill"
    assert runtime.calls == [
        ("list",),
        ("start",),
        ("dismiss",),
        (
            "correct",
            "alpha skill",
            {"categoryId": "development-testing", "expectedRevision": 4},
        ),
    ]


def test_server_composes_runtime_with_additive_compatible_projection(
    tmp_path, monkeypatch
):
    home = tmp_path / "openclaw"
    skill_file = home / "skills-library" / "alpha" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: alpha\ndescription: Existing description\n---\n# Alpha",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        server,
        "VO_CONFIG",
        {
            **server.VO_CONFIG,
            "openclaw": {
                **server.VO_CONFIG.get("openclaw", {}),
                "homePath": str(home),
            },
        },
    )
    monkeypatch.setattr(server, "_ensure_builtin_communication_skill", lambda: None)

    runtime = server._skill_library_organization_runtime()
    projection = runtime.library_projection()

    assert isinstance(runtime, SkillLibraryOrganizationRuntime)
    assert runtime.organizer.coordinator is server.ARCHIVE_MANAGER_WORK_COORDINATOR
    assert projection["skills"][0]["name"] == "alpha"
    assert projection["skills"][0]["description"] == "Existing description"
    assert projection["skills"][0]["primaryCategoryId"] == "default"
    assert len(projection["categories"]) == 6
    assert projection["catalogRevision"] == 0
    assert projection["organization"] is None
    assert "status" in projection["archiveManager"]


def test_public_projection_hides_internal_target_snapshot(tmp_path):
    home = tmp_path / "openclaw"
    library = home / "skills-library"
    target = library / "alpha" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Alpha", encoding="utf-8")

    class Repository:
        def project(self, _names):
            return {
                "categories": [{"id": "default", "name": "默认标签"}],
                "revision": 7,
                "lastOrganization": {
                    "runId": "run-1",
                    "status": "running",
                    "targetSlugs": ["alpha"],
                    "failures": [],
                },
            }

    organizer = type(
        "Organizer",
        (),
        {"repository": Repository(), "library_dir": library},
    )()
    runtime = SkillLibraryOrganizationRuntime(
        organizer=organizer,
        admin=object(),
        list_skills=lambda: {
            "skills": [{"name": "alpha"}],
            "organization": {
                "runId": "run-1",
                "status": "running",
                "targetSlugs": ["alpha"],
                "failures": [],
            },
        },
        archive_manager_state=lambda: {"status": "working"},
    )

    projection = runtime.library_projection()

    assert projection["organization"]["runId"] == "run-1"
    assert "targetSlugs" not in projection["organization"]
