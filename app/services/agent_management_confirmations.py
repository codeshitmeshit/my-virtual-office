"""Payload-bound confirmation challenges for high-risk Agent operations."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from services.agent_profile_configuration import ConfigurationActor


HIGH_RISK_ACTIONS = frozenset(
    {
        "provider",
        "branch",
        "workspace",
        "assignment",
        "binding",
        "create",
        "delete",
    }
)
DEFAULT_CONFIRMATION_TTL_SECONDS = 60
MAX_CONFIRMATIONS = 512
MAX_CONFIRMATIONS_PER_ACTOR = 20
MAX_CHANGE_BYTES = 32_768


class AgentManagementConfirmationError(RuntimeError):
    code = "agent_management_confirmation_failed"


class ConfirmationValidationError(AgentManagementConfirmationError, ValueError):
    code = "agent_management_confirmation_invalid"


class ConfirmationDeniedError(AgentManagementConfirmationError, PermissionError):
    code = "agent_management_confirmation_denied"


class ConfirmationConflictError(AgentManagementConfirmationError):
    code = "agent_management_confirmation_conflict"


class ConfirmationExpiredError(AgentManagementConfirmationError):
    code = "agent_management_confirmation_expired"


@dataclass(frozen=True, slots=True)
class ConfirmationChallenge:
    token: str
    target_ai_id: str
    action: str
    revision: int
    change_digest: str
    expires_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "challengeToken": self.token,
            "targetAiId": self.target_ai_id,
            "action": self.action,
            "revision": self.revision,
            "changeDigest": self.change_digest,
            "expiresAt": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ConfirmedHighRiskChange:
    target_ai_id: str
    action: str
    revision: int
    change_digest: str


@dataclass(slots=True)
class _StoredChallenge:
    token_digest: str
    actor_key: str
    target_ai_id: str
    action: str
    revision: int
    change_digest: str
    expires_at: datetime


class AgentManagementConfirmationService:
    """Issue and consume short-lived, payload-bound confirmation challenges."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        ttl_seconds: int = DEFAULT_CONFIRMATION_TTL_SECONDS,
        max_challenges: int = MAX_CONFIRMATIONS,
        max_per_actor: int = MAX_CONFIRMATIONS_PER_ACTOR,
    ):
        if not 5 <= int(ttl_seconds) <= 300:
            raise ValueError("ttl_seconds is out of bounds")
        if not 1 <= int(max_challenges) <= 10_000:
            raise ValueError("max_challenges is out of bounds")
        if not 1 <= int(max_per_actor) <= int(max_challenges):
            raise ValueError("max_per_actor is out of bounds")
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._ttl = timedelta(seconds=int(ttl_seconds))
        self._max = int(max_challenges)
        self._max_per_actor = int(max_per_actor)
        self._records: OrderedDict[str, _StoredChallenge] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _actor_key(actor: ConfigurationActor) -> str:
        if not isinstance(actor, ConfigurationActor):
            raise ConfirmationDeniedError("confirmation actor is invalid")
        return f"{actor.kind.value}:{actor.ai_id or '-'}"

    def _time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise RuntimeError("confirmation clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _target(value: object) -> str:
        target = str(value or "").strip()
        if (
            not target
            or len(target) > 256
            or "/" in target
            or "\\" in target
            or any(ord(character) < 32 for character in target)
        ):
            raise ConfirmationValidationError("target Agent ID is invalid")
        return target

    @staticmethod
    def _action(value: object) -> str:
        action = str(value or "").strip()
        if action not in HIGH_RISK_ACTIONS:
            raise ConfirmationValidationError("high-risk action is invalid")
        return action

    @staticmethod
    def _revision(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfirmationValidationError("revision is invalid")
        return value

    @staticmethod
    def _canonical_change(before: object, after: object) -> bytes:
        try:
            encoded = json.dumps(
                {"before": before, "after": after},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ConfirmationValidationError(
                "confirmation change must contain JSON values"
            ) from exc
        if len(encoded) > MAX_CHANGE_BYTES:
            raise ConfirmationValidationError("confirmation change is too large")
        return encoded

    @classmethod
    def change_digest(cls, before: object, after: object) -> str:
        return hashlib.sha256(cls._canonical_change(before, after)).hexdigest()

    def _prune(self, now: datetime) -> None:
        for digest, record in tuple(self._records.items()):
            if record.expires_at <= now:
                self._records.pop(digest, None)
        while len(self._records) >= self._max:
            self._records.popitem(last=False)

    def issue(
        self,
        actor: ConfigurationActor,
        *,
        target_ai_id: object,
        action: object,
        before: object,
        after: object,
        revision: object,
    ) -> ConfirmationChallenge:
        actor_key = self._actor_key(actor)
        target = self._target(target_ai_id)
        normalized_action = self._action(action)
        normalized_revision = self._revision(revision)
        change_digest = self.change_digest(before, after)
        token = str(self._token_factory() or "")
        if not 32 <= len(token) <= 512:
            raise RuntimeError("confirmation token factory returned an invalid token")
        token_digest = self._token_digest(token)
        now = self._time()
        expires_at = now + self._ttl
        with self._lock:
            self._prune(now)
            actor_records = [
                digest
                for digest, record in self._records.items()
                if record.actor_key == actor_key
            ]
            while len(actor_records) >= self._max_per_actor:
                self._records.pop(actor_records.pop(0), None)
            if token_digest in self._records:
                raise RuntimeError("confirmation token collision")
            self._records[token_digest] = _StoredChallenge(
                token_digest=token_digest,
                actor_key=actor_key,
                target_ai_id=target,
                action=normalized_action,
                revision=normalized_revision,
                change_digest=change_digest,
                expires_at=expires_at,
            )
        return ConfirmationChallenge(
            token=token,
            target_ai_id=target,
            action=normalized_action,
            revision=normalized_revision,
            change_digest=change_digest,
            expires_at=expires_at,
        )

    def consume(
        self,
        actor: ConfigurationActor,
        body: object,
        *,
        current_revision: object,
    ) -> ConfirmedHighRiskChange:
        if not isinstance(body, Mapping):
            raise ConfirmationValidationError("confirmation body must be an object")
        required = {
            "challengeToken",
            "targetAiId",
            "action",
            "before",
            "after",
            "revision",
        }
        if set(body) != required:
            raise ConfirmationValidationError(
                "confirmation requires the server challenge and exact change"
            )
        token = body.get("challengeToken")
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise ConfirmationValidationError("challenge token is invalid")
        actor_key = self._actor_key(actor)
        target = self._target(body.get("targetAiId"))
        action = self._action(body.get("action"))
        revision = self._revision(body.get("revision"))
        actual_revision = self._revision(current_revision)
        change_digest = self.change_digest(body.get("before"), body.get("after"))
        token_digest = self._token_digest(token)
        now = self._time()
        with self._lock:
            record = self._records.get(token_digest)
            if record is None:
                raise ConfirmationExpiredError("confirmation is unavailable")
            if record.expires_at <= now:
                self._records.pop(token_digest, None)
                raise ConfirmationExpiredError("confirmation expired")
            if record.actor_key != actor_key:
                raise ConfirmationDeniedError("confirmation actor changed")
            expected = (
                record.target_ai_id,
                record.action,
                record.revision,
                record.change_digest,
            )
            received = (target, action, revision, change_digest)
            if received != expected or actual_revision != record.revision:
                self._records.pop(token_digest, None)
                raise ConfirmationConflictError(
                    "confirmed change or revision no longer matches"
                )
            self._records.pop(token_digest, None)
        return ConfirmedHighRiskChange(
            target_ai_id=target,
            action=action,
            revision=revision,
            change_digest=change_digest,
        )
