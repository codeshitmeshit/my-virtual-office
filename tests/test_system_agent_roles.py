"""Policy and validation coverage for shared VO system-Agent roles."""

import dataclasses
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.system_agent_roles import (
    ARCHIVE_MANAGER_ROLE,
    DEFAULT_SYSTEM_AGENT_ROLES,
    HR_ROLE,
    SystemAgentRole,
    SystemAgentRoleError,
    SystemAgentRoleRegistry,
    resolve_system_agent_role,
)


def make_role(**overrides):
    values = {
        "role_key": "future_agent",
        "stable_id": "future-agent",
        "display_name": "Future Agent",
        "emoji": "🔮",
        "provider_kind": "openclaw",
        "profile_template": "future-agent-profile.md",
        "version_marker": "future-agent-profile-version",
        "required_files": ("IDENTITY.md", "AGENTS.md"),
        "assignable": False,
        "deletable": False,
        "meeting_eligible": True,
        "automatic_work_categories": ("future_work",),
        "aliases": ("未来 Agent",),
    }
    values.update(overrides)
    return SystemAgentRole(**values)


def test_default_roles_are_immutable_and_preserve_distinct_policies():
    assert dataclasses.is_dataclass(ARCHIVE_MANAGER_ROLE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ARCHIVE_MANAGER_ROLE.assignable = True

    assert ARCHIVE_MANAGER_ROLE.stable_id == "archive-manager"
    assert ARCHIVE_MANAGER_ROLE.assignable is False
    assert ARCHIVE_MANAGER_ROLE.deletable is False
    assert ARCHIVE_MANAGER_ROLE.meeting_eligible is False
    assert {"MEMORY.md", "HEARTBEAT.md"}.issubset(ARCHIVE_MANAGER_ROLE.required_files)

    assert HR_ROLE.stable_id == "hr"
    assert HR_ROLE.assignable is False
    assert HR_ROLE.deletable is False
    assert HR_ROLE.meeting_eligible is True
    assert HR_ROLE.automatic_work_categories != ARCHIVE_MANAGER_ROLE.automatic_work_categories


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("archive-manager", ARCHIVE_MANAGER_ROLE),
        ("档案管理员", ARCHIVE_MANAGER_ROLE),
        ({"statusKey": "archive-manager"}, ARCHIVE_MANAGER_ROLE),
        ({"systemRole": "archive_manager", "id": "renamed"}, ARCHIVE_MANAGER_ROLE),
        ("hr", HR_ROLE),
        ("HR", HR_ROLE),
        ("Hr", HR_ROLE),
        ({"agentId": "hr"}, HR_ROLE),
        ("ordinary-agent", None),
        ({"systemRole": "unknown", "id": "ordinary-agent"}, None),
        (None, None),
    ],
)
def test_default_registry_resolves_only_stable_exact_identities(candidate, expected):
    assert resolve_system_agent_role(candidate) is expected


def test_persisted_provider_identity_supports_rename_without_fuzzy_matching():
    persisted = {
        "archive_manager": ("provider-archive-42", "档案管理员（已接入）"),
        "hr": ("provider-hr-9",),
    }
    assert DEFAULT_SYSTEM_AGENT_ROLES.resolve(
        "provider-archive-42", persisted_identities=persisted,
    ) is ARCHIVE_MANAGER_ROLE
    assert DEFAULT_SYSTEM_AGENT_ROLES.resolve(
        {"name": "档案管理员（已接入）"}, persisted_identities=persisted,
    ) is ARCHIVE_MANAGER_ROLE
    assert DEFAULT_SYSTEM_AGENT_ROLES.resolve(
        "provider-archive", persisted_identities=persisted,
    ) is None


def test_unknown_agents_keep_ordinary_default_policies():
    registry = DEFAULT_SYSTEM_AGENT_ROLES
    assert registry.is_assignable("ordinary-agent") is True
    assert registry.is_deletable("ordinary-agent") is True
    assert registry.is_meeting_eligible("ordinary-agent") is True

    assert registry.is_assignable("archive-manager") is False
    assert registry.is_deletable("hr") is False
    assert registry.is_meeting_eligible("archive-manager") is False
    assert registry.is_meeting_eligible("hr") is True


def test_future_role_registration_requires_no_domain_subclass():
    future = make_role()
    registry = SystemAgentRoleRegistry((ARCHIVE_MANAGER_ROLE, HR_ROLE, future))
    assert registry.require("future_agent") is future
    assert registry.resolve("未来 Agent") is future
    assert registry.is_assignable("future-agent") is False
    assert registry.is_meeting_eligible("future-agent") is True
    with pytest.raises(KeyError, match="unknown system-Agent role"):
        registry.require("missing")


@pytest.mark.parametrize(
    "overrides",
    [
        {"role_key": "Invalid-Key"},
        {"stable_id": "../unsafe"},
        {"stable_id": "UPPER"},
        {"display_name": " "},
        {"display_name": " Padded"},
        {"emoji": ""},
        {"provider_kind": "OpenClaw"},
        {"profile_template": "../profile.md"},
        {"required_files": ()},
        {"required_files": ("AGENTS.md", "AGENTS.md")},
        {"required_files": ("nested/AGENTS.md",)},
        {"required_files": ("nested\\AGENTS.md",)},
        {"automatic_work_categories": ("not-valid",)},
        {"automatic_work_categories": ("same", "same")},
        {"aliases": ("future-agent",)},
        {"aliases": (" padded",)},
    ],
)
def test_role_validation_rejects_invalid_or_ambiguous_definitions(overrides):
    with pytest.raises(SystemAgentRoleError):
        make_role(**overrides)


def test_registry_rejects_conflicting_keys_and_cross_role_identities():
    with pytest.raises(SystemAgentRoleError, match="duplicate.*role_key"):
        SystemAgentRoleRegistry((make_role(), make_role(stable_id="other-agent")))

    with pytest.raises(SystemAgentRoleError, match="identity.*conflicts"):
        SystemAgentRoleRegistry((make_role(), make_role(
            role_key="other_agent",
            stable_id="other-agent",
            display_name="Other Agent",
            aliases=("Future Agent",),
        )))


def test_conflicting_persisted_identity_fails_closed():
    with pytest.raises(SystemAgentRoleError, match="conflicting"):
        DEFAULT_SYSTEM_AGENT_ROLES.resolve(
            "provider-duplicate",
            persisted_identities={
                "archive_manager": ("provider-duplicate",),
                "hr": ("provider-duplicate",),
            },
        )
