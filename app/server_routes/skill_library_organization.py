"""HTTP routes for Skills Library organization."""

from __future__ import annotations

import urllib.parse
from typing import Callable

from services.archive_manager_work_coordinator import ArchiveManagerBusyError
from services.skill_library_catalog import CatalogRevisionConflict
from services.skill_library_organization_admin import (
    SkillOrganizationMutationError,
)
from services.skill_library_organization_runs import SkillOrganizationStartError

from .http import JsonBodyError, read_json, send_json


_runtime_provider: Callable[[], object] | None = None


def configure_runtime(provider: Callable[[], object]) -> None:
    """Install the explicit runtime provider during server composition."""

    global _runtime_provider
    _runtime_provider = provider


def _runtime():
    if _runtime_provider is None:
        raise RuntimeError("skill library organization runtime is not configured")
    return _runtime_provider()


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as exc:
        return {}, {
            "ok": False,
            "code": "invalid_json",
            "error": str(exc),
            "_status": 400,
        }


def _error(exc: BaseException) -> dict:
    if isinstance(exc, CatalogRevisionConflict):
        return {
            "ok": False,
            "code": exc.code,
            "error": str(exc),
            "expectedRevision": exc.expected,
            "actualRevision": exc.actual,
            "_status": 409,
        }
    if isinstance(
        exc, (SkillOrganizationStartError, SkillOrganizationMutationError)
    ):
        return {
            "ok": False,
            "code": exc.code,
            "error": str(exc),
            "_status": exc.status,
        }
    if isinstance(exc, ArchiveManagerBusyError):
        return {
            "ok": False,
            "code": exc.code,
            "error": str(exc),
            "holder": exc.holder,
            "_status": 409,
        }
    if isinstance(exc, ValueError):
        return {
            "ok": False,
            "code": "validation_error",
            "error": str(exc),
            "_status": 400,
        }
    return {
        "ok": False,
        "code": "skill_organization_failed",
        "error": "Skill Library organization failed",
        "_status": 500,
    }


def _skill_slug(path: str) -> str:
    tail = path.split("/api/skills-library/", 1)[1]
    return urllib.parse.unquote(tail.rsplit("/category", 1)[0].strip("/"))


def handle_get(handler, parsed_url):
    if parsed_url.path != "/api/skills-library":
        return False
    try:
        return send_json(handler, _runtime().library_projection())
    except Exception as exc:
        return send_json(handler, _error(exc))


def handle_post(handler, parsed_url):
    path = parsed_url.path
    is_category = path.startswith("/api/skills-library/") and path.endswith(
        "/category"
    )
    if path not in {
        "/api/skills-library/organization/runs",
        "/api/skills-library/organization/dismiss",
    } and not is_category:
        return False
    try:
        runtime = _runtime()
        if path == "/api/skills-library/organization/runs":
            return send_json(handler, runtime.start_run())
        if path == "/api/skills-library/organization/dismiss":
            body, error = _body(handler)
            return send_json(handler, error or runtime.dismiss())
        if is_category:
            body, error = _body(handler)
            return send_json(
                handler,
                error or runtime.correct_skill(_skill_slug(path), body),
            )
    except Exception as exc:
        return send_json(handler, _error(exc))
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
