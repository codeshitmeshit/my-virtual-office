import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_service import PersonalAssetService  # noqa: E402
from services.personal_asset_store import (  # noqa: E402
    PersonalAssetConflictError,
    PersonalAssetStore,
    PersonalAssetValidationError,
)


def make_service(tmp_path):
    return PersonalAssetService(PersonalAssetStore(tmp_path / "assets.json"))


def payload(label, value, category="custom", sensitivity="standard"):
    return {
        "label": label,
        "value": value,
        "category": category,
        "sensitivity": sensitivity,
    }


def test_owner_crud_returns_safe_snapshot_and_preserves_other_entries(tmp_path):
    service = make_service(tmp_path)
    first = service.create_entry(payload("职业", "设计", "occupation"), expected_revision=0)
    second = service.create_entry(payload("兴趣", ["阅读"], "interests"), expected_revision=first["revision"])
    updated = service.update_entry(
        first["entry"]["id"], {"value": "AI 设计"}, expected_revision=second["revision"]
    )
    assert {item["label"] for item in updated["profile"]["entries"]} == {"职业", "兴趣"}
    assert "accessLinks" not in updated["profile"]
    assert "usageRecords" not in updated["profile"]

    deleted = service.delete_entry(
        first["entry"]["id"], expected_revision=updated["revision"]
    )
    assert [item["label"] for item in deleted["profile"]["entries"]] == ["兴趣"]


def test_confirmed_batch_is_all_or_nothing_and_idempotent(tmp_path):
    service = make_service(tmp_path)
    confirmed_changes = [
        {"action": "create", "entry": payload("职业", "产品", "occupation")},
        {"action": "create", "entry": payload("目标", "完成 VO", "office-goals")},
    ]
    created = service.apply_confirmed_batch(
        confirmed_changes,
        expected_revision=0,
        idempotency_key="onboarding:1",
        source={"kind": "onboarding", "agentId": "agent-1", "contextId": "chat-1"},
    )
    assert len(created["profile"]["entries"]) == 2
    repeated = service.apply_confirmed_batch(
        confirmed_changes,
        expected_revision=0,
        idempotency_key="onboarding:1",
        source={"kind": "onboarding", "agentId": "agent-1", "contextId": "chat-1"},
    )
    assert repeated["idempotent"] is True
    assert len(repeated["profile"]["entries"]) == 2
    assert repeated["revision"] == created["revision"]
    with pytest.raises(PersonalAssetConflictError):
        service.apply_confirmed_batch(
            [{"action": "create", "entry": payload("ignored", "ignored")}],
            expected_revision=created["revision"],
            idempotency_key="onboarding:1",
            source={"kind": "onboarding", "agentId": "agent-1", "contextId": "chat-1"},
        )

    before = service.snapshot()
    with pytest.raises(PersonalAssetValidationError):
        service.apply_confirmed_batch(
            [
                {"action": "create", "entry": payload("新增", "ok")},
                {"action": "update", "entryId": "missing", "patch": {"value": "bad"}},
            ],
            expected_revision=before["revision"],
            idempotency_key="onboarding:bad",
            source={"kind": "onboarding", "agentId": "agent-1", "contextId": "chat-1"},
        )
    assert service.snapshot() == before


def test_suggestion_accept_edit_and_reject_are_single_owner_commands(tmp_path):
    service = make_service(tmp_path)
    suggestion = service.submit_suggestion(
        proposal=payload("兴趣", ["阅读"], "interests"),
        source={"kind": "agent", "agentId": "agent-1"},
        idempotency_key="suggest:1",
    )
    accepted = service.accept_suggestion(
        suggestion["suggestion"]["id"],
        expected_revision=suggestion["revision"],
        edited_proposal=payload("兴趣爱好", ["阅读", "徒步"], "interests"),
    )
    assert accepted["entry"]["label"] == "兴趣爱好"
    assert accepted["entry"]["value"] == ["阅读", "徒步"]

    second = service.submit_suggestion(
        proposal=payload("聊天", "简洁", "chat-preferences"),
        source={"kind": "agent", "agentId": "agent-1"},
        idempotency_key="suggest:2",
    )
    rejected = service.reject_suggestion(
        second["suggestion"]["id"], expected_revision=second["revision"]
    )
    assert rejected["suggestion"]["status"] == "rejected"
    assert len(rejected["profile"]["entries"]) == 1


def test_stale_owner_command_has_stable_conflict(tmp_path):
    service = make_service(tmp_path)
    service.create_entry(payload("职业", "产品", "occupation"), expected_revision=0)
    with pytest.raises(PersonalAssetConflictError) as error:
        service.create_entry(payload("兴趣", "阅读", "interests"), expected_revision=0)
    assert error.value.code == "personal_asset_revision_conflict"


def test_post_commit_observer_cannot_turn_local_success_into_failure(tmp_path):
    observed = []

    def failing_observer(profile):
        observed.append(profile["revision"])
        raise RuntimeError("OSS unavailable")

    service = PersonalAssetService(
        PersonalAssetStore(tmp_path / "assets.json"), on_mutation=failing_observer
    )

    created = service.create_entry(payload("职业", "产品"), expected_revision=0)
    suggestion = service.submit_suggestion(
        proposal=payload("兴趣", "阅读"),
        source={"kind": "agent", "agentId": "agent-1"},
        idempotency_key="observer:suggestion",
    )

    assert created["profile"]["entries"][0]["label"] == "职业"
    assert suggestion["revision"] == 2
    assert observed == [1, 2]
