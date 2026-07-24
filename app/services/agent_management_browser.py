"""Audience-safe browser routes backed by an Agent Management session."""

from __future__ import annotations

import http.cookies
import urllib.parse
from dataclasses import dataclass
from typing import Mapping, Sequence

from services.agent_management_session_exchange import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_PATH,
)
from services.agent_management_sessions import (
    AgentManagementBrowserSessionExpiredError,
    AgentManagementSessionService,
)
from services.agent_profile_configuration import ConfigurationActor
from services.agent_profile_mutations import AgentProfileMutationAPI
from services.agent_profile_store import AgentProfileStore, AgentProfileStoreError
from services.hr_agent_api import HRAgentAPI
from services.hr_agent_auth import AuthenticatedHRAgent
from services.hr_directory import HRDirectoryQuery
from services.hr_repository import HRRepository, HRRepositoryError


BROWSER_PREFIX = "/api/agent-management/browser"
BOOTSTRAP_PATH = f"{BROWSER_PREFIX}/bootstrap"
AGENT_PREFIX = f"{BROWSER_PREFIX}/agents/"
ACCESS_LOG_PATH = f"{BROWSER_PREFIX}/access-log/self"
PROFILE_MUTATION_PATH = f"{BROWSER_PREFIX}/profile/mutate"
PROFILE_UNDO_PATH = f"{BROWSER_PREFIX}/profile/undo"
LOGOUT_PATH = f"{BROWSER_PREFIX}/logout"
POST_PATHS = frozenset(
    {PROFILE_MUTATION_PATH, PROFILE_UNDO_PATH, LOGOUT_PATH}
)


@dataclass(frozen=True, slots=True)
class AgentManagementBrowserResponse:
    status: int
    payload: dict[str, object]
    headers: Mapping[str, str] | None = None


class AgentManagementBrowserRoutes:
    """Resolve session identity and expose only Agent-safe projections."""

    def __init__(
        self,
        *,
        repository: HRRepository,
        sessions: AgentManagementSessionService,
        profiles: AgentProfileStore,
        mutations: AgentProfileMutationAPI,
    ):
        if not isinstance(repository, HRRepository):
            raise TypeError("repository must be an HRRepository")
        if not isinstance(sessions, AgentManagementSessionService):
            raise TypeError("sessions must be an AgentManagementSessionService")
        if not isinstance(profiles, AgentProfileStore):
            raise TypeError("profiles must be an AgentProfileStore")
        if not isinstance(mutations, AgentProfileMutationAPI):
            raise TypeError("mutations must be an AgentProfileMutationAPI")
        self._repository = repository
        self._sessions = sessions
        self._profiles = profiles
        self._mutations = mutations
        self._hr = HRAgentAPI(repository, HRDirectoryQuery(repository))

    @staticmethod
    def handles(method: str, path: str) -> bool:
        normalized_method = str(method or "").upper()
        normalized_path = str(path or "").split("?", 1)[0]
        if normalized_method == "GET":
            return normalized_path in {BOOTSTRAP_PATH, ACCESS_LOG_PATH} or (
                normalized_path.startswith(AGENT_PREFIX)
            )
        if normalized_method == "POST":
            return normalized_path in POST_PATHS
        return False

    @staticmethod
    def session_token(cookie_header: object) -> str | None:
        if (
            not isinstance(cookie_header, str)
            or not cookie_header
            or len(cookie_header) > 8_192
        ):
            return None
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(cookie_header)
        except http.cookies.CookieError:
            return None
        morsel = cookies.get(SESSION_COOKIE_NAME)
        if morsel is None:
            return None
        value = str(morsel.value or "")
        return value if 32 <= len(value) <= 512 else None

    @staticmethod
    def _error(status: int, code: str) -> AgentManagementBrowserResponse:
        return AgentManagementBrowserResponse(
            status, {"ok": False, "code": code}
        )

    def _identity(
        self, session_token: object
    ) -> tuple[AuthenticatedHRAgent | None, AgentManagementBrowserResponse | None]:
        try:
            session = self._sessions.resolve(session_token)
        except AgentManagementBrowserSessionExpiredError:
            return None, self._error(
                401, "agent_management_browser_session_expired"
            )
        try:
            agent = self._repository.get_agent(session.ai_id)
        except HRRepositoryError:
            return None, self._error(
                503, "agent_management_directory_unavailable"
            )
        if agent is None:
            self._sessions.invalidate(session.token)
            return None, self._error(
                403, "agent_management_agent_unknown"
            )
        if agent.status != "active":
            self._sessions.invalidate(session.token)
            return None, self._error(
                403, "agent_management_agent_inactive"
            )
        return (
            AuthenticatedHRAgent(
                ai_id=agent.ai_id,
                name=agent.name,
                provider_kind=agent.provider_kind,
            ),
            None,
        )

    @staticmethod
    def _value(
        query: Mapping[str, Sequence[str]],
        name: str,
        *,
        default: str | None = None,
    ) -> str | None:
        values = query.get(name)
        if values is None:
            return default
        if isinstance(values, (str, bytes)) or len(values) != 1:
            raise ValueError(f"query parameter {name} is invalid")
        value = values[0]
        if not isinstance(value, str):
            raise ValueError(f"query parameter {name} is invalid")
        return value

    @classmethod
    def _limit(
        cls,
        query: Mapping[str, Sequence[str]],
        *,
        default: int = 50,
    ) -> int:
        value = cls._value(query, "limit")
        if value is None:
            return default
        result = int(value)
        if not 1 <= result <= 100:
            raise ValueError("limit is invalid")
        return result

    @staticmethod
    def _target(path: str) -> str | None:
        encoded = str(path or "")[len(AGENT_PREFIX) :].strip("/")
        if not encoded or "/" in encoded:
            return None
        target = urllib.parse.unquote(encoded).strip()
        if not target or "/" in target or "\\" in target or len(target) > 256:
            return None
        return target

    @staticmethod
    def _profile_payload(profile) -> dict[str, object] | None:
        return profile.to_dict() if profile is not None else None

    def get(
        self,
        path: str,
        query: Mapping[str, Sequence[str]],
        *,
        session_token: object,
        occurrence_key: str,
    ) -> AgentManagementBrowserResponse:
        identity, error = self._identity(session_token)
        if error is not None:
            return error
        assert identity is not None
        try:
            if path == BOOTSTRAP_PATH:
                result = self._hr.directory(
                    identity,
                    availability=self._value(query, "availability"),
                    readiness=self._value(query, "readiness"),
                    query=self._value(query, "query"),
                    limit=self._limit(query),
                    cursor=self._value(query, "cursor"),
                )
                return AgentManagementBrowserResponse(
                    result.status,
                    {
                        **result.payload,
                        "audience": {
                            "kind": "agent",
                            "aiId": identity.ai_id,
                        },
                    },
                )
            if path == ACCESS_LOG_PATH:
                result = self._hr.self_access_log(
                    identity,
                    limit=self._limit(query),
                    cursor=self._value(query, "cursor"),
                )
                return AgentManagementBrowserResponse(
                    result.status, result.payload
                )
            if path.startswith(AGENT_PREFIX):
                target = self._target(path)
                if target is None:
                    return self._error(
                        404, "agent_management_agent_not_found"
                    )
                profile = self._profiles.get(target)
                result = self._hr.agent_detail(
                    identity,
                    target,
                    occurrence_key=occurrence_key,
                )
                if result.status != 200:
                    return AgentManagementBrowserResponse(
                        result.status, result.payload
                    )
                return AgentManagementBrowserResponse(
                    200,
                    {
                        "ok": True,
                        "scope": (
                            "self" if target == identity.ai_id else "public"
                        ),
                        "profile": self._profile_payload(profile),
                        "hr": result.payload["agent"],
                    },
                )
            return self._error(404, "agent_management_route_not_found")
        except (ValueError, AgentProfileStoreError):
            return self._error(400, "agent_management_browser_request_invalid")
        except Exception as exc:
            result = self._hr.safe_error(exc)
            return AgentManagementBrowserResponse(result.status, result.payload)

    def post(
        self,
        path: str,
        body: object,
        *,
        session_token: object,
    ) -> AgentManagementBrowserResponse:
        identity, error = self._identity(session_token)
        if error is not None:
            return error
        assert identity is not None
        actor = ConfigurationActor.agent(identity.ai_id)
        if path == LOGOUT_PATH:
            self._sessions.invalidate(str(session_token or ""))
            return AgentManagementBrowserResponse(
                200,
                {"ok": True, "loggedOut": True},
                {
                    "Set-Cookie": (
                        f"{SESSION_COOKIE_NAME}=; Path={SESSION_COOKIE_PATH}; "
                        "Max-Age=0; HttpOnly; SameSite=Strict"
                    )
                },
            )
        if path == PROFILE_MUTATION_PATH:
            if (
                not isinstance(body, Mapping)
                or body.get("targetAiId") != identity.ai_id
            ):
                return self._error(
                    403, "agent_profile_mutation_denied"
                )
            result = self._mutations.mutate(actor, body)
            return AgentManagementBrowserResponse(
                result.status, result.payload
            )
        if path == PROFILE_UNDO_PATH:
            result = self._mutations.undo(actor, body)
            return AgentManagementBrowserResponse(
                result.status, result.payload
            )
        return self._error(404, "agent_management_route_not_found")


def build_agent_management_browser_routes(
    *,
    repository: HRRepository,
    sessions: AgentManagementSessionService,
    profiles: AgentProfileStore,
    mutations: AgentProfileMutationAPI,
) -> AgentManagementBrowserRoutes:
    return AgentManagementBrowserRoutes(
        repository=repository,
        sessions=sessions,
        profiles=profiles,
        mutations=mutations,
    )
