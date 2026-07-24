from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.agent_profile_configuration import (  # noqa: E402
    AgentProfileConfigurationService,
    ConfigurationActor,
)
from services.agent_profile_mutations import AgentProfileMutationAPI  # noqa: E402
from services.agent_profile_store import AgentProfileStore  # noqa: E402


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Tokens:
    def __init__(self):
        self.index = 0

    def __call__(self):
        self.index += 1
        return f"undo-token-{self.index:04d}-" + "x" * 32


class Directory:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def profile_changed(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("offline")


def api(tmp_path, *, directory=None, ttl=30):
    clock = Clock()
    store = AgentProfileStore(tmp_path / "profiles.json", now=clock)
    configuration = AgentProfileConfigurationService(store, directory=directory)
    return (
        AgentProfileMutationAPI(
            configuration,
            store,
            now=clock,
            token_factory=Tokens(),
            undo_ttl_seconds=ttl,
        ),
        store,
        clock,
    )


def mutation(field="name", value="Agent A", revision=0, target="agent-a"):
    return {
        "targetAiId": target,
        "field": field,
        "value": value,
        "expectedRevision": revision,
    }


def test_mutation_returns_field_save_state_revision_and_bounded_undo(tmp_path):
    app, store, _clock = api(tmp_path)
    result = app.mutate(ConfigurationActor.agent("agent-a"), mutation())

    assert result.status == 200
    assert result.payload["saveState"] == "saved"
    assert result.payload["field"] == "name"
    assert result.payload["revision"] == 1
    assert len(result.payload["undoToken"]) >= 32
    assert result.payload["undoExpiresAt"].endswith("+00:00")
    assert store.get("agent-a").name == "Agent A"


def test_undo_restores_value_and_is_single_use(tmp_path):
    app, store, _clock = api(tmp_path)
    first = app.mutate(
        ConfigurationActor.agent("agent-a"), mutation(value="First")
    )
    second = app.mutate(
        ConfigurationActor.agent("agent-a"),
        mutation(value="Second", revision=1),
    )

    undone = app.undo(
        ConfigurationActor.agent("agent-a"),
        {
            "undoToken": second.payload["undoToken"],
            "expectedRevision": 2,
        },
    )
    replay = app.undo(
        ConfigurationActor.agent("agent-a"),
        {
            "undoToken": second.payload["undoToken"],
            "expectedRevision": 2,
        },
    )

    assert first.status == 200
    assert undone.status == 200
    assert undone.payload["saveState"] == "undone"
    assert undone.payload["revision"] == 3
    assert store.get("agent-a").name == "First"
    assert replay.status == 410
    assert replay.payload["code"] == "agent_profile_undo_unavailable"


def test_undo_removes_appearance_field_that_was_previously_absent(tmp_path):
    app, store, _clock = api(tmp_path)
    changed = app.mutate(
        ConfigurationActor.agent("agent-a"),
        mutation(field="appearance.hairStyle", value="short"),
    )

    undone = app.undo(
        ConfigurationActor.agent("agent-a"),
        {
            "undoToken": changed.payload["undoToken"],
            "expectedRevision": 1,
        },
    )

    assert undone.status == 200
    assert "hairStyle" not in store.get("agent-a").appearance


def test_expired_undo_does_not_change_data(tmp_path):
    app, store, clock = api(tmp_path, ttl=30)
    changed = app.mutate(
        ConfigurationActor.agent("agent-a"), mutation(value="Saved")
    )
    clock.advance(31)

    result = app.undo(
        ConfigurationActor.agent("agent-a"),
        {
            "undoToken": changed.payload["undoToken"],
            "expectedRevision": 1,
        },
    )

    assert result.status == 410
    assert store.get("agent-a").name == "Saved"


def test_later_edit_makes_earlier_undo_conflict_without_overwrite(tmp_path):
    app, store, _clock = api(tmp_path)
    first = app.mutate(
        ConfigurationActor.agent("agent-a"), mutation(value="First")
    )
    app.mutate(
        ConfigurationActor.agent("agent-a"),
        mutation(value="Later", revision=1),
    )

    result = app.undo(
        ConfigurationActor.agent("agent-a"),
        {
            "undoToken": first.payload["undoToken"],
            "expectedRevision": 1,
        },
    )

    assert result.status == 409
    assert result.payload["code"] == "agent_profile_undo_conflict"
    assert store.get("agent-a").name == "Later"


def test_undo_is_bound_to_original_actor(tmp_path):
    app, store, _clock = api(tmp_path)
    changed = app.mutate(ConfigurationActor.human(), mutation(value="Human"))

    denied = app.undo(
        ConfigurationActor.agent("agent-a"),
        {
            "undoToken": changed.payload["undoToken"],
            "expectedRevision": 1,
        },
    )

    assert denied.status == 403
    assert denied.payload["code"] == "agent_profile_undo_denied"
    assert store.get("agent-a").name == "Human"


def test_cross_agent_mutation_is_denied_without_token(tmp_path):
    app, store, _clock = api(tmp_path)
    result = app.mutate(
        ConfigurationActor.agent("agent-b"),
        mutation(target="agent-a"),
    )

    assert result.status == 403
    assert result.payload["code"] == "agent_profile_mutation_denied"
    assert "undoToken" not in result.payload
    assert store.get("agent-a") is None


def test_malformed_and_restricted_mutations_return_stable_errors(tmp_path):
    app, store, _clock = api(tmp_path)
    malformed = app.mutate(ConfigurationActor.human(), {"targetAiId": "a"})
    restricted = app.mutate(
        ConfigurationActor.human(), mutation(field="provider", value="codex")
    )

    assert malformed.status == 400
    assert malformed.payload["code"] == "agent_profile_command_invalid"
    assert restricted.status == 403
    assert "undoToken" not in restricted.payload
    assert store.get("agent-a") is None


def test_store_failure_returns_failed_without_undo_token(tmp_path, monkeypatch):
    app, store, _clock = api(tmp_path)

    def fail(*_args, **_kwargs):
        raise OSError("disk")

    monkeypatch.setattr(store, "_atomic_write", fail)
    result = app.mutate(ConfigurationActor.human(), mutation())

    assert result.status == 500
    assert result.payload == {
        "ok": False,
        "code": "agent_profile_mutation_failed",
    }


def test_directory_partial_failure_keeps_commit_and_undo(tmp_path):
    directory = Directory(fail=True)
    app, store, _clock = api(tmp_path, directory=directory)

    result = app.mutate(
        ConfigurationActor.agent("agent-a"),
        mutation(field="introduction", value="Hello"),
    )

    assert result.status == 200
    assert result.payload["reconciliationPending"] is True
    assert result.payload["warningCode"] == "agent_directory_reconciliation_pending"
    assert result.payload["undoToken"]
    assert store.get("agent-a").introduction == "Hello"


def test_per_actor_token_bound_evicts_oldest_without_affecting_save(tmp_path):
    clock = Clock()
    store = AgentProfileStore(tmp_path / "profiles.json", now=clock)
    configuration = AgentProfileConfigurationService(store)
    app = AgentProfileMutationAPI(
        configuration,
        store,
        now=clock,
        token_factory=Tokens(),
        max_tokens=2,
        max_tokens_per_actor=1,
    )
    first = app.mutate(ConfigurationActor.human(), mutation(value="One"))
    second = app.mutate(
        ConfigurationActor.human(), mutation(value="Two", revision=1)
    )

    unavailable = app.undo(
        ConfigurationActor.human(),
        {
            "undoToken": first.payload["undoToken"],
            "expectedRevision": 1,
        },
    )
    assert second.status == 200
    assert unavailable.status == 410
