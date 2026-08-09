import json
import os
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_store import (  # noqa: E402
    PersonalAssetConflictError,
    PersonalAssetStore,
    PersonalAssetStoreError,
    PersonalAssetValidationError,
)


def store(tmp_path, **kwargs):
    return PersonalAssetStore(tmp_path / "personal-assets.json", **kwargs)


def entry(label="职业", value="产品设计", *, sensitivity="standard", category="occupation"):
    return {
        "category": category,
        "label": label,
        "value": value,
        "sensitivity": sensitivity,
    }


def test_create_custom_update_delete_round_trip_and_permissions(tmp_path):
    assets = store(tmp_path)
    created = assets.create_entry(entry(), expected_revision=0)
    custom = assets.create_entry(
        entry("常用写作语气", ["简洁", "直接"], category="custom-tone"),
        expected_revision=created["revision"],
    )
    updated = assets.update_entry(
        created["entry"]["id"],
        {"value": "AI 产品设计", "sensitivity": "sensitive"},
        expected_revision=custom["revision"],
    )
    assert updated["entry"]["value"] == "AI 产品设计"
    assert updated["entry"]["sensitivity"] == "sensitive"
    assert updated["entry"]["revision"] == 2
    assert len(updated["snapshot"]["entries"]) == 2

    reopened = PersonalAssetStore(assets.path)
    snapshot = reopened.snapshot()
    assert {item["category"] for item in snapshot["entries"]} == {"occupation", "custom-tone"}
    deleted = reopened.delete_entry(
        created["entry"]["id"], expected_revision=snapshot["revision"]
    )
    assert [item["label"] for item in deleted["snapshot"]["entries"]] == ["常用写作语气"]
    assert stat.S_IMODE(os.stat(assets.path).st_mode) == 0o600


def test_stale_and_invalid_writes_preserve_last_valid_snapshot(tmp_path):
    assets = store(tmp_path)
    created = assets.create_entry(entry(), expected_revision=0)
    before = assets.snapshot()
    with pytest.raises(PersonalAssetConflictError) as conflict:
        assets.update_entry(created["entry"]["id"], {"value": "工程师"}, expected_revision=0)
    assert conflict.value.code == "personal_asset_revision_conflict"
    with pytest.raises(PersonalAssetValidationError):
        assets.create_entry(entry(value={"bad": object()}), expected_revision=before["revision"])
    with pytest.raises(PersonalAssetValidationError):
        assets.create_entry(entry(value={"deep": [[[[[["x"]]]]]]}), expected_revision=before["revision"])
    assert assets.snapshot() == before


def test_existing_corrupt_state_never_falls_back_to_empty(tmp_path):
    path = tmp_path / "personal-assets.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(PersonalAssetStoreError) as error:
        PersonalAssetStore(path).snapshot()
    assert error.value.code == "personal_asset_state_invalid"


def test_failed_atomic_replace_keeps_previous_file(tmp_path):
    assets = store(tmp_path)
    created = assets.create_entry(entry(), expected_revision=0)
    raw_before = assets.path.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("replace unavailable")

    failing = PersonalAssetStore(assets.path, replace=fail_replace)
    with pytest.raises(PersonalAssetStoreError) as error:
        failing.update_entry(created["entry"]["id"], {"value": "new"}, expected_revision=1)
    assert error.value.code == "personal_asset_state_unavailable"
    assert assets.path.read_bytes() == raw_before


def test_suggestion_resolution_is_atomic_and_idempotent(tmp_path):
    assets = store(tmp_path)
    suggestion = assets.create_suggestion(
        {"proposal": entry("兴趣", ["阅读"], category="interests"), "source": {"kind": "agent", "agentId": "a-1"}},
        idempotency_key="suggest:1",
    )
    repeated = assets.create_suggestion(
        {"proposal": entry("different", "ignored"), "source": {"kind": "agent", "agentId": "a-1"}},
        idempotency_key="suggest:1",
    )
    assert repeated["created"] is False
    assert repeated["suggestion"]["id"] == suggestion["suggestion"]["id"]

    accepted = assets.resolve_suggestion(
        suggestion["suggestion"]["id"],
        action="accept",
        expected_revision=suggestion["revision"],
    )
    assert accepted["suggestion"]["status"] == "accepted"
    assert accepted["entry"]["label"] == "兴趣"
    with pytest.raises(PersonalAssetConflictError):
        assets.resolve_suggestion(
            suggestion["suggestion"]["id"], action="reject", expected_revision=accepted["revision"]
        )


def test_usage_records_and_access_links_never_copy_values(tmp_path):
    assets = store(tmp_path, usage_limit=2)
    created = assets.create_entry(entry(value="private-value", sensitivity="sensitive"), expected_revision=0)
    entry_id = created["entry"]["id"]
    assets.put_access_link(
        "request-1",
        {
            "decisionId": "decision-1",
            "agentId": "agent-1",
            "taskContext": {"type": "task", "id": "task-1", "label": "任务"},
            "entryIds": [entry_id],
            "expiresAt": "2099-01-01T00:00:00+00:00",
        },
    )
    for index in range(3):
        assets.record_usage(
            request_id=f"usage-{index}",
            agent_id="agent-1",
            task_context={"type": "task", "id": "task-1"},
            entry_ids=[entry_id],
            outcome="disclosed",
        )
    internal = assets.internal_snapshot()
    assert len(internal["usageRecords"]) == 2
    serialized = json.dumps(
        {"link": internal["accessLinks"]["request-1"], "usage": internal["usageRecords"]},
        ensure_ascii=False,
    )
    assert "private-value" not in serialized
    assert internal["accessLinks"]["request-1"]["decisionId"] == "decision-1"


def test_consume_once_and_usage_are_one_idempotent_transaction(tmp_path):
    assets = store(tmp_path)
    created = assets.create_entry(entry(value="secret", sensitivity="sensitive"), expected_revision=0)
    entry_id = created["entry"]["id"]
    assets.put_access_link(
        "request-1",
        {
            "decisionId": "decision-1",
            "agentId": "agent-1",
            "taskContext": {"type": "task", "id": "task-1", "label": "任务"},
            "entryIds": [entry_id],
            "expiresAt": "2099-01-01T00:00:00+00:00",
        },
    )
    first = assets.consume_access_and_record_usage(
        "request-1", once=True, outcome="disclosed"
    )
    second = assets.consume_access_and_record_usage(
        "request-1", once=True, outcome="disclosed"
    )
    assert first["consumed"] is True
    assert second["consumed"] is False
    assert len(assets.internal_snapshot()["usageRecords"]) == 1


def test_restore_profile_snapshot_is_atomic_and_invalidates_stale_access(tmp_path):
    local = PersonalAssetStore(tmp_path / "local.json")
    local_created = local.create_entry(entry("旧资料", "local"), expected_revision=0)
    local.put_access_link(
        "request-restore",
        {
            "decisionId": "decision-restore",
            "agentId": "agent-1",
            "taskContext": {"type": "task", "id": "task-restore"},
            "entryIds": [local_created["entry"]["id"]],
            "expiresAt": "2099-01-01T00:00:00+00:00",
        },
    )
    remote = PersonalAssetStore(tmp_path / "remote.json")
    remote.create_entry(entry("云端资料", "remote"), expected_revision=0)

    before_revision = local.snapshot()["revision"]
    restored = local.restore_profile_snapshot(
        remote.snapshot(), expected_revision=before_revision
    )

    assert restored["revision"] == before_revision + 1
    assert [item["label"] for item in restored["snapshot"]["entries"]] == ["云端资料"]
    assert local.internal_snapshot()["accessLinks"] == {}

    before = local.snapshot()
    invalid = {**remote.snapshot(), "entries": [{"id": "bad", "label": "missing fields"}]}
    with pytest.raises(PersonalAssetValidationError):
        local.restore_profile_snapshot(invalid, expected_revision=before["revision"])
    assert local.snapshot() == before
