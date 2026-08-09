import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_agent_auth import (  # noqa: E402
    PersonalAssetAgentAuthRequest,
    PersonalAssetAgentAuthenticationError,
    PersonalAssetAgentAuthenticator,
)


import pytest


@pytest.fixture
def authenticator():
    return PersonalAssetAgentAuthenticator()


def request(**overrides):
    values = {
        "remote_host": "127.0.0.1",
        "origin": None,
        "action": "personal-assets",
        "ai_id": "agent-1",
    }
    values.update(overrides)
    return PersonalAssetAgentAuthRequest(**values)


def test_auth_accepts_any_named_agent_from_originless_loopback(authenticator):
    identity = authenticator.authenticate(request())
    assert identity.ai_id == "agent-1"
    assert identity.provider_kind == "vo-runtime"

    assert authenticator.authenticate(request(ai_id="codex-local")).ai_id == "codex-local"
    assert authenticator.authenticate(request(ai_id="not-in-hr")).ai_id == "not-in-hr"

    cases = [
        ({"remote_host": "10.0.0.1"}, "personal_asset_agent_loopback_required"),
        ({"origin": "https://office.example"}, "personal_asset_agent_browser_origin_forbidden"),
        ({"action": "human-decision"}, "personal_asset_agent_action_required"),
        ({"ai_id": ""}, "personal_asset_agent_identity_required"),
        ({"ai_id": "bad id"}, "personal_asset_agent_identity_required"),
    ]
    for overrides, code in cases:
        with pytest.raises(PersonalAssetAgentAuthenticationError) as error:
            authenticator.authenticate(request(**overrides))
        assert error.value.code == code
