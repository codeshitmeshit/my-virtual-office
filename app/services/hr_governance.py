"""Trusted caller roles and server-side Human Resources disclosure projections."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Iterable, Mapping


class HRGovernanceError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class HRCaller:
    role: str
    ai_id: str
    active: bool

    @classmethod
    def human(cls) -> "HRCaller":
        return cls("human", "human", True)

    @classmethod
    def hr(cls, ai_id: str = "hr") -> "HRCaller":
        return cls("hr", ai_id, True)

    @classmethod
    def agent(cls, ai_id: str, *, active: bool = True) -> "HRCaller":
        return cls("agent", ai_id, active)

    @classmethod
    def unknown(cls) -> "HRCaller":
        return cls("unknown", "", False)


class HRDisclosurePolicy:
    """Selects one of three explicit top-level allowlists from a trusted caller."""

    FULL_FIELDS = frozenset(
        {
            "aiId",
            "name",
            "introduction",
            "availability",
            "status",
            "agentKind",
            "providerKind",
            "introductionProvenance",
            "identityHistory",
            "reports",
            "assessments",
            "evidence",
            "improvements",
            "workflowState",
            "hrContactState",
            "accessHistory",
            "grantReadiness",
            "createdAt",
            "updatedAt",
        }
    )
    PUBLIC_FIELDS = frozenset(
        {
            "aiId",
            "name",
            "introduction",
            "availability",
            "publicWorkSummary",
            "workload",
        }
    )
    SELF_FIELDS = PUBLIC_FIELDS | frozenset(
        {
            "reports",
            "assessments",
            "improvements",
            "workflowState",
            "hrContactState",
            "accessHistory",
        }
    )
    SENSITIVE_KEYS = frozenset(
        {
            "bearertoken",
            "token",
            "claimtoken",
            "secretdigest",
            "secret",
            "grantsecret",
            "credential",
            "password",
            "authorization",
            "providerenvelope",
        }
    )
    SENSITIVE_KEY_FRAGMENTS = (
        "token",
        "secret",
        "credential",
        "password",
        "authorization",
        "providerenvelope",
    )

    @staticmethod
    def _caller(caller: HRCaller) -> HRCaller:
        if not isinstance(caller, HRCaller) or caller.role not in {
            "human",
            "hr",
            "agent",
            "unknown",
        }:
            raise HRGovernanceError("hr_unknown_caller", "caller identity is unknown")
        if caller.role == "unknown" or not caller.ai_id:
            raise HRGovernanceError("hr_unknown_caller", "caller identity is unknown")
        if not caller.active:
            raise HRGovernanceError("hr_inactive_caller", "caller Agent is inactive")
        return caller

    @classmethod
    def scope_for(cls, caller: HRCaller, target_ai_id: str) -> str:
        caller = cls._caller(caller)
        if not isinstance(target_ai_id, str) or not target_ai_id:
            raise HRGovernanceError("hr_target_invalid", "target Agent is invalid")
        if caller.role in {"human", "hr"}:
            return "full"
        return "self" if caller.ai_id == target_ai_id else "public"

    @classmethod
    def authorize_scope(
        cls,
        caller: HRCaller,
        target_ai_id: str,
        requested_scope: str,
    ) -> str:
        effective = cls.scope_for(caller, target_ai_id)
        if requested_scope not in {"full", "public", "self"}:
            raise HRGovernanceError("hr_scope_invalid", "disclosure scope is invalid")
        if requested_scope == "full" and effective != "full":
            raise HRGovernanceError(
                "hr_full_view_forbidden",
                "full Human Resources records require human or HR authority",
            )
        if requested_scope == "self" and effective not in {"self", "full"}:
            raise HRGovernanceError(
                "hr_self_view_forbidden",
                "self Human Resources records require matching Agent identity",
            )
        return requested_scope

    @classmethod
    def _strip_sensitive(cls, value: object) -> object:
        if isinstance(value, Mapping):
            result = {}
            for key, nested in value.items():
                normalized = str(key).replace("_", "").replace("-", "").lower()
                if normalized in cls.SENSITIVE_KEYS or any(
                    fragment in normalized for fragment in cls.SENSITIVE_KEY_FRAGMENTS
                ):
                    continue
                result[str(key)] = cls._strip_sensitive(nested)
            return result
        if isinstance(value, (list, tuple)):
            return [cls._strip_sensitive(item) for item in value]
        return copy.deepcopy(value)

    @classmethod
    def project(
        cls,
        record: Mapping[str, object],
        *,
        caller: HRCaller,
        target_ai_id: str,
        requested_scope: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(record, Mapping):
            raise HRGovernanceError("hr_record_invalid", "HR record is invalid")
        scope = (
            cls.scope_for(caller, target_ai_id)
            if requested_scope is None
            else cls.authorize_scope(caller, target_ai_id, requested_scope)
        )
        if record.get("aiId") != target_ai_id:
            raise HRGovernanceError(
                "hr_record_target_mismatch",
                "HR record does not match the requested Agent",
            )
        fields = {
            "full": cls.FULL_FIELDS,
            "public": cls.PUBLIC_FIELDS,
            "self": cls.SELF_FIELDS,
        }[scope]
        projected = {
            key: cls._strip_sensitive(value)
            for key, value in record.items()
            if key in fields
        }
        if scope == "self" and isinstance(projected.get("accessHistory"), list):
            projected["accessHistory"] = [
                item
                for item in projected["accessHistory"]
                if isinstance(item, Mapping)
                and item.get("targetAiId") == caller.ai_id
            ]
        projected["scope"] = scope
        return projected

    @classmethod
    def project_access_log(
        cls,
        records: Iterable[Mapping[str, object]],
        *,
        caller: HRCaller,
        target_ai_id: str | None = None,
    ) -> tuple[dict[str, object], ...]:
        caller = cls._caller(caller)
        items = tuple(records)
        if any(not isinstance(item, Mapping) for item in items):
            raise HRGovernanceError("hr_audit_record_invalid", "access record is invalid")
        if caller.role in {"human", "hr"}:
            return tuple(cls._strip_sensitive(item) for item in items)
        target = target_ai_id or caller.ai_id
        if target != caller.ai_id:
            raise HRGovernanceError(
                "hr_audit_view_forbidden",
                "Agents may inspect only access records where they are the target",
            )
        return tuple(
            cls._strip_sensitive(item)
            for item in items
            if item.get("targetAiId") == caller.ai_id
        )
