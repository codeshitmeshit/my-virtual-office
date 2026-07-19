"""Security and identity-binding tests for Human Resources Agent authentication."""

import hashlib
import sys
from datetime import datetime, timedelta, timezone
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


NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)
SECRETS = {
    "agent-1": "agent-one-human-resources-grant-00000001",
    "agent-2": "agent-two-human-resources-grant-00000002",
    "revoked": "revoked-human-resources-agent-grant-000003",
    "expired": "expired-human-resources-agent-grant-000004",
}


def _digest(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: NOW)
    result.initialize()
    for ai_id, status, provider in (
        ("agent-1", "active", "openclaw"),
        ("agent-2", "active", "openclaw"),
        ("inactive", "disabled", "openclaw"),
        ("no-grant", "active", "openclaw"),
        ("revoked", "active", "openclaw"),
        ("expired", "active", "openclaw"),
        ("codex-agent", "active", "codex"),
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
    for ai_id in ("agent-1", "agent-2", "revoked", "expired"):
        expiry = NOW - timedelta(seconds=1) if ai_id == "expired" else NOW + timedelta(days=30)
        result.rotate_access_grant(
            ai_id=ai_id,
            key_id=f"key-{ai_id}",
            secret_digest=_digest(SECRETS[ai_id]),
            issued_at=(NOW - timedelta(days=1)).isoformat(),
            expires_at=expiry.isoformat(),
        )
    result.revoke_access_grant(
        ai_id="revoked",
        key_id="key-revoked",
        revoked_at=NOW.isoformat(),
        reason="test revocation",
    )
    return result


@pytest.fixture
def authenticator(repository):
    return HRAgentAuthenticator(repository, clock=lambda: NOW)


def _request(
    *,
    ai_id="agent-1",
    secret=SECRETS["agent-1"],
    remote_host="127.0.0.1",
    origin=None,
    action="human-resources",
    authorization=None,
):
    return HRAgentAuthRequest(
        remote_host=remote_host,
        origin=origin,
        action=action,
        ai_id=ai_id,
        authorization=authorization if authorization is not None else f"Bearer {secret}",
    )


@pytest.mark.parametrize("remote_host", ["127.0.0.1", "127.99.1.4", "::1", "[::1]"])
def test_authentication_accepts_originless_loopback_and_binds_identity(authenticator, remote_host):
    identity = authenticator.authenticate(_request(remote_host=remote_host))
    assert identity.ai_id == "agent-1"
    assert identity.key_id == "key-agent-1"
    assert identity.provider_kind == "openclaw"
    assert SECRETS["agent-1"] not in repr(identity)


@pytest.mark.parametrize("remote_host", ["10.0.0.7", "192.168.1.2", "localhost", ""])
def test_authentication_rejects_non_loopback_or_spoofed_hosts(authenticator, remote_host):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(remote_host=remote_host))
    assert error.value.code == "hr_agent_loopback_required"


@pytest.mark.parametrize("origin", ["https://office.example", "null", ""])
def test_authentication_rejects_every_browser_origin_header(authenticator, origin):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(origin=origin))
    assert error.value.code == "hr_agent_browser_origin_forbidden"


@pytest.mark.parametrize("action", [None, "", "project-authoring", "Human Resources"])
def test_authentication_requires_exact_hr_action(authenticator, action):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(action=action))
    assert error.value.code == "hr_agent_action_required"


@pytest.mark.parametrize(
    ("authorization", "code"),
    [
        (None, "hr_agent_bearer_required"),
        ("", "hr_agent_bearer_required"),
        ("Basic abc", "hr_agent_bearer_required"),
        ("Bearer short", "hr_agent_bearer_required"),
        ("Bearer contains whitespace", "hr_agent_bearer_required"),
    ],
)
def test_authentication_rejects_missing_or_malformed_bearer(
    authenticator, authorization, code
):
    request = _request()
    request = HRAgentAuthRequest(
        remote_host=request.remote_host,
        origin=request.origin,
        action=request.action,
        ai_id=request.ai_id,
        authorization=authorization,
    )
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(request)
    assert error.value.code == code


@pytest.mark.parametrize(
    ("ai_id", "secret", "code"),
    [
        ("missing", SECRETS["agent-1"], "hr_agent_unknown"),
        ("inactive", SECRETS["agent-1"], "hr_agent_inactive"),
        ("no-grant", SECRETS["agent-1"], "hr_agent_grant_missing"),
        ("expired", SECRETS["expired"], "hr_agent_grant_expired"),
        ("revoked", SECRETS["revoked"], "hr_agent_grant_revoked"),
        ("codex-agent", SECRETS["agent-1"], "hr_agent_provider_unsupported"),
    ],
)
def test_authentication_rejects_unknown_inactive_expired_revoked_and_unsupported(
    authenticator, ai_id, secret, code
):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(ai_id=ai_id, secret=secret))
    assert error.value.code == code


def test_header_spoofing_cannot_use_another_agents_grant(authenticator):
    with pytest.raises(HRAgentAuthenticationError) as error:
        authenticator.authenticate(_request(ai_id="agent-1", secret=SECRETS["agent-2"]))
    assert error.value.code == "hr_agent_grant_mismatch"

    identity = authenticator.authenticate(_request(ai_id="agent-2", secret=SECRETS["agent-2"]))
    assert identity.ai_id == "agent-2"


def test_digest_match_uses_constant_time_comparison(repository, monkeypatch):
    calls = []

    def compare(left, right):
        calls.append((left, right))
        return left == right

    monkeypatch.setattr("services.hr_agent_auth.hmac.compare_digest", compare)
    authenticator = HRAgentAuthenticator(repository, clock=lambda: NOW)
    authenticator.authenticate(_request())
    with pytest.raises(HRAgentAuthenticationError):
        authenticator.authenticate(_request(secret=SECRETS["agent-2"]))
    assert len(calls) == 2
    assert all(len(left) == len(right) == 64 for left, right in calls)
