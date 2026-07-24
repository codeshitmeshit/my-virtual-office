from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.agent_profile_configuration import (  # noqa: E402
    APPEARANCE_FIELDS,
    ActorKind,
    AgentProfileAuthorizationError,
    AgentProfileCommandError,
    AgentProfileConfigurationService,
    ConfigurationActor,
    ProfileMutationCommand,
)
from services.agent_profile_store import AgentProfileStore  # noqa: E402


class DirectoryRecorder:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    def profile_changed(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


def service(tmp_path, directory=None):
    store = AgentProfileStore(
        tmp_path / "profiles.json",
        now=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
    )
    return AgentProfileConfigurationService(store, directory=directory), store


@pytest.mark.parametrize(
    ("actor", "target", "allowed"),
    [
        (ConfigurationActor.human(), "agent-a", True),
        (ConfigurationActor.agent("agent-a"), "agent-a", True),
        (ConfigurationActor.agent("agent-a"), "agent-b", False),
    ],
)
def test_actor_matrix_for_low_risk_name(tmp_path, actor, target, allowed):
    app, store = service(tmp_path)
    command = ProfileMutationCommand(target, "name", "Updated", 0)

    if not allowed:
        with pytest.raises(AgentProfileAuthorizationError):
            app.mutate(actor, command)
        assert store.get(target) is None
        return

    result = app.mutate(actor, command)
    assert result.profile.name == "Updated"
    assert result.profile.revision == 1


def test_human_can_update_another_agent_but_not_restricted_fields(tmp_path):
    app, store = service(tmp_path)
    result = app.mutate(
        ConfigurationActor.human(),
        ProfileMutationCommand("agent-a", "introduction", "I review APIs.", 0),
    )
    assert result.profile.introduction == "I review APIs."

    for field in (
        "provider",
        "providerKind",
        "branch",
        "workspace",
        "assignment",
        "binding",
        "create",
        "delete",
    ):
        with pytest.raises(AgentProfileAuthorizationError):
            app.mutate(
                ConfigurationActor.human(),
                ProfileMutationCommand("agent-a", field, "forbidden", 1),
            )
    assert store.get("agent-a").revision == 1


@pytest.mark.parametrize(
    ("field", "value", "stored"),
    [
        ("appearance.hairStyle", "short", ("hairStyle", "short")),
        ("appearance.glasses", "none", ("glasses", None)),
        ("appearance.color", "#AABBCC", ("color", "#aabbcc")),
        ("appearance.emoji", "🧑‍💻", ("emoji", "🧑‍💻")),
        ("appearance.hairHighlight", None, ("hairHighlight", None)),
    ],
)
def test_appearance_fields_are_allowlisted_and_normalized(
    tmp_path, field, value, stored
):
    app, _store = service(tmp_path)
    result = app.mutate(
        ConfigurationActor.agent("agent-a"),
        ProfileMutationCommand("agent-a", field, value, 0),
    )
    key, expected = stored
    assert result.profile.appearance.get(key) == expected


def test_every_declared_appearance_field_has_a_validation_path(tmp_path):
    assert {
        "gender",
        "hairStyle",
        "eyebrowStyle",
        "facialHair",
        "costume",
        "headwear",
        "glasses",
        "heldItem",
        "deskItem",
        "color",
        "skinTone",
        "hairColor",
        "hairHighlight",
        "eyeColor",
        "facialHairColor",
        "headwearColor",
        "glassesColor",
        "emoji",
    } == APPEARANCE_FIELDS


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("appearance.hairStyle", "not-real"),
        ("appearance.color", "red"),
        ("appearance.emoji", ""),
        ("appearance.unknown", "value"),
    ],
)
def test_invalid_appearance_values_fail_before_persistence(tmp_path, field, value):
    app, store = service(tmp_path)
    with pytest.raises(AgentProfileCommandError):
        app.mutate(
            ConfigurationActor.agent("agent-a"),
            ProfileMutationCommand("agent-a", field, value, 0),
        )
    assert store.get("agent-a") is None


def test_one_field_command_preserves_other_fields_and_revision(tmp_path):
    app, _store = service(tmp_path)
    first = app.mutate(
        ConfigurationActor.agent("agent-a"),
        ProfileMutationCommand(
            "agent-a", "responsibilities", ["Backend"], 0
        ),
    )
    second = app.mutate(
        ConfigurationActor.agent("agent-a"),
        ProfileMutationCommand("agent-a", "specialties", ["Python"], 1),
    )

    assert first.profile.revision == 1
    assert second.profile.revision == 2
    assert second.profile.responsibilities == ("Backend",)
    assert second.profile.specialties == ("Python",)


def test_directory_reconciliation_receives_only_descriptive_profile_changes(tmp_path):
    directory = DirectoryRecorder()
    app, _store = service(tmp_path, directory)
    result = app.mutate(
        ConfigurationActor.agent("agent-a"),
        ProfileMutationCommand("agent-a", "name", "Agent A", 0),
    )
    appearance = app.mutate(
        ConfigurationActor.agent("agent-a"),
        ProfileMutationCommand("agent-a", "appearance.hairStyle", "short", 1),
    )

    assert result.reconciliation_pending is False
    assert appearance.reconciliation_pending is False
    assert directory.calls == [
        {
            "ai_id": "agent-a",
            "field": "name",
            "value": "Agent A",
            "revision": 1,
        }
    ]


def test_directory_failure_reports_pending_without_rolling_back_commit(tmp_path):
    directory = DirectoryRecorder(RuntimeError("offline"))
    app, store = service(tmp_path, directory)

    result = app.mutate(
        ConfigurationActor.agent("agent-a"),
        ProfileMutationCommand("agent-a", "introduction", "Hello", 0),
    )

    assert result.profile.revision == 1
    assert result.reconciliation_pending is True
    assert result.warning_code == "agent_directory_reconciliation_pending"
    assert store.get("agent-a").introduction == "Hello"


def test_responsibility_and_specialty_are_recommendation_only(tmp_path):
    app, _store = service(tmp_path)
    first = app.mutate(
        ConfigurationActor.human(),
        ProfileMutationCommand(
            "agent-a", "responsibilities", ["Backend", "Review"], 0
        ),
    )
    second = app.mutate(
        ConfigurationActor.human(),
        ProfileMutationCommand(
            "agent-a", "specialties", ["Python", "review"], 1
        ),
    )

    assert app.recommendation_terms(second.profile) == (
        "Backend",
        "Review",
        "Python",
    )
    assert app.assignment_allowed(first.profile, ("Design",)) is True
    assert app.assignment_allowed(second.profile, ()) is True


def test_actor_and_command_validation(tmp_path):
    assert ConfigurationActor.human().kind is ActorKind.HUMAN
    with pytest.raises(AgentProfileCommandError):
        ConfigurationActor.agent("")
    with pytest.raises(AgentProfileCommandError):
        ProfileMutationCommand("agent-a", "name", "x", -1)

    app, _store = service(tmp_path)
    with pytest.raises(AgentProfileAuthorizationError):
        app.mutate(
            object(),
            ProfileMutationCommand("agent-a", "name", "x", 0),
        )


def test_module_does_not_import_legacy_entrypoint_or_http():
    source = (
        ROOT / "app" / "services" / "agent_profile_configuration.py"
    ).read_text(encoding="utf-8")
    assert "import server" not in source
    assert "http.server" not in source
    assert "OfficeHandler" not in source
