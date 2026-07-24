from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.agent_profile_store import (  # noqa: E402
    AgentProfileConflictError,
    AgentProfileStore,
    AgentProfileStoreError,
    AgentProfileValidationError,
)


NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


def make_store(tmp_path: Path, **kwargs) -> AgentProfileStore:
    return AgentProfileStore(
        tmp_path / "agent-management" / "profiles.json",
        legacy_office_config_path=tmp_path / "office-config.json",
        now=lambda: NOW,
        **kwargs,
    )


def write_legacy(tmp_path: Path) -> None:
    (tmp_path / "office-config.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "visual-codex",
                        "statusKey": "codex-local",
                        "name": "Codex Local",
                        "role": "Backend / Reviewer",
                        "emoji": "🤖",
                        "color": "#ffcc00",
                        "gender": "M",
                        "appearance": {"hairStyle": "short"},
                        "branch": "HQ",
                        "providerKind": "codex",
                        "providerAgentId": "local",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_missing_profile_and_missing_legacy_return_none(tmp_path):
    assert make_store(tmp_path).get("unknown") is None


def test_legacy_profile_is_projected_without_materializing_or_copying_bindings(tmp_path):
    write_legacy(tmp_path)
    store = make_store(tmp_path)

    profile = store.get("codex-local")

    assert profile is not None
    assert profile.revision == 0
    assert profile.source == "legacy-office-config"
    assert profile.name == "Codex Local"
    assert profile.responsibilities == ("Backend / Reviewer",)
    assert profile.specialties == ()
    assert profile.appearance == {
        "hairStyle": "short",
        "emoji": "🤖",
        "color": "#ffcc00",
        "gender": "M",
    }
    assert not store.path.exists()
    assert "branch" not in profile.to_dict()
    assert "providerKind" not in profile.to_dict()


def test_first_update_materializes_legacy_and_increments_revision(tmp_path):
    write_legacy(tmp_path)
    store = make_store(tmp_path)

    updated = store.update(
        "codex-local",
        {"specialties": ["Python", "Review", "python"]},
        expected_revision=0,
    )

    assert updated.revision == 1
    assert updated.specialties == ("Python", "Review")
    assert updated.responsibilities == ("Backend / Reviewer",)
    assert updated.updated_at == NOW.isoformat()
    reopened = make_store(tmp_path).get("codex-local")
    assert reopened == updated
    persisted = json.loads(store.path.read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 1
    assert set(persisted["profiles"]["codex-local"]) == {
        "name",
        "introduction",
        "responsibilities",
        "specialties",
        "appearance",
        "revision",
        "updatedAt",
    }


def test_new_profile_update_and_list_are_stable(tmp_path):
    store = make_store(tmp_path)
    second = store.update("z-agent", {"name": "Z"}, expected_revision=0)
    first = store.update("a-agent", {"name": "A"}, expected_revision=0)

    assert second.revision == first.revision == 1
    assert [profile.ai_id for profile in store.list()] == ["a-agent", "z-agent"]


def test_stale_revision_is_rejected_without_changing_data(tmp_path):
    store = make_store(tmp_path)
    first = store.update("agent-1", {"name": "First"}, expected_revision=0)

    with pytest.raises(AgentProfileConflictError):
        store.update("agent-1", {"name": "Stale"}, expected_revision=0)

    assert store.get("agent-1") == first


def test_concurrent_expected_revision_allows_exactly_one_writer(tmp_path):
    store = make_store(tmp_path)
    store.update("agent-1", {"name": "Initial"}, expected_revision=0)
    barrier = threading.Barrier(2)
    results = []
    failures = []

    def write(name: str) -> None:
        barrier.wait()
        try:
            results.append(
                store.update("agent-1", {"name": name}, expected_revision=1)
            )
        except Exception as exc:  # assertions below identify the exact failure
            failures.append(exc)

    threads = [
        threading.Thread(target=write, args=("One",)),
        threading.Thread(target=write, args=("Two",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], AgentProfileConflictError)
    assert store.get("agent-1").revision == 2


def test_failed_atomic_replace_preserves_previous_document_and_cleans_temp(tmp_path):
    store = make_store(tmp_path)
    store.update("agent-1", {"name": "Initial"}, expected_revision=0)
    before = store.path.read_bytes()

    def fail_replace(_source: str, _target: str) -> None:
        raise OSError("injected")

    failing = make_store(tmp_path, replace=fail_replace)
    with pytest.raises(AgentProfileStoreError, match="write failed"):
        failing.update("agent-1", {"name": "Changed"}, expected_revision=1)

    assert store.path.read_bytes() == before
    assert not list(store.path.parent.glob(f".{store.path.name}.*.tmp"))


@pytest.mark.parametrize(
    "ai_id",
    ["", "has/slash", "has\\slash", "bad\nid", "x" * 257],
)
def test_invalid_stable_ai_ids_are_rejected(tmp_path, ai_id):
    with pytest.raises(AgentProfileValidationError):
        make_store(tmp_path).get(ai_id)


def test_field_bounds_and_unknown_fields_are_rejected(tmp_path):
    store = make_store(tmp_path)
    invalid_patches = (
        {"providerKind": "codex"},
        {"name": "x" * 161},
        {"introduction": "x" * 5_001},
        {"responsibilities": [str(index) for index in range(13)]},
        {"specialties": "Python"},
        {"appearance": {"bad": object()}},
    )
    for patch in invalid_patches:
        with pytest.raises(AgentProfileValidationError):
            store.update("agent-1", patch, expected_revision=0)


def test_returned_appearance_is_a_deep_copy(tmp_path):
    store = make_store(tmp_path)
    profile = store.update(
        "agent-1",
        {"appearance": {"nested": {"value": "original"}}},
        expected_revision=0,
    )

    profile.appearance["nested"]["value"] = "changed"

    assert store.get("agent-1").appearance["nested"]["value"] == "original"


def test_invalid_existing_documents_fail_closed(tmp_path):
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text('{"schemaVersion": 9, "profiles": {}}', encoding="utf-8")

    with pytest.raises(AgentProfileStoreError, match="schema"):
        store.get("agent-1")
