"""个人资产 HTTP 路由解析；业务规则留在 transport-free services。"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping

from .personal_asset_agent_api import PersonalAssetAgentAPI
from .personal_asset_agent_auth import (
    PersonalAssetAgentAuthenticationError,
    PersonalAssetAgentAuthenticator,
    PersonalAssetAgentAuthRequest,
)
from .personal_asset_service import PersonalAssetService
from .personal_asset_feishu_onboarding import (
    PersonalAssetFeishuOnboarding,
    PersonalAssetFeishuOnboardingError,
)
from .personal_asset_oss_availability_http import PersonalAssetOssAvailabilityHTTP
from .personal_asset_sync_http import PersonalAssetSyncHTTP
from .personal_asset_store import (
    PersonalAssetConflictError,
    PersonalAssetStoreError,
    PersonalAssetValidationError,
)


MANAGEMENT_PREFIX = "/api/personal-assets"
AGENT_PREFIX = "/api/agent/personal-assets"


@dataclass(frozen=True, slots=True)
class PersonalAssetHTTPResponse:
    status: int
    payload: dict[str, Any]


class PersonalAssetHTTPRoutes:
    def __init__(
        self,
        service: PersonalAssetService,
        agent_api: PersonalAssetAgentAPI,
        authenticator: PersonalAssetAgentAuthenticator,
        sync_http: PersonalAssetSyncHTTP | None = None,
        availability_http: PersonalAssetOssAvailabilityHTTP | None = None,
        feishu_onboarding: PersonalAssetFeishuOnboarding | None = None,
    ):
        self._service = service
        self._agent_api = agent_api
        self._authenticator = authenticator
        self._sync_http = sync_http
        self._availability_http = availability_http
        self._feishu_onboarding = feishu_onboarding

    @staticmethod
    def handles(path: str) -> bool:
        return path == MANAGEMENT_PREFIX or path.startswith(f"{MANAGEMENT_PREFIX}/") or path == AGENT_PREFIX or path.startswith(f"{AGENT_PREFIX}/")

    @staticmethod
    def is_management(path: str) -> bool:
        return path == MANAGEMENT_PREFIX or path.startswith(f"{MANAGEMENT_PREFIX}/")

    @staticmethod
    def _ok(payload: Mapping[str, Any], status: int = 200) -> PersonalAssetHTTPResponse:
        return PersonalAssetHTTPResponse(status, {"ok": True, **dict(payload)})

    def _management_ok(
        self, payload: Mapping[str, Any], status: int = 200
    ) -> PersonalAssetHTTPResponse:
        result = dict(payload)
        if self._sync_http is not None:
            result["sync"] = self._sync_http.status()
        return self._ok(result, status)

    @staticmethod
    def _error(exc: Exception) -> PersonalAssetHTTPResponse:
        if isinstance(exc, PersonalAssetAgentAuthenticationError):
            return PersonalAssetHTTPResponse(403, {"ok": False, "code": exc.code})
        if isinstance(exc, PersonalAssetConflictError):
            return PersonalAssetHTTPResponse(409, {"ok": False, "code": exc.code})
        if isinstance(exc, PersonalAssetValidationError):
            return PersonalAssetHTTPResponse(400, {"ok": False, "code": exc.code})
        if isinstance(exc, PersonalAssetStoreError):
            return PersonalAssetHTTPResponse(503, {"ok": False, "code": exc.code})
        if isinstance(exc, PersonalAssetFeishuOnboardingError):
            return PersonalAssetHTTPResponse(exc.status, {"ok": False, "code": exc.code})
        return PersonalAssetHTTPResponse(500, {"ok": False, "code": "personal_asset_internal_error"})

    @staticmethod
    def _not_found() -> PersonalAssetHTTPResponse:
        return PersonalAssetHTTPResponse(404, {"ok": False, "code": "personal_asset_route_not_found"})

    def management_get(self, path: str) -> PersonalAssetHTTPResponse:
        if self._availability_http is not None and self._availability_http.handles_get(path):
            response = self._availability_http.get(path)
            return PersonalAssetHTTPResponse(response.status, response.payload)
        if path != MANAGEMENT_PREFIX:
            return self._not_found()
        try:
            return self._management_ok({"profile": self._service.snapshot()})
        except Exception as exc:
            return self._error(exc)

    def management_post(self, path: str, body: Mapping[str, object]) -> PersonalAssetHTTPResponse:
        payload = body if isinstance(body, Mapping) else {}
        try:
            if self._sync_http is not None and self._sync_http.handles(path):
                response = self._sync_http.post(path, payload)
                return PersonalAssetHTTPResponse(response.status, response.payload)
            if path == f"{MANAGEMENT_PREFIX}/entries":
                entry = payload.get("entry")
                if not isinstance(entry, Mapping):
                    raise PersonalAssetValidationError("entry is required")
                return self._management_ok(
                    self._service.create_entry(entry, expected_revision=payload.get("expectedRevision")),
                    201,
                )
            entry_prefix = f"{MANAGEMENT_PREFIX}/entries/"
            if path.startswith(entry_prefix):
                entry_id = urllib.parse.unquote(path[len(entry_prefix) :]).strip("/")
                if not entry_id or "/" in entry_id:
                    return self._not_found()
                operation = str(payload.get("operation") or "").strip().lower()
                if operation == "update":
                    patch = payload.get("patch")
                    if not isinstance(patch, Mapping):
                        raise PersonalAssetValidationError("patch is required")
                    return self._management_ok(
                        self._service.update_entry(
                            entry_id, patch, expected_revision=payload.get("expectedRevision")
                        )
                    )
                if operation == "delete":
                    return self._management_ok(
                        self._service.delete_entry(
                            entry_id, expected_revision=payload.get("expectedRevision")
                        )
                    )
                raise PersonalAssetValidationError("operation must be update or delete")
            suggestion_prefix = f"{MANAGEMENT_PREFIX}/suggestions/"
            if path.startswith(suggestion_prefix):
                rest = path[len(suggestion_prefix) :].strip("/")
                suggestion_id, separator, operation = rest.rpartition("/")
                suggestion_id = urllib.parse.unquote(suggestion_id)
                if not separator or not suggestion_id or "/" in suggestion_id:
                    return self._not_found()
                if operation == "accept":
                    edited = payload.get("editedProposal")
                    if edited is not None and not isinstance(edited, Mapping):
                        raise PersonalAssetValidationError("editedProposal must be an object")
                    return self._management_ok(
                        self._service.accept_suggestion(
                            suggestion_id,
                            expected_revision=payload.get("expectedRevision"),
                            edited_proposal=edited,
                        )
                    )
                if operation == "reject":
                    return self._management_ok(
                        self._service.reject_suggestion(
                            suggestion_id, expected_revision=payload.get("expectedRevision")
                        )
                    )
            return self._not_found()
        except Exception as exc:
            return self._error(exc)

    def agent_post(
        self,
        path: str,
        body: Mapping[str, object],
        auth_request: PersonalAssetAgentAuthRequest,
    ) -> PersonalAssetHTTPResponse:
        try:
            identity = self._authenticator.authenticate(auth_request)
            if path == f"{AGENT_PREFIX}/request-context":
                return self._ok(self._agent_api.request_context(identity, body))
            if path == f"{AGENT_PREFIX}/profile-outline":
                return self._ok(self._agent_api.profile_outline(identity, body))
            if path == f"{AGENT_PREFIX}/suggest-change":
                return self._ok(self._agent_api.suggest_change(identity, body), 201)
            if path == f"{AGENT_PREFIX}/apply-confirmed-onboarding":
                return self._ok(self._agent_api.apply_confirmed_onboarding(identity, body))
            if path == f"{AGENT_PREFIX}/feishu-onboarding-form":
                if self._feishu_onboarding is None:
                    raise PersonalAssetFeishuOnboardingError(
                        "personal_asset_feishu_unavailable",
                        "Feishu Personal Assets onboarding is unavailable",
                        503,
                    )
                return self._ok(self._feishu_onboarding.open_form(identity, body), 202)
            return self._not_found()
        except Exception as exc:
            return self._error(exc)
