from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_session_mint import (
    AgentManagementMintRequest,
    AgentManagementSessionMintService,
)
from services.agent_management_sessions import AgentManagementSessionService
from services.hr_repository import HRRepository


@pytest.fixture
def repository(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    for ai_id, status, provider in (
        ("openclaw-agent", "active", "openclaw"),
        ("codex-agent", "active", "codex"),
        ("hermes-agent", "active", "hermes"),
        ("inactive-agent", "disabled", "openclaw"),
    ):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="project",
            provider_kind=provider,
            status=status,
            availability="available",
            source="test",
        )
    return repository


@pytest.fixture
def mint(repository):
    return AgentManagementSessionMintService(
        repository,
        AgentManagementSessionService(
            max_launch_codes=6,
            max_launch_codes_per_agent=2,
        ),
    )


def _request(
    *,
    ai_id="openclaw-agent",
    remote_host="127.0.0.1",
    origin=None,
    action="agent-management",
):
    return AgentManagementMintRequest(
        remote_host=remote_host,
        origin=origin,
        action=action,
        ai_id=ai_id,
    )


@pytest.mark.parametrize(
    "remote_host",
    ["127.0.0.1", "127.9.8.7", "::1", "[::1]"],
)
def test_originless_loopback_mint_is_provider_neutral(mint, remote_host):
    for ai_id in ("openclaw-agent", "codex-agent", "hermes-agent"):
        result = mint.mint(_request(ai_id=ai_id, remote_host=remote_host))
        assert result.status == 201
        assert result.payload["aiId"] == ai_id
        assert result.payload["launchCode"] in result.payload["launchUrl"]
        assert "provider" not in result.payload


@pytest.mark.parametrize("remote_host", ["10.0.0.2", "localhost", ""])
def test_remote_or_non_ip_request_is_rejected(mint, remote_host):
    result = mint.mint(_request(remote_host=remote_host))
    assert result.status == 403
    assert result.payload["code"] == "agent_management_loopback_required"


@pytest.mark.parametrize("origin", ["https://office.example", "null", ""])
def test_every_browser_origin_header_is_rejected(mint, origin):
    result = mint.mint(_request(origin=origin))
    assert result.status == 403
    assert result.payload["code"] == "agent_management_browser_origin_forbidden"


@pytest.mark.parametrize("action", [None, "", "human-resources", "Agent-Management"])
def test_exact_agent_management_action_is_required(mint, action):
    result = mint.mint(_request(action=action))
    assert result.status == 400
    assert result.payload["code"] == "agent_management_action_required"


@pytest.mark.parametrize(
    ("ai_id", "code"),
    [
        ("", "agent_management_identity_required"),
        ("bad/id", "agent_management_identity_required"),
        ("missing", "agent_management_agent_unknown"),
        ("inactive-agent", "agent_management_agent_inactive"),
    ],
)
def test_identity_must_be_registered_and_active(mint, ai_id, code):
    result = mint.mint(_request(ai_id=ai_id))
    assert result.payload["code"] == code


def test_per_agent_launch_cap_is_reported_as_rate_limit(mint):
    assert mint.mint(_request()).status == 201
    assert mint.mint(_request()).status == 201
    limited = mint.mint(_request())
    assert limited.status == 429
    assert limited.payload["code"] == "agent_management_launch_rate_limited"
