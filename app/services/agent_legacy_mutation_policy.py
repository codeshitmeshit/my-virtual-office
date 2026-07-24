"""Compatibility policy for legacy Agent mutation routes.

The merged management surface is the only owner of Agent profile and
high-risk lifecycle changes.  Legacy routes may retain unrelated workspace or
skill behavior, but they must be management-authorized and cannot mutate Agent
identity, assignment, provider, workspace, or lifecycle state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


MIGRATED_ROUTE_CODE = "agent_management_route_migrated"
MIGRATED_ROUTE_STATUS = 410

_POST_EXACT = frozenset(
    {
        "/api/office-config",
        "/api/agent/create",
        "/set-model",
        "/api/skills-library",
        "/api/skills-library/apply",
        "/api/skills-library/save-from-agent",
        "/api/skills-library/upload",
    }
)
_DELETE_EXACT = frozenset({"/api/agent/delete"})
_WORKSPACE_PROFILE_FIELDS = frozenset(
    {"name", "displayName", "role", "branch", "emoji", "color"}
)


@dataclass(frozen=True, slots=True)
class LegacyMutationDecision:
    allowed: bool
    status: int = 200
    code: str | None = None
    error: str | None = None

    def response(self) -> dict[str, object]:
        return {
            "ok": False,
            "code": self.code or MIGRATED_ROUTE_CODE,
            "error": self.error or "Use the merged Agent management API",
        }


ALLOW = LegacyMutationDecision(allowed=True)


def requires_management(method: str, path: str) -> bool:
    """Return whether a retained or retired legacy write route is privileged."""

    normalized_method = str(method or "").upper()
    normalized_path = str(path or "").split("?", 1)[0]
    if normalized_method == "POST":
        return (
            normalized_path in _POST_EXACT
            or normalized_path.startswith("/api/agent-workspace/")
            or (
                normalized_path.startswith("/api/agent/")
                and "/skills" in normalized_path
            )
        )
    if normalized_method == "DELETE":
        return (
            normalized_path in _DELETE_EXACT
            or (
                normalized_path.startswith("/api/agent/")
                and "/skills/" in normalized_path
            )
            or normalized_path.startswith("/api/skills-library/")
        )
    return False


def retired_route(method: str, path: str) -> LegacyMutationDecision:
    """Reject old high-risk routes that cannot carry a bound confirmation."""

    normalized = (str(method or "").upper(), str(path or "").split("?", 1)[0])
    if normalized in {
        ("POST", "/api/agent/create"),
        ("DELETE", "/api/agent/delete"),
        ("POST", "/set-model"),
    }:
        return LegacyMutationDecision(
            allowed=False,
            status=MIGRATED_ROUTE_STATUS,
            error=(
                "This high-risk route was removed; use the merged Agent "
                "management confirmation flow"
            ),
        )
    return ALLOW


def office_config_update(
    current: object,
    proposed: object,
) -> LegacyMutationDecision:
    """Allow layout persistence only; Agent and branch state is read-only here."""

    if not isinstance(proposed, Mapping):
        return LegacyMutationDecision(
            allowed=False,
            status=400,
            code="agent_management_payload_invalid",
            error="Office configuration must be a JSON object",
        )
    current_mapping = current if isinstance(current, Mapping) else {}
    for owned_key in ("agents", "branches"):
        if proposed.get(owned_key, []) != current_mapping.get(owned_key, []):
            return LegacyMutationDecision(
                allowed=False,
                status=MIGRATED_ROUTE_STATUS,
                error=(
                    f"Office configuration field '{owned_key}' is owned by "
                    "the merged Agent management API"
                ),
            )
    return ALLOW


def workspace_update(body: object) -> LegacyMutationDecision:
    """Prevent the workspace multiplexer from bypassing profile commands."""

    if not isinstance(body, Mapping):
        return LegacyMutationDecision(
            allowed=False,
            status=400,
            code="agent_management_payload_invalid",
            error="Agent workspace request must be a JSON object",
        )
    if body.get("action") != "updateSettings":
        return ALLOW
    forbidden = sorted(_WORKSPACE_PROFILE_FIELDS.intersection(body))
    if forbidden:
        return LegacyMutationDecision(
            allowed=False,
            status=MIGRATED_ROUTE_STATUS,
            error=(
                "Agent profile fields moved to the merged management API: "
                + ", ".join(forbidden)
            ),
        )
    return ALLOW
