import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_agent_auth import PersonalAssetAgentAuthRequest  # noqa: E402
from services.personal_asset_http import AGENT_PREFIX, MANAGEMENT_PREFIX, PersonalAssetHTTPRoutes  # noqa: E402
from services.personal_asset_runtime import build_personal_asset_runtime  # noqa: E402
from services.personal_asset_feishu_onboarding import PersonalAssetFeishuOnboarding  # noqa: E402
from services.personal_asset_oss_availability_http import OSS_AVAILABILITY_PATH  # noqa: E402
from services.personal_asset_sync_http import (  # noqa: E402
    SYNC_NOW_PATH,
    SYNC_PREFERENCES_PATH,
)


class Decisions:
    def create(self, payload, *, agent_id=""):
        decision = {"id": "decision-1", "status": "pending", "source": payload["source"], "resolution": None}
        return {"created": True, "decision": decision, "snapshot": {"revision": 1, "decisions": [decision]}}

    def snapshot(self):
        return {"revision": 0, "decisions": []}


@pytest.fixture
def runtime(tmp_path):
    return build_personal_asset_runtime(
        status_dir=tmp_path / "status", decision_workflow=Decisions()
    )


def auth(ai_id="agent-1", *, origin=None):
    return PersonalAssetAgentAuthRequest(
        remote_host="127.0.0.1", origin=origin, action="personal-assets", ai_id=ai_id
    )


def test_route_recognition_is_narrow():
    assert PersonalAssetHTTPRoutes.handles(MANAGEMENT_PREFIX)
    assert PersonalAssetHTTPRoutes.handles(f"{AGENT_PREFIX}/request-context")
    assert PersonalAssetHTTPRoutes.is_management(f"{MANAGEMENT_PREFIX}/entries")
    assert not PersonalAssetHTTPRoutes.handles("/api/human-decisions")
    assert not PersonalAssetHTTPRoutes.handles("/api/personal-assets-extra")


def test_management_crud_and_suggestion_routes(runtime):
    routes = runtime.routes
    empty = routes.management_get(MANAGEMENT_PREFIX)
    assert empty.status == 200 and empty.payload["profile"]["entries"] == []
    assert empty.payload["sync"]["enabled"] is True
    created = routes.management_post(
        f"{MANAGEMENT_PREFIX}/entries",
        {"expectedRevision": 0, "entry": {"category": "occupation", "label": "职业", "value": "产品", "sensitivity": "standard"}},
    )
    assert created.status == 201
    entry_id = created.payload["entry"]["id"]
    updated = routes.management_post(
        f"{MANAGEMENT_PREFIX}/entries/{entry_id}",
        {"operation": "update", "expectedRevision": created.payload["revision"], "patch": {"value": "AI 产品"}},
    )
    assert updated.status == 200 and updated.payload["entry"]["value"] == "AI 产品"
    deleted = routes.management_post(
        f"{MANAGEMENT_PREFIX}/entries/{entry_id}",
        {"operation": "delete", "expectedRevision": updated.payload["revision"]},
    )
    assert deleted.status == 200 and deleted.payload["profile"]["entries"] == []


def test_agent_auth_and_operations_are_transport_free(runtime):
    routes = runtime.routes
    created = routes.management_post(
        f"{MANAGEMENT_PREFIX}/entries",
        {"expectedRevision": 0, "entry": {"category": "occupation", "label": "职业", "value": "产品", "sensitivity": "standard"}},
    )
    entry_id = created.payload["entry"]["id"]
    response = routes.agent_post(
        f"{AGENT_PREFIX}/request-context",
        {"requestId": "read-1", "entryIds": [entry_id], "purpose": "项目规划", "taskContext": {"type": "task", "id": "task-1", "label": "规划"}},
        auth(),
    )
    assert response.status == 200 and response.payload["status"] == "disclosed"

    forbidden = routes.agent_post(
        f"{AGENT_PREFIX}/request-context", {}, auth(origin="https://office.example")
    )
    assert forbidden.status == 403
    assert forbidden.payload["code"] == "personal_asset_agent_browser_origin_forbidden"


def test_agent_not_registered_in_hr_can_write_confirmed_personal_assets(runtime):
    changes = [
        {
            "action": "create",
            "entry": {
                "category": "chat-preferences",
                "label": "聊天偏好",
                "value": "简洁直接",
                "sensitivity": "standard",
            },
        }
    ]
    canonical = json.dumps(
        changes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    response = runtime.routes.agent_post(
        f"{AGENT_PREFIX}/apply-confirmed-onboarding",
        {
            "requestId": "onboarding-codex-local",
            "expectedRevision": 0,
            "confirmedChanges": changes,
            "confirmationSummaryDigest": hashlib.sha256(canonical).hexdigest(),
            "taskContext": {"type": "chat", "id": "chat-1", "label": "个人资产建档"},
        },
        auth("codex-local"),
    )

    assert response.status == 200
    assert response.payload["savedScope"]
    assert runtime.routes.management_get(MANAGEMENT_PREFIX).payload["profile"]["entries"][0]["value"] == "简洁直接"


def test_agent_profile_outline_route_returns_metadata_only(runtime):
    routes = runtime.routes
    routes.management_post(
        f"{MANAGEMENT_PREFIX}/entries",
        {
            "expectedRevision": 0,
            "entry": {
                "category": "occupation",
                "label": "职业",
                "value": "产品",
                "sensitivity": "standard",
            },
        },
    )
    response = routes.agent_post(
        f"{AGENT_PREFIX}/profile-outline",
        {
            "requestId": "outline-1",
            "taskContext": {"type": "chat", "id": "chat-1", "label": "个人资产建档"},
        },
        auth(),
    )
    assert response.status == 200
    assert response.payload["entries"][0]["label"] == "职业"
    assert "value" not in response.payload["entries"][0]


def test_agent_can_open_grouped_feishu_onboarding_form(tmp_path):
    delivered = []
    onboarding = PersonalAssetFeishuOnboarding(
        deliver_form=lambda message_id, intent: delivered.append((message_id, intent))
        or {"ok": True, "messageId": "om_card"}
    )
    local_runtime = build_personal_asset_runtime(
        status_dir=tmp_path / "status",
        decision_workflow=Decisions(),
        feishu_onboarding=onboarding,
    )
    response = local_runtime.routes.agent_post(
        f"{AGENT_PREFIX}/feishu-onboarding-form",
        {
            "requestId": "form-route-1",
            "expectedRevision": 0,
            "sourceContext": {
                "sourceApp": "feishu",
                "sourceSurface": "feishu-dm",
                "sourceMessageId": "om_source",
                "conversationId": "conversation-1",
                "feishuChatId": "oc_chat",
                "chatType": "p2p",
                "ownerId": "ou_owner",
            },
        },
        auth("codex-local"),
    )

    assert response.status == 202
    assert response.payload["status"] == "form_delivered"
    assert delivered[0][0] == "om_source"
    assert delivered[0][1]["inputs"][0]["section"] == "基本信息"


def test_http_maps_validation_conflict_and_unknown_routes(runtime):
    routes = runtime.routes
    invalid = routes.management_post(f"{MANAGEMENT_PREFIX}/entries", {})
    assert invalid.status == 400 and invalid.payload["code"] == "personal_asset_invalid"
    missing = routes.management_post(f"{MANAGEMENT_PREFIX}/unknown", {})
    assert missing.status == 404 and missing.payload["code"] == "personal_asset_route_not_found"


def test_management_sync_commands_stay_inside_personal_assets_routes(runtime):
    routes = runtime.routes

    disabled = routes.management_post(SYNC_PREFERENCES_PATH, {"enabled": False})
    enabled = routes.management_post(SYNC_PREFERENCES_PATH, {"enabled": True})
    queued = routes.management_post(SYNC_NOW_PATH, {})

    assert disabled.status == 200 and disabled.payload["sync"]["enabled"] is False
    assert enabled.status == 200 and enabled.payload["sync"]["enabled"] is True
    assert queued.status == 202 and queued.payload["sync"]["status"] == "pending"
    assert PersonalAssetHTTPRoutes.handles(SYNC_NOW_PATH)


def test_management_get_exposes_lazy_oss_availability_without_affecting_snapshot(runtime):
    availability = runtime.routes.management_get(OSS_AVAILABILITY_PATH)
    snapshot = runtime.routes.management_get(MANAGEMENT_PREFIX)

    assert availability.status == 200
    assert availability.payload["availability"]["status"] == "unconfigured"
    assert availability.payload["availability"]["code"] == "oss_configuration_unavailable"
    assert snapshot.status == 200
    assert "availability" not in snapshot.payload
