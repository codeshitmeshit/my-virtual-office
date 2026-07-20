"""Trusted VO identity checks for Human Resources Agent APIs."""

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_agent_auth import (
    HRAgentAuthenticationError,
    HRAgentAuthenticator,
    HRAgentAuthRequest,
)
from services.hr_repository import HRRepository


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status")
    result.initialize()
    for ai_id, status, provider in (
        ("agent-1", "active", "openclaw"),
        ("inactive", "disabled", "openclaw"),
        ("codex-agent", "active", "codex"),
        ("hermes-agent", "active", "hermes"),
    ):
        result.upsert_agent(
            ai_id=ai_id,
            name=ai_id.title(),
            agent_kind="project",
            provider_kind=provider,
            status=status,
            availability="available",
            source="test",
        )
    return result


@pytest.fixture
def authenticator(repository):
    return HRAgentAuthenticator(repository)


def _request(*, ai_id="agent-1", remote_host="127.0.0.1", origin=None, action="human-resources"):
    return HRAgentAuthRequest(
        remote_host=remote_host,
        origin=origin,
        action=action,
        ai_id=ai_id,
    )


@pytest.mark.parametrize("remote_host", ["127.0.0.1", "127.99.1.4", "::1", "[::1]"])
def test_trusted_identity_accepts_originless_loopback_for_every_registered_provider(
    authenticator, remote_host
):
    for ai_id in ("agent-1", "codex-agent", "hermes-agent"):
        identity = authenticator.authenticate(_request(ai_id=ai_id, remote_host=remote_host))
        assert identity.ai_id == ai_id
        assert identity.provider_kind
        assert not hasattr(identity, "key_id")


@pytest.mark.parametrize("remote_host", ["10.0.0.7", "192.168.1.2", "localhost", ""])
def test_trusted_identity_rejects_non_loopback_hosts(authenticator, remote_host):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(remote_host=remote_host))
    assert error.value.code == "hr_agent_loopback_required"


@pytest.mark.parametrize("origin", ["https://office.example", "null", ""])
def test_trusted_identity_rejects_every_browser_origin_header(authenticator, origin):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(origin=origin))
    assert error.value.code == "hr_agent_browser_origin_forbidden"


@pytest.mark.parametrize("action", [None, "", "project-authoring", "Human Resources"])
def test_trusted_identity_requires_exact_hr_action(authenticator, action):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(action=action))
    assert error.value.code == "hr_agent_action_required"


@pytest.mark.parametrize(
    ("ai_id", "code"),
    [
        (None, "hr_agent_identity_required"),
        ("", "hr_agent_identity_required"),
        ("missing", "hr_agent_unknown"),
        ("inactive", "hr_agent_inactive"),
    ],
)
def test_trusted_identity_requires_a_known_active_directory_agent(authenticator, ai_id, code):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(ai_id=ai_id))
    assert error.value.code == code
