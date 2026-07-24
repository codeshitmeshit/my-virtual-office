"""Short-lived, restart-invalidated Agent Management browser sessions."""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable


DEFAULT_LAUNCH_TTL_SECONDS = 60
DEFAULT_IDLE_TTL_SECONDS = 300
DEFAULT_ABSOLUTE_TTL_SECONDS = 900
DEFAULT_MAX_LAUNCH_CODES = 512
DEFAULT_MAX_LAUNCH_CODES_PER_AGENT = 5
DEFAULT_MAX_SESSIONS = 512
DEFAULT_MAX_SESSIONS_PER_AGENT = 3


class AgentManagementSessionError(RuntimeError):
    code = "agent_management_session_failed"


class AgentManagementSessionValidationError(
    AgentManagementSessionError, ValueError
):
    code = "agent_management_session_invalid"


class AgentManagementSessionCapacityError(AgentManagementSessionError):
    code = "agent_management_session_capacity"


class AgentManagementLaunchCodeUnavailableError(AgentManagementSessionError):
    code = "agent_management_launch_code_unavailable"


class AgentManagementLaunchCodeExpiredError(AgentManagementSessionError):
    code = "agent_management_launch_code_expired"


class AgentManagementBrowserSessionExpiredError(AgentManagementSessionError):
    code = "agent_management_browser_session_expired"


@dataclass(frozen=True, slots=True)
class AgentManagementLaunch:
    code: str
    ai_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AgentManagementBrowserSession:
    token: str
    ai_id: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(slots=True)
class _LaunchRecord:
    digest: str
    ai_id: str
    expires_at: datetime
    used: bool = False


@dataclass(slots=True)
class _SessionRecord:
    digest: str
    ai_id: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class AgentManagementSessionService:
    """Own bounded in-memory launch-code and browser-session repositories."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        secret_factory: Callable[[], str] | None = None,
        launch_ttl_seconds: int = DEFAULT_LAUNCH_TTL_SECONDS,
        idle_ttl_seconds: int = DEFAULT_IDLE_TTL_SECONDS,
        absolute_ttl_seconds: int = DEFAULT_ABSOLUTE_TTL_SECONDS,
        max_launch_codes: int = DEFAULT_MAX_LAUNCH_CODES,
        max_launch_codes_per_agent: int = DEFAULT_MAX_LAUNCH_CODES_PER_AGENT,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_sessions_per_agent: int = DEFAULT_MAX_SESSIONS_PER_AGENT,
    ):
        if not 5 <= int(launch_ttl_seconds) <= 300:
            raise ValueError("launch_ttl_seconds is out of bounds")
        if not 30 <= int(idle_ttl_seconds) <= 86_400:
            raise ValueError("idle_ttl_seconds is out of bounds")
        if not int(idle_ttl_seconds) <= int(absolute_ttl_seconds) <= 604_800:
            raise ValueError("absolute_ttl_seconds is out of bounds")
        self._validate_caps(
            max_launch_codes,
            max_launch_codes_per_agent,
            label="launch code",
        )
        self._validate_caps(
            max_sessions,
            max_sessions_per_agent,
            label="session",
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._secret_factory = secret_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._launch_ttl = timedelta(seconds=int(launch_ttl_seconds))
        self._idle_ttl = timedelta(seconds=int(idle_ttl_seconds))
        self._absolute_ttl = timedelta(seconds=int(absolute_ttl_seconds))
        self._max_launch_codes = int(max_launch_codes)
        self._max_launch_codes_per_agent = int(max_launch_codes_per_agent)
        self._max_sessions = int(max_sessions)
        self._max_sessions_per_agent = int(max_sessions_per_agent)
        self._launch_codes: OrderedDict[str, _LaunchRecord] = OrderedDict()
        self._sessions: OrderedDict[str, _SessionRecord] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _validate_caps(global_cap: int, per_agent: int, *, label: str) -> None:
        if not 1 <= int(global_cap) <= 100_000:
            raise ValueError(f"{label} global cap is out of bounds")
        if not 1 <= int(per_agent) <= int(global_cap):
            raise ValueError(f"{label} per-Agent cap is out of bounds")

    @staticmethod
    def _ai_id(value: object) -> str:
        ai_id = str(value or "").strip()
        if (
            not ai_id
            or len(ai_id) > 256
            or "/" in ai_id
            or "\\" in ai_id
            or any(ord(character) < 32 for character in ai_id)
        ):
            raise AgentManagementSessionValidationError("Agent ID is invalid")
        return ai_id

    def _time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise RuntimeError("session clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _digest(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def _secret(self) -> tuple[str, str]:
        secret = str(self._secret_factory() or "")
        if not 32 <= len(secret) <= 512:
            raise RuntimeError("session secret factory returned an invalid value")
        return secret, self._digest(secret)

    @staticmethod
    def _active_for_agent(records, ai_id: str) -> int:
        return sum(1 for record in records.values() if record.ai_id == ai_id)

    def _cleanup_locked(self, now: datetime) -> tuple[int, int]:
        removed_launches = 0
        removed_sessions = 0
        for digest, record in tuple(self._launch_codes.items()):
            if record.expires_at <= now:
                self._launch_codes.pop(digest, None)
                removed_launches += 1
        for digest, record in tuple(self._sessions.items()):
            if (
                record.idle_expires_at <= now
                or record.absolute_expires_at <= now
            ):
                self._sessions.pop(digest, None)
                removed_sessions += 1
        return removed_launches, removed_sessions

    def cleanup(self) -> dict[str, int]:
        with self._lock:
            launches, sessions = self._cleanup_locked(self._time())
            return {
                "launchCodesRemoved": launches,
                "sessionsRemoved": sessions,
            }

    def issue_launch_code(self, ai_id: object) -> AgentManagementLaunch:
        normalized_ai_id = self._ai_id(ai_id)
        now = self._time()
        with self._lock:
            self._cleanup_locked(now)
            if len(self._launch_codes) >= self._max_launch_codes:
                raise AgentManagementSessionCapacityError(
                    "launch-code capacity reached"
                )
            if (
                self._active_for_agent(self._launch_codes, normalized_ai_id)
                >= self._max_launch_codes_per_agent
            ):
                raise AgentManagementSessionCapacityError(
                    "Agent launch-code capacity reached"
                )
            code, digest = self._secret()
            if digest in self._launch_codes or digest in self._sessions:
                raise RuntimeError("session secret collision")
            expires_at = now + self._launch_ttl
            self._launch_codes[digest] = _LaunchRecord(
                digest=digest,
                ai_id=normalized_ai_id,
                expires_at=expires_at,
            )
        return AgentManagementLaunch(
            code=code,
            ai_id=normalized_ai_id,
            expires_at=expires_at,
        )

    def exchange_launch_code(
        self, code: object
    ) -> AgentManagementBrowserSession:
        if not isinstance(code, str) or not 32 <= len(code) <= 512:
            raise AgentManagementLaunchCodeUnavailableError(
                "launch code is unavailable"
            )
        digest = self._digest(code)
        now = self._time()
        with self._lock:
            record = self._launch_codes.get(digest)
            if record is None or record.used:
                raise AgentManagementLaunchCodeUnavailableError(
                    "launch code is unavailable"
                )
            if record.expires_at <= now:
                self._launch_codes.pop(digest, None)
                raise AgentManagementLaunchCodeExpiredError(
                    "launch code expired"
                )
            self._cleanup_locked(now)
            if len(self._sessions) >= self._max_sessions:
                raise AgentManagementSessionCapacityError(
                    "browser-session capacity reached"
                )
            if (
                self._active_for_agent(self._sessions, record.ai_id)
                >= self._max_sessions_per_agent
            ):
                raise AgentManagementSessionCapacityError(
                    "Agent browser-session capacity reached"
                )
            token, token_digest = self._secret()
            if (
                token_digest in self._launch_codes
                or token_digest in self._sessions
            ):
                raise RuntimeError("session secret collision")
            record.used = True
            absolute_expires_at = now + self._absolute_ttl
            idle_expires_at = min(now + self._idle_ttl, absolute_expires_at)
            self._sessions[token_digest] = _SessionRecord(
                digest=token_digest,
                ai_id=record.ai_id,
                idle_expires_at=idle_expires_at,
                absolute_expires_at=absolute_expires_at,
            )
        return AgentManagementBrowserSession(
            token=token,
            ai_id=record.ai_id,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )

    def resolve(self, token: object) -> AgentManagementBrowserSession:
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise AgentManagementBrowserSessionExpiredError(
                "browser session is unavailable"
            )
        digest = self._digest(token)
        now = self._time()
        with self._lock:
            record = self._sessions.get(digest)
            if record is None:
                raise AgentManagementBrowserSessionExpiredError(
                    "browser session is unavailable"
                )
            if (
                record.idle_expires_at <= now
                or record.absolute_expires_at <= now
            ):
                self._sessions.pop(digest, None)
                raise AgentManagementBrowserSessionExpiredError(
                    "browser session expired"
                )
            record.idle_expires_at = min(
                now + self._idle_ttl,
                record.absolute_expires_at,
            )
            self._sessions.move_to_end(digest)
            return AgentManagementBrowserSession(
                token=token,
                ai_id=record.ai_id,
                idle_expires_at=record.idle_expires_at,
                absolute_expires_at=record.absolute_expires_at,
            )

    def invalidate(self, token: object) -> bool:
        if not isinstance(token, str) or not token:
            return False
        digest = self._digest(token)
        with self._lock:
            return self._sessions.pop(digest, None) is not None

    def diagnostics(self) -> dict[str, int]:
        with self._lock:
            self._cleanup_locked(self._time())
            return {
                "launchCodes": len(self._launch_codes),
                "activeSessions": len(self._sessions),
            }
