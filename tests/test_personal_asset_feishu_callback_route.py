import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR",
    tempfile.mkdtemp(prefix="vo-personal-asset-feishu-callback-import-"),
)

import server  # noqa: E402


class _OnboardingStub:
    def __init__(self):
        self.calls = []

    def handle_action(self, event, value):
        self.calls.append((event, value))
        return {
            "handled": True,
            "ok": True,
            "queued": True,
            "status": "draft_queued",
        }


def test_runtime_card_callback_routes_personal_asset_form_to_onboarding(tmp_path):
    onboarding = _OnboardingStub()
    previous_getter = server._get_personal_asset_feishu_onboarding
    previous_status_dir = server.STATUS_DIR
    server._get_personal_asset_feishu_onboarding = lambda: onboarding
    server.STATUS_DIR = str(tmp_path)
    try:
        result = server._handle_feishu_card_action(
            {
                "schema": "2.0",
                "header": {
                    "event_type": "card.action.trigger",
                    "event_id": "evt-personal-assets-1",
                },
                "event": {
                    "open_message_id": "om_personal_assets_card",
                    "open_chat_id": "oc_personal_assets_chat",
                    "operator": {"open_id": "ou_owner"},
                    "action": {
                        "value": {
                            "action": "personal_asset_onboarding_submit",
                            "agent_id": "codex-local",
                            "owner_id": "ou_owner",
                        },
                        "form_value": {"preferred_name": "小欧"},
                    },
                },
            }
        )
    finally:
        server._get_personal_asset_feishu_onboarding = previous_getter
        server.STATUS_DIR = previous_status_dir

    assert len(onboarding.calls) == 1
    assert result["ok"] is True
    assert result["outcome"]["status"] == "draft_queued"
    assert result["toast"]["content"] == "表单已收到"

