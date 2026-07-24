from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.agent_management_confirmations import (  # noqa: E402
    HIGH_RISK_ACTIONS,
    AgentManagementConfirmationService,
    ConfirmationConflictError,
    ConfirmationDeniedError,
    ConfirmationExpiredError,
    ConfirmationValidationError,
)
from services.agent_profile_configuration import ConfigurationActor  # noqa: E402


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Tokens:
    def __init__(self):
        self.index = 0

    def __call__(self):
        self.index += 1
        return f"confirmation-{self.index:04d}-" + "x" * 32


def service(*, ttl=60, max_challenges=512, max_per_actor=20):
    clock = Clock()
    confirmation = AgentManagementConfirmationService(
        now=clock,
        token_factory=Tokens(),
        ttl_seconds=ttl,
        max_challenges=max_challenges,
        max_per_actor=max_per_actor,
    )
    return confirmation, clock


def issue(confirmation, actor=None, **overrides):
    values = {
        "target_ai_id": "agent-a",
        "action": "branch",
        "before": {"branch": "HQ"},
        "after": {"branch": "ENG"},
        "revision": 4,
    }
    values.update(overrides)
    return confirmation.issue(actor or ConfigurationActor.human(), **values)


def body(challenge, **overrides):
    values = {
        "challengeToken": challenge.token,
        "targetAiId": challenge.target_ai_id,
        "action": challenge.action,
        "before": {"branch": "HQ"},
        "after": {"branch": "ENG"},
        "revision": challenge.revision,
    }
    values.update(overrides)
    return values


def test_all_specified_high_risk_actions_are_supported():
    assert HIGH_RISK_ACTIONS == {
        "provider",
        "branch",
        "workspace",
        "assignment",
        "binding",
        "create",
        "delete",
    }


@pytest.mark.parametrize("action", sorted(HIGH_RISK_ACTIONS))
def test_issue_and_consume_bind_every_high_risk_action(action):
    confirmation, _clock = service()
    challenge = issue(
        confirmation,
        action=action,
        before={"value": "before"},
        after={"value": "after"},
    )
    request = body(
        challenge,
        before={"value": "before"},
        after={"value": "after"},
    )

    confirmed = confirmation.consume(
        ConfigurationActor.human(), request, current_revision=4
    )

    assert confirmed.action == action
    assert confirmed.target_ai_id == "agent-a"
    assert confirmed.revision == 4
    assert confirmed.change_digest == challenge.change_digest


def test_canonical_digest_is_key_order_independent_but_value_sensitive():
    first = AgentManagementConfirmationService.change_digest(
        {"a": 1, "b": 2}, {"nested": {"x": 1, "y": 2}}
    )
    reordered = AgentManagementConfirmationService.change_digest(
        {"b": 2, "a": 1}, {"nested": {"y": 2, "x": 1}}
    )
    changed = AgentManagementConfirmationService.change_digest(
        {"a": 1, "b": 2}, {"nested": {"x": 2, "y": 2}}
    )
    assert first == reordered
    assert changed != first


def test_boolean_only_confirmation_is_rejected():
    confirmation, _clock = service()
    with pytest.raises(ConfirmationValidationError):
        confirmation.consume(
            ConfigurationActor.human(),
            {"confirmed": True},
            current_revision=0,
        )


@pytest.mark.parametrize(
    ("change", "current_revision"),
    [
        ({"targetAiId": "agent-b"}, 4),
        ({"action": "workspace"}, 4),
        ({"before": {"branch": "OTHER"}}, 4),
        ({"after": {"branch": "OTHER"}}, 4),
        ({"revision": 5}, 4),
        ({}, 5),
    ],
)
def test_payload_substitution_or_stale_revision_consumes_and_rejects(
    change, current_revision
):
    confirmation, _clock = service()
    challenge = issue(confirmation)
    request = body(challenge, **change)

    with pytest.raises(ConfirmationConflictError):
        confirmation.consume(
            ConfigurationActor.human(),
            request,
            current_revision=current_revision,
        )
    with pytest.raises(ConfirmationExpiredError):
        confirmation.consume(
            ConfigurationActor.human(),
            body(challenge),
            current_revision=4,
        )


def test_confirmation_is_bound_to_actor_without_consuming_on_wrong_actor():
    confirmation, _clock = service()
    challenge = issue(confirmation, actor=ConfigurationActor.human())

    with pytest.raises(ConfirmationDeniedError):
        confirmation.consume(
            ConfigurationActor.agent("agent-a"),
            body(challenge),
            current_revision=4,
        )

    confirmed = confirmation.consume(
        ConfigurationActor.human(), body(challenge), current_revision=4
    )
    assert confirmed.action == "branch"


def test_confirmation_is_single_use():
    confirmation, _clock = service()
    challenge = issue(confirmation)
    confirmation.consume(
        ConfigurationActor.human(), body(challenge), current_revision=4
    )

    with pytest.raises(ConfirmationExpiredError):
        confirmation.consume(
            ConfigurationActor.human(), body(challenge), current_revision=4
        )


def test_expired_confirmation_is_rejected():
    confirmation, clock = service(ttl=5)
    challenge = issue(confirmation)
    clock.advance(6)

    with pytest.raises(ConfirmationExpiredError):
        confirmation.consume(
            ConfigurationActor.human(), body(challenge), current_revision=4
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_ai_id": ""},
        {"target_ai_id": "bad/id"},
        {"action": "not-risky"},
        {"revision": -1},
        {"before": {"bad": object()}},
        {"after": {"large": "x" * 33_000}},
    ],
)
def test_issue_validation_rejects_invalid_changes(kwargs):
    confirmation, _clock = service()
    with pytest.raises(ConfirmationValidationError):
        issue(confirmation, **kwargs)


def test_actor_and_global_bounds_evict_oldest_challenges():
    confirmation, _clock = service(max_challenges=2, max_per_actor=1)
    first = issue(confirmation, target_ai_id="agent-a")
    second = issue(confirmation, target_ai_id="agent-b")

    with pytest.raises(ConfirmationExpiredError):
        confirmation.consume(
            ConfigurationActor.human(), body(first), current_revision=4
        )
    request = body(second, targetAiId="agent-b")
    assert confirmation.consume(
        ConfigurationActor.human(), request, current_revision=4
    ).target_ai_id == "agent-b"


def test_challenge_projection_contains_no_before_or_after_payload():
    confirmation, _clock = service()
    challenge = issue(
        confirmation,
        before={"workspace": "/secret/before"},
        after={"workspace": "/secret/after"},
    )

    projected = challenge.to_dict()
    assert "before" not in projected
    assert "after" not in projected
    assert "/secret" not in str(projected)
    assert projected["changeDigest"] == challenge.change_digest
