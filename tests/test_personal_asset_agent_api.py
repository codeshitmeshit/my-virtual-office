import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_agent_api import PersonalAssetAgentAPI  # noqa: E402
from services.personal_asset_agent_auth import AuthenticatedPersonalAssetAgent  # noqa: E402
from services.personal_asset_agent_access import PersonalAssetAgentAccess  # noqa: E402
from services.personal_asset_service import PersonalAssetService  # noqa: E402
from services.personal_asset_store import (  # noqa: E402
    PersonalAssetConflictError,
    PersonalAssetStore,
    PersonalAssetValidationError,
)


@pytest.fixture
def context(tmp_path):
    store = PersonalAssetStore(tmp_path / "assets.json")
    service = PersonalAssetService(store)
    first = service.create_entry(
        {"category": "occupation", "label": "职业", "value": "产品设计", "sensitivity": "standard"},
        expected_revision=0,
    )
    second = service.create_entry(
        {"category": "interests", "label": "兴趣", "value": ["阅读"], "sensitivity": "standard"},
        expected_revision=first["revision"],
    )
    access = PersonalAssetAgentAccess(store)
    api = PersonalAssetAgentAPI(service, access)
    identity = AuthenticatedPersonalAssetAgent("agent-1", "Agent One", "codex")
    return store, service, api, identity, second["profile"]["entries"]


def task():
    return {"type": "task", "id": "task-1", "label": "规划", "projectId": "project-1"}


def test_standard_read_returns_only_exact_scope_and_one_usage(context):
    store, _service, api, identity, entries = context
    selected = entries[0]
    response = api.request_context(
        identity,
        {
            "requestId": "read-1",
            "entryIds": [selected["id"]],
            "purpose": "为当前项目规划沟通方式",
            "taskContext": task(),
        },
    )
    assert [item["id"] for item in response["entries"]] == [selected["id"]]
    assert response["status"] == "disclosed"
    assert len(store.internal_snapshot()["usageRecords"]) == 1
    repeated = api.request_context(
        identity,
        {
            "requestId": "read-1",
            "entryIds": [selected["id"]],
            "purpose": "为当前项目规划沟通方式",
            "taskContext": task(),
        },
    )
    assert repeated["entries"] == response["entries"]
    assert len(store.internal_snapshot()["usageRecords"]) == 1


@pytest.mark.parametrize("entry_ids,purpose", [([], "需要资料"), (["*"], "需要全部资料"), (None, "读取完整档案")])
def test_broad_or_empty_read_is_rejected(context, entry_ids, purpose):
    _store, _service, api, identity, _entries = context
    with pytest.raises(PersonalAssetValidationError):
        api.request_context(
            identity,
            {"requestId": "bad", "entryIds": entry_ids, "purpose": purpose, "taskContext": task()},
        )


def test_suggestion_never_updates_entries_until_owner_accepts(context):
    _store, service, api, identity, entries = context
    before_ids = [item["id"] for item in entries]
    result = api.suggest_change(
        identity,
        {
            "requestId": "suggest-1",
            "proposal": {"category": "office-goals", "label": "目标", "value": "完成 VO", "sensitivity": "standard"},
            "taskContext": task(),
        },
    )
    assert result["suggestion"]["status"] == "pending"
    assert [item["id"] for item in service.snapshot()["entries"]] == before_ids


def test_confirmed_onboarding_requires_digest_and_is_idempotent(context):
    _store, service, api, identity, _entries = context
    sensitive_value = "现有敏感值不得进入 Agent 写入响应"
    service.create_entry(
        {
            "category": "fund-focus",
            "label": "资金关注",
            "value": sensitive_value,
            "sensitivity": "sensitive",
        },
        expected_revision=service.snapshot()["revision"],
    )
    changes = [
        {"action": "create", "entry": {"category": "chat-preferences", "label": "聊天偏好", "value": "简洁", "sensitivity": "standard"}}
    ]
    digest = hashlib.sha256(
        json.dumps(changes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = {
        "requestId": "onboarding-1",
        "expectedRevision": service.snapshot()["revision"],
        "confirmedChanges": changes,
        "confirmationSummaryDigest": digest,
        "taskContext": {"type": "chat", "id": "chat-1", "label": "个人资产建档"},
    }
    first = api.apply_confirmed_onboarding(identity, payload)
    second = api.apply_confirmed_onboarding(identity, payload)
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["savedScope"] == second["savedScope"]
    assert first["savedScope"]
    assert "profile" not in first and "entries" not in first
    assert sensitive_value not in json.dumps(first, ensure_ascii=False)
    assert "简洁" not in json.dumps(first, ensure_ascii=False)
    assert [item["label"] for item in service.snapshot()["entries"]].count("聊天偏好") == 1

    bad = dict(payload)
    bad["requestId"] = "onboarding-2"
    bad["confirmationSummaryDigest"] = "0" * 64
    with pytest.raises(PersonalAssetValidationError):
        api.apply_confirmed_onboarding(identity, bad)

    changed = [
        {
            "action": "create",
            "entry": {
                "category": "chat-preferences",
                "label": "聊天偏好",
                "value": "更详细",
                "sensitivity": "standard",
            },
        }
    ]
    reused = {
        **payload,
        "expectedRevision": service.snapshot()["revision"],
        "confirmedChanges": changed,
        "confirmationSummaryDigest": hashlib.sha256(
            json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    with pytest.raises(PersonalAssetConflictError):
        api.apply_confirmed_onboarding(identity, reused)
    assert [item["value"] for item in service.snapshot()["entries"]].count("更详细") == 0


def test_profile_outline_exposes_no_values_and_redacts_sensitive_labels(context):
    _store, service, api, identity, _entries = context
    created = service.create_entry(
        {
            "category": "fund-focus",
            "label": "当前关注资金",
            "value": "仅用于验证且不得出现在目录响应",
            "sensitivity": "sensitive",
        },
        expected_revision=service.snapshot()["revision"],
    )

    outline = api.profile_outline(
        identity,
        {
            "requestId": "outline-1",
            "taskContext": {"type": "chat", "id": "chat-1", "label": "个人资产建档"},
        },
    )

    assert outline["revision"] == created["revision"]
    assert len(outline["entries"]) == 3
    assert all("value" not in entry for entry in outline["entries"])
    sensitive = next(entry for entry in outline["entries"] if entry["sensitivity"] == "sensitive")
    assert sensitive["label"] == "敏感条目"
    assert "仅用于验证" not in json.dumps(outline, ensure_ascii=False)
