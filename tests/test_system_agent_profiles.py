"""Filesystem and parsing coverage for shared system-Agent profiles."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.system_agent_profiles import (
    ProfileTemplateError,
    RenderedSystemAgentProfile,
    UnsafeProfilePathError,
    extract_template_version,
    load_and_render_profile,
    parse_template_files,
    profile_needs_update,
    read_profile_version,
    render_profile_template,
    resolve_safe_workspace,
    sync_profile_files,
)
from services.system_agent_roles import ARCHIVE_MANAGER_ROLE


MARKER = "example-profile-version"
REQUIRED = ("IDENTITY.md", "AGENTS.md")


def template(*, version="v1", identity="Hello {{NAME}}", agents="Rules"):
    return f"""# Example
Example-Profile-Version: {version}

--- file: IDENTITY.md ---
<!-- example-profile-version: {version} -->
{identity}

--- file: AGENTS.md ---
<!-- example-profile-version: {version} -->
{agents}
"""


def render(source=None, **tokens):
    return render_profile_template(
        source or template(),
        version_marker=MARKER,
        required_files=REQUIRED,
        tokens={"NAME": "HR", **tokens},
    )


def test_extracts_one_case_insensitive_version_header_from_first_twenty_lines():
    assert extract_template_version(template(), MARKER) == "v1"
    assert extract_template_version(template().replace("Example-Profile", "example-profile"), MARKER) == "v1"
    with pytest.raises(ProfileTemplateError, match="exactly one"):
        extract_template_version("\n".join(["line"] * 21) + "\nExample-Profile-Version: late", MARKER)
    with pytest.raises(ProfileTemplateError, match="exactly one"):
        extract_template_version(template() + "\nExample-Profile-Version: v2", MARKER)
    with pytest.raises(ProfileTemplateError, match="one non-empty token"):
        extract_template_version(template(version="two words"), MARKER)


def test_parses_sections_normalizes_newlines_and_rejects_duplicates_or_bad_markers():
    files = parse_template_files(template())
    assert tuple(files) == REQUIRED
    assert files["IDENTITY.md"].endswith("\n")
    with pytest.raises(ProfileTemplateError, match="duplicate"):
        parse_template_files(template() + "\n--- file: IDENTITY.md ---\nagain")
    with pytest.raises(ProfileTemplateError, match="malformed"):
        parse_template_files("--- file: ../escape ---\nno")
    with pytest.raises(ProfileTemplateError, match="no file sections"):
        parse_template_files("Example-Profile-Version: v1")


def test_render_replaces_named_or_braced_tokens_and_is_immutable():
    profile = render()
    assert profile.version == "v1"
    assert "Hello HR" in profile.files["IDENTITY.md"]
    with pytest.raises(TypeError):
        profile.files["IDENTITY.md"] = "mutated"

    braced = render_profile_template(
        template(identity="{{NAME}}/{{TITLE}}"),
        version_marker=MARKER,
        required_files=REQUIRED,
        tokens={"{{NAME}}": "HR", "TITLE": "Human Resources"},
    )
    assert "HR/Human Resources" in braced.files["IDENTITY.md"]


def test_render_rejects_missing_required_file_unresolved_token_and_missing_file_version():
    with pytest.raises(ProfileTemplateError, match="missing files"):
        render_profile_template(
            template(), version_marker=MARKER,
            required_files=("IDENTITY.md", "MISSING.md"), tokens={"NAME": "HR"},
        )
    with pytest.raises(ProfileTemplateError, match="unresolved tokens"):
        render(template(identity="{{NAME}} {{UNKNOWN}}"))
    without_marker = template().replace("<!-- example-profile-version: v1 -->\nRules", "Rules")
    with pytest.raises(ProfileTemplateError, match="does not declare"):
        render(without_marker)


@pytest.mark.parametrize("filename", ("../x", "nested/x", "nested\\x", ".", ""))
def test_render_rejects_unsafe_required_filenames(filename):
    with pytest.raises((ProfileTemplateError, UnsafeProfilePathError)):
        render_profile_template(
            template(), version_marker=MARKER,
            required_files=(filename,), tokens={"NAME": "HR"},
        )


def test_archive_manager_template_renders_all_legacy_required_files():
    profile = load_and_render_profile(
        APP_DIR / ARCHIVE_MANAGER_ROLE.profile_template,
        ARCHIVE_MANAGER_ROLE,
        tokens={
            "ARCHIVE_MANAGER_NAME": ARCHIVE_MANAGER_ROLE.display_name,
            "ARCHIVE_MANAGER_EMOJI": ARCHIVE_MANAGER_ROLE.emoji,
            "ARCHIVE_MANAGER_AGENT_ID": ARCHIVE_MANAGER_ROLE.stable_id,
            "ARCHIVE_MANAGER_PROFILE_VERSION": "2026-06-20.2",
        },
    )
    assert profile.version == "2026-06-20.2"
    assert set(ARCHIVE_MANAGER_ROLE.required_files) == set(profile.files)
    assert "不承担普通执行任务" in profile.files["agent.md"]


def test_load_rejects_template_symlink_and_non_utf8(tmp_path):
    real = tmp_path / "real.md"
    real.write_text(template(), encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    with pytest.raises(UnsafeProfilePathError, match="symbolic link"):
        load_and_render_profile(link, ARCHIVE_MANAGER_ROLE, tokens={})

    invalid = tmp_path / "invalid.md"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ProfileTemplateError, match="cannot be read"):
        load_and_render_profile(invalid, ARCHIVE_MANAGER_ROLE, tokens={})


def test_resolve_workspace_accepts_default_and_in_root_configured_paths(tmp_path):
    root = tmp_path / "openclaw"
    assert resolve_safe_workspace(root, "hr") == (root / "workspace-hr").resolve()
    configured = root / "custom" / "hr"
    assert resolve_safe_workspace(root, "hr", configured) == configured.resolve()


@pytest.mark.parametrize("agent_id", ("", "../hr", "HR", "a/b", "a" * 65))
def test_resolve_workspace_rejects_unsafe_agent_ids(tmp_path, agent_id):
    with pytest.raises(UnsafeProfilePathError, match="agent_id"):
        resolve_safe_workspace(tmp_path, agent_id)


def test_resolve_workspace_rejects_root_outside_and_symlink_escape(tmp_path):
    root = tmp_path / "openclaw"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(UnsafeProfilePathError, match="outside"):
        resolve_safe_workspace(root, "hr", outside)
    with pytest.raises(UnsafeProfilePathError, match="must not be"):
        resolve_safe_workspace(root, "hr", root)

    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeProfilePathError, match="symbolic link"):
        resolve_safe_workspace(root, "hr", root / "linked" / "hr")


def test_sync_writes_atomically_then_detects_unchanged_and_repairs_content(tmp_path):
    root = tmp_path / "openclaw"
    workspace = resolve_safe_workspace(root, "hr")
    profile = render()
    first = sync_profile_files(root, workspace, profile, version_marker=MARKER)
    assert first.updated is True
    assert first.written_files == REQUIRED
    assert profile_needs_update(workspace, profile, version_marker=MARKER) is False
    assert not list(workspace.glob("*.tmp"))

    second = sync_profile_files(root, workspace, profile, version_marker=MARKER)
    assert second.updated is False
    assert second.unchanged_files == REQUIRED

    (workspace / "IDENTITY.md").write_text(
        "<!-- example-profile-version: v1 -->\ncorrupted\n", encoding="utf-8",
    )
    assert profile_needs_update(workspace, profile, version_marker=MARKER) is True
    repaired = sync_profile_files(root, workspace, profile, version_marker=MARKER)
    assert repaired.written_files == ("IDENTITY.md",)
    assert (workspace / "IDENTITY.md").read_text(encoding="utf-8") == profile.files["IDENTITY.md"]


def test_sync_repairs_old_version_and_missing_file(tmp_path):
    root = tmp_path / "openclaw"
    workspace = resolve_safe_workspace(root, "hr")
    old = render(template(version="v0"))
    sync_profile_files(root, workspace, old, version_marker=MARKER)
    (workspace / "AGENTS.md").unlink()

    current = render()
    result = sync_profile_files(root, workspace, current, version_marker=MARKER)
    assert result.written_files == REQUIRED
    assert all(read_profile_version((workspace / name).read_text(), MARKER) == "v1" for name in REQUIRED)


def test_sync_rejects_workspace_and_target_symlinks_without_touching_outside(tmp_path):
    root = tmp_path / "openclaw"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "IDENTITY.md"
    sentinel.write_text("outside", encoding="utf-8")
    linked_workspace = root / "workspace-hr"
    linked_workspace.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeProfilePathError, match="symbolic link"):
        sync_profile_files(root, linked_workspace, render(), version_marker=MARKER)
    assert sentinel.read_text(encoding="utf-8") == "outside"

    linked_workspace.unlink()
    linked_workspace.mkdir()
    (linked_workspace / "IDENTITY.md").symlink_to(sentinel)
    with pytest.raises(UnsafeProfilePathError, match="symbolic link"):
        sync_profile_files(root, linked_workspace, render(), version_marker=MARKER)
    assert sentinel.read_text(encoding="utf-8") == "outside"


def test_atomic_write_failure_preserves_existing_file_and_removes_temp(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    workspace = resolve_safe_workspace(root, "hr")
    old = render(template(version="v0"))
    sync_profile_files(root, workspace, old, version_marker=MARKER)
    before = (workspace / "IDENTITY.md").read_text(encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        sync_profile_files(root, workspace, render(), version_marker=MARKER)
    assert (workspace / "IDENTITY.md").read_text(encoding="utf-8") == before
    assert not list(workspace.glob(".*.tmp"))
