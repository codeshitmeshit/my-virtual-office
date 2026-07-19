"""Canonical HR directory-skill publication into fake Agent workspaces."""

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_skill_publisher import (
    DIRECTORY_SKILL_NAME,
    HRSkillPublisher,
    repository_directory_skill_path,
)
from services.managed_skills import MANAGED_SKILL_MARKER


def canonical(body="directory instructions"):
    return (
        "---\n"
        "name: vo-agent-directory\n"
        "description: safe directory\n"
        "---\n\n"
        f"# Directory\n\n{body}\n"
    )


def setup(tmp_path, body="directory instructions"):
    base = tmp_path / "workspaces"
    skill = tmp_path / "canonical" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(canonical(body), encoding="utf-8")
    publisher = HRSkillPublisher(workspace_base=base, canonical_skill_path=skill)
    return publisher, base, skill


def agent(workspace, provider="openclaw", ai_id="agent-1"):
    return {"id": ai_id, "providerKind": provider, "workspace": str(workspace)}


def test_supported_workspace_install_reports_hash_marker_and_readiness(tmp_path):
    publisher, base, canonical_path = setup(tmp_path)
    workspace = base / "agent-1"
    workspace.mkdir(parents=True)
    result = publisher.publish(agent(workspace))
    assert result.ready is True
    assert result.state == "updated"
    assert result.updated is True
    expected_hash = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    assert result.sha256 == expected_hash
    installed = workspace / "skills" / DIRECTORY_SKILL_NAME / "SKILL.md"
    marker = json.loads((installed.parent / MANAGED_SKILL_MARKER).read_text())
    assert installed.read_text() == canonical_path.read_text()
    assert marker["skill"] == DIRECTORY_SKILL_NAME
    assert marker["sha256"] == expected_hash


def test_repeated_publish_noops_and_canonical_change_refreshes_deterministically(tmp_path):
    publisher, base, canonical_path = setup(tmp_path, "version one")
    workspace = base / "agent-1"
    workspace.mkdir(parents=True)
    first = publisher.publish(agent(workspace))
    installed = workspace / "skills" / DIRECTORY_SKILL_NAME / "SKILL.md"
    before_mtime = installed.stat().st_mtime_ns
    second = publisher.publish(agent(workspace))
    assert second.ready is True
    assert second.state == "ready"
    assert second.updated is False
    assert installed.stat().st_mtime_ns == before_mtime

    canonical_path.write_text(canonical("version two"))
    third = publisher.publish(agent(workspace))
    assert third.state == "updated"
    assert third.sha256 != first.sha256
    assert installed.read_text() == canonical("version two")


def test_unowned_conflict_is_preserved_and_reported(tmp_path):
    publisher, base, _canonical_path = setup(tmp_path)
    workspace = base / "agent-1"
    installed = workspace / "skills" / DIRECTORY_SKILL_NAME / "SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_text("user-owned directory skill")
    result = publisher.publish(agent(workspace))
    assert result.ready is False
    assert result.state == "conflict"
    assert result.error_code == "hr_skill_conflict"
    assert installed.read_text() == "user-owned directory skill"


def test_unsupported_provider_remains_visible_as_not_ready(tmp_path):
    publisher, _base, _canonical_path = setup(tmp_path)
    result = publisher.publish(agent(tmp_path / "outside", provider="codex"))
    assert result.ready is False
    assert result.state == "unsupported_provider"
    assert result.error_code == "hr_skill_unsupported_provider"


def test_missing_outside_and_symlinked_workspace_paths_fail_closed(tmp_path):
    publisher, base, _canonical_path = setup(tmp_path)
    missing = publisher.publish(agent(base / "missing", ai_id="missing"))
    assert missing.state == "workspace_missing"

    outside = tmp_path / "outside"
    outside.mkdir()
    rejected = publisher.publish(agent(outside, ai_id="outside"))
    assert rejected.state == "path_rejected"

    workspace = base / "linked"
    workspace.mkdir(parents=True)
    (workspace / "skills").symlink_to(outside, target_is_directory=True)
    linked = publisher.publish(agent(workspace, ai_id="linked"))
    assert linked.state == "path_rejected"
    assert list(outside.iterdir()) == []


def test_missing_invalid_or_secret_bearing_canonical_is_not_installed(tmp_path):
    publisher, base, canonical_path = setup(tmp_path)
    workspace = base / "agent-1"
    workspace.mkdir(parents=True)
    canonical_path.unlink()
    assert publisher.publish(agent(workspace)).state == "canonical_invalid"

    canonical_path.write_text(canonical("Authorization: Bearer actualSecretTokenValue123456789"))
    secret = publisher.publish(agent(workspace))
    assert secret.state == "canonical_invalid"
    assert not (workspace / "skills" / DIRECTORY_SKILL_NAME).exists()


def test_invalid_agent_identity_is_reported_without_filesystem_changes(tmp_path):
    publisher, base, _canonical_path = setup(tmp_path)
    result = publisher.publish({"providerKind": "openclaw", "workspace": str(base / "agent")})
    assert result.state == "invalid_agent"
    assert result.error_code == "hr_skill_agent_invalid"
    assert publisher.publish(None).state == "invalid_agent"
    assert not base.exists()


def test_repository_path_helper_targets_canonical_skill():
    assert repository_directory_skill_path(ROOT) == (
        ROOT / "skills" / DIRECTORY_SKILL_NAME / "SKILL.md"
    )


def test_publisher_module_has_no_server_or_transport_dependency():
    source = (APP_DIR / "services" / "hr_skill_publisher.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
