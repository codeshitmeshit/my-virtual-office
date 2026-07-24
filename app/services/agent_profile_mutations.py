"""Application API for profile auto-save and revision-checked undo."""

from __future__ import annotations

import copy
import hashlib
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from services.agent_profile_configuration import (
    AgentProfileAuthorizationError,
    AgentProfileCommandError,
    AgentProfileConfigurationService,
    ConfigurationActor,
    ProfileMutationCommand,
)
from services.agent_profile_store import (
    AgentProfileConflictError,
    AgentProfileStore,
    AgentProfileStoreError,
    AgentProfileValidationError,
)


UNDO_TTL_SECONDS = 30
MAX_UNDO_TOKENS = 512
MAX_UNDO_TOKENS_PER_ACTOR = 20


@dataclass(frozen=True, slots=True)
class AgentProfileAPIResult:
    status: int
    payload: dict[str, object]


@dataclass(slots=True)
class _UndoRecord:
    digest: str
    actor_key: str
    target_ai_id: str
    field: str
    previous_value: object
    appearance_was_present: bool
    written_revision: int
    expires_at: datetime


class AgentProfileMutationAPI:
    """Map bounded request objects onto the profile configuration service."""

    def __init__(
        self,
        configuration: AgentProfileConfigurationService,
        store: AgentProfileStore,
        *,
        now: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        undo_ttl_seconds: int = UNDO_TTL_SECONDS,
        max_tokens: int = MAX_UNDO_TOKENS,
        max_tokens_per_actor: int = MAX_UNDO_TOKENS_PER_ACTOR,
    ):
        if not isinstance(configuration, AgentProfileConfigurationService):
            raise TypeError(
                "configuration must be an AgentProfileConfigurationService"
            )
        if not isinstance(store, AgentProfileStore):
            raise TypeError("store must be an AgentProfileStore")
        if not 1 <= int(undo_ttl_seconds) <= 300:
            raise ValueError("undo_ttl_seconds is out of bounds")
        if not 1 <= int(max_tokens) <= 10_000:
            raise ValueError("max_tokens is out of bounds")
        if not 1 <= int(max_tokens_per_actor) <= int(max_tokens):
            raise ValueError("max_tokens_per_actor is out of bounds")
        self._configuration = configuration
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._undo_ttl = timedelta(seconds=int(undo_ttl_seconds))
        self._max_tokens = int(max_tokens)
        self._max_tokens_per_actor = int(max_tokens_per_actor)
        self._undo: OrderedDict[str, _UndoRecord] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _actor_key(actor: ConfigurationActor) -> str:
        return f"{actor.kind.value}:{actor.ai_id or '-'}"

    def _time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise RuntimeError("profile mutation clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _request(
        body: object,
        *,
        required: frozenset[str],
        optional: frozenset[str] = frozenset(),
    ) -> Mapping[str, object]:
        if not isinstance(body, Mapping):
            raise AgentProfileCommandError("request body must be an object")
        keys = set(body)
        if keys - required - optional or required - keys:
            raise AgentProfileCommandError("request body fields are invalid")
        return body

    @staticmethod
    def _previous(profile, field: str) -> tuple[object, bool]:
        if field.startswith("appearance."):
            key = field.removeprefix("appearance.")
            present = profile is not None and key in profile.appearance
            return (
                copy.deepcopy(profile.appearance.get(key)) if present else None,
                present,
            )
        if profile is None:
            return ([] if field in {"responsibilities", "specialties"} else ""), True
        return copy.deepcopy(getattr(profile, field)), True

    def _prune(self, now: datetime) -> None:
        for digest, record in tuple(self._undo.items()):
            if record.expires_at <= now:
                self._undo.pop(digest, None)
        while len(self._undo) >= self._max_tokens:
            self._undo.popitem(last=False)

    def _remember(
        self,
        *,
        actor: ConfigurationActor,
        target_ai_id: str,
        field: str,
        previous_value: object,
        appearance_was_present: bool,
        written_revision: int,
        now: datetime,
    ) -> tuple[str, datetime]:
        token = str(self._token_factory() or "")
        if len(token) < 32 or len(token) > 512:
            raise RuntimeError("undo token factory returned an invalid token")
        digest = self._digest(token)
        actor_key = self._actor_key(actor)
        with self._lock:
            self._prune(now)
            actor_digests = [
                key
                for key, record in self._undo.items()
                if record.actor_key == actor_key
            ]
            while len(actor_digests) >= self._max_tokens_per_actor:
                self._undo.pop(actor_digests.pop(0), None)
            expires_at = now + self._undo_ttl
            self._undo[digest] = _UndoRecord(
                digest=digest,
                actor_key=actor_key,
                target_ai_id=target_ai_id,
                field=field,
                previous_value=copy.deepcopy(previous_value),
                appearance_was_present=appearance_was_present,
                written_revision=written_revision,
                expires_at=expires_at,
            )
        return token, expires_at

    @staticmethod
    def _error(exc: Exception) -> AgentProfileAPIResult:
        if isinstance(exc, AgentProfileAuthorizationError):
            return AgentProfileAPIResult(403, {"ok": False, "code": exc.code})
        if isinstance(exc, AgentProfileConflictError):
            return AgentProfileAPIResult(409, {"ok": False, "code": exc.code})
        if isinstance(
            exc, (AgentProfileCommandError, AgentProfileValidationError, ValueError)
        ):
            return AgentProfileAPIResult(
                400,
                {
                    "ok": False,
                    "code": str(
                        getattr(exc, "code", "agent_profile_request_invalid")
                    ),
                },
            )
        return AgentProfileAPIResult(
            500, {"ok": False, "code": "agent_profile_mutation_failed"}
        )

    def mutate(
        self, actor: ConfigurationActor, body: object
    ) -> AgentProfileAPIResult:
        try:
            request = self._request(
                body,
                required=frozenset(
                    {"targetAiId", "field", "value", "expectedRevision"}
                ),
            )
            target = str(request["targetAiId"] or "").strip()
            field = str(request["field"] or "").strip()
            expected = request["expectedRevision"]
            before = self._store.get(target)
            previous, appearance_was_present = self._previous(before, field)
            outcome = self._configuration.mutate(
                actor,
                ProfileMutationCommand(
                    target_ai_id=target,
                    field=field,
                    value=copy.deepcopy(request["value"]),
                    expected_revision=expected,
                ),
            )
            now = self._time()
            token, expires_at = self._remember(
                actor=actor,
                target_ai_id=target,
                field=field,
                previous_value=previous,
                appearance_was_present=appearance_was_present,
                written_revision=outcome.profile.revision,
                now=now,
            )
            payload: dict[str, object] = {
                "ok": True,
                "saveState": "saved",
                "field": field,
                "profile": outcome.profile.to_dict(),
                "revision": outcome.profile.revision,
                "undoToken": token,
                "undoExpiresAt": expires_at.isoformat(),
            }
            if outcome.reconciliation_pending:
                payload["warningCode"] = outcome.warning_code
                payload["reconciliationPending"] = True
            return AgentProfileAPIResult(200, payload)
        except Exception as exc:
            return self._error(exc)

    def undo(self, actor: ConfigurationActor, body: object) -> AgentProfileAPIResult:
        try:
            request = self._request(
                body, required=frozenset({"undoToken", "expectedRevision"})
            )
            token = request["undoToken"]
            expected = request["expectedRevision"]
            if not isinstance(token, str) or not 32 <= len(token) <= 512:
                raise AgentProfileCommandError("undo token is invalid")
            if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
                raise AgentProfileCommandError("expectedRevision is invalid")
            digest = self._digest(token)
            now = self._time()
            with self._lock:
                self._prune(now)
                record = self._undo.get(digest)
                if record is None:
                    return AgentProfileAPIResult(
                        410, {"ok": False, "code": "agent_profile_undo_unavailable"}
                    )
                if record.actor_key != self._actor_key(actor):
                    return AgentProfileAPIResult(
                        403, {"ok": False, "code": "agent_profile_undo_denied"}
                    )
                if expected != record.written_revision:
                    self._undo.pop(digest, None)
                    return AgentProfileAPIResult(
                        409, {"ok": False, "code": "agent_profile_undo_conflict"}
                    )
                current = self._store.get(record.target_ai_id)
                if current is None or current.revision != record.written_revision:
                    self._undo.pop(digest, None)
                    return AgentProfileAPIResult(
                        409, {"ok": False, "code": "agent_profile_undo_conflict"}
                    )
                try:
                    outcome = self._configuration.restore(
                        actor,
                        target_ai_id=record.target_ai_id,
                        field=record.field,
                        value=copy.deepcopy(record.previous_value),
                        expected_revision=record.written_revision,
                        appearance_was_present=record.appearance_was_present,
                    )
                except AgentProfileConflictError:
                    self._undo.pop(digest, None)
                    return AgentProfileAPIResult(
                        409, {"ok": False, "code": "agent_profile_undo_conflict"}
                    )
                self._undo.pop(digest, None)
            payload: dict[str, object] = {
                "ok": True,
                "saveState": "undone",
                "field": record.field,
                "profile": outcome.profile.to_dict(),
                "revision": outcome.profile.revision,
            }
            if outcome.reconciliation_pending:
                payload["warningCode"] = outcome.warning_code
                payload["reconciliationPending"] = True
            return AgentProfileAPIResult(200, payload)
        except Exception as exc:
            return self._error(exc)
