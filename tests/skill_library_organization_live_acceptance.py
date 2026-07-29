#!/usr/bin/env python3
"""Live acceptance for a dedicated Virtual Office with real OpenClaw.

This script mutates the configured Skills Library. It refuses to run unless the
explicit mutation guard is enabled and aborts before organization if unrelated
skills are present in the default category.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone

import requests


BASE_URL = os.environ.get("VO_TEST_URL", "http://127.0.0.1:8090").rstrip("/")
TOKEN = os.environ.get("VO_MANAGEMENT_TOKEN", "")
ALLOW_MUTATION = os.environ.get("VO_LIVE_ACCEPTANCE_ALLOW_MUTATION") == "1"
SKILL_COUNT = int(os.environ.get("VO_LIVE_SKILL_COUNT", "3"))
TIMEOUT_SECONDS = int(os.environ.get("VO_LIVE_ACCEPTANCE_TIMEOUT", "900"))
PREFIX = os.environ.get(
    "VO_LIVE_SKILL_PREFIX",
    "live-org-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
)
HEADERS = {
    "X-VO-Management-Token": TOKEN,
    "Content-Type": "application/json",
}


def request(method: str, path: str, body=None, *, authorized=True):
    response = requests.request(
        method,
        BASE_URL + path,
        json=body,
        headers=HEADERS if authorized else {"Content-Type": "application/json"},
        timeout=30,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return response.status_code, payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def skill_content(slug: str) -> str:
    return (
        "---\n"
        f"name: {slug}\n"
        f"description: Live OpenClaw acceptance skill {slug}\n"
        "---\n"
        f"# {slug}\n"
        "Classify this test skill by its software testing purpose.\n"
    )


def main() -> None:
    require(
        ALLOW_MUTATION,
        "Set VO_LIVE_ACCEPTANCE_ALLOW_MUTATION=1 for a dedicated test instance.",
    )
    require(TOKEN, "VO_MANAGEMENT_TOKEN is required.")
    require(1 <= SKILL_COUNT <= 120, "VO_LIVE_SKILL_COUNT must be 1..120.")
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{2,48}", PREFIX) is not None,
        "VO_LIVE_SKILL_PREFIX must be a safe lowercase kebab-case prefix.",
    )
    slugs = [f"{PREFIX}-{index:03d}" for index in range(SKILL_COUNT)]
    created: list[str] = []
    evidence: list[str] = []

    try:
        health_status, _health = request("GET", "/health")
        require(health_status == 200, "Virtual Office health check failed.")

        denied_status, denied = request(
            "POST",
            "/api/skills-library/organization/runs",
            {},
            authorized=False,
        )
        require(
            denied_status == 403
            and denied.get("code") == "management_token_required",
            "Organization start did not enforce the management token.",
        )
        evidence.append("management-token")

        for slug in slugs:
            status, payload = request(
                "POST",
                "/api/skills-library",
                {"name": slug, "content": skill_content(slug)},
            )
            require(status == 200 and payload.get("ok"), f"Create failed: {slug}")
            created.append(slug)

        status, listing = request("GET", "/api/skills-library")
        require(status == 200, "Skills Library listing failed.")
        default_slugs = {
            item["name"]
            for item in listing.get("skills", [])
            if item.get("primaryCategoryId") == "default"
        }
        unrelated = sorted(default_slugs - set(slugs))
        require(
            not unrelated,
            "Dedicated instance required; unrelated default skills: "
            + ", ".join(unrelated[:10]),
        )
        require(set(slugs) <= default_slugs, "Created skills were not in Default.")
        evidence.append(f"default-intake:{len(slugs)}")

        start_status, started = request(
            "POST", "/api/skills-library/organization/runs", {}
        )
        require(start_status == 202, f"Organization start failed: {started}")
        require(started.get("status") == "running", "Run did not start as running.")
        evidence.append("real-archive-manager-start")

        deadline = time.monotonic() + TIMEOUT_SECONDS
        terminal = None
        latest = listing
        while time.monotonic() < deadline:
            _status, latest = request("GET", "/api/skills-library")
            organization = latest.get("organization") or {}
            if organization.get("status") in {
                "completed",
                "partial",
                "failed",
                "resolved",
            }:
                terminal = organization
                break
            time.sleep(2)
        require(terminal is not None, "Organization did not reach a terminal state.")
        require(
            terminal.get("totalCount") == SKILL_COUNT,
            f"Unexpected run scope: {terminal.get('totalCount')}",
        )
        evidence.append(f"terminal:{terminal.get('status')}")

        failures = {
            item.get("slug")
            for item in terminal.get("failures", [])
            if item.get("slug") in set(slugs)
        }
        revision = latest.get("catalogRevision")
        for slug in sorted(failures):
            correction_status, corrected = request(
                "POST",
                f"/api/skills-library/{slug}/category",
                {
                    "categoryId": "development-testing",
                    "expectedRevision": revision,
                },
            )
            require(
                correction_status == 200 and corrected.get("ok"),
                f"Manual correction failed: {slug}",
            )
            revision = corrected["catalogRevision"]
        if failures:
            require(
                corrected["organization"]["status"] == "resolved",
                "Final manual correction did not resolve the marker.",
            )
        evidence.append(f"manual-repair:{len(failures)}")

        _status, final_listing = request("GET", "/api/skills-library")
        final_by_slug = {
            item["name"]: item for item in final_listing.get("skills", [])
        }
        require(
            all(
                final_by_slug[slug].get("primaryCategoryId") != "default"
                for slug in slugs
            ),
            "One or more live test skills remained in Default.",
        )

        overview_status, overview = request("GET", "/api/archive-room")
        require(overview_status == 200, "Archive Room overview failed.")
        activities = (
            overview.get("archiveManager", {}).get("recentActivity", [])
        )
        require(
            any(
                item.get("action") == "skill_library_organization"
                for item in activities
            ),
            "Archive-manager terminal activity was not visible.",
        )
        evidence.append("archive-manager-activity")

        print(
            {
                "ok": True,
                "runId": terminal.get("runId"),
                "skillCount": SKILL_COUNT,
                "evidence": evidence,
            }
        )
    finally:
        cleanup_failures = []
        for slug in created:
            status, _payload = request(
                "DELETE", f"/api/skills-library/{slug}"
            )
            if status != 200:
                cleanup_failures.append(slug)
        if cleanup_failures:
            print({"cleanupFailed": cleanup_failures})


if __name__ == "__main__":
    main()
