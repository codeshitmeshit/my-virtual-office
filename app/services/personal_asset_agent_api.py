"""Transport-free Agent operations for personal assets."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Mapping

from .personal_asset_agent_access import PersonalAssetAgentAccess, _task_context
from .personal_asset_agent_auth import AuthenticatedPersonalAssetAgent
from .personal_asset_service import PersonalAssetService
from .personal_asset_store import PersonalAssetValidationError


class PersonalAssetAgentAPI:
    def __init__(self, service: PersonalAssetService, access: PersonalAssetAgentAccess):
        if not isinstance(service, PersonalAssetService):
            raise TypeError("service must be a PersonalAssetService")
        if not isinstance(access, PersonalAssetAgentAccess):
            raise TypeError("access must be a PersonalAssetAgentAccess")
        self._service = service
        self._access = access

    def request_context(
        self, identity: AuthenticatedPersonalAssetAgent, payload: Mapping[str, object]
    ) -> dict:
        return self._access.request_context(identity, payload)

    def suggest_change(
        self, identity: AuthenticatedPersonalAssetAgent, payload: Mapping[str, object]
    ) -> dict:
        if not isinstance(payload, Mapping):
            raise PersonalAssetValidationError("request must be an object")
        request_id = str(payload.get("requestId") or "").strip()
        if not request_id:
            raise PersonalAssetValidationError("requestId is required")
        task_context = _task_context(payload.get("taskContext"))
        proposal = payload.get("proposal")
        if not isinstance(proposal, Mapping):
            raise PersonalAssetValidationError("proposal must be an object")
        # 普通 Agent 只能创建 pending suggestion，不能用布尔 flag 绕过 owner 决策。
        return self._service.submit_suggestion(
            proposal=proposal,
            source={"kind": "agent", "agentId": identity.ai_id, "taskContext": task_context},
            idempotency_key=request_id,
        )

    def profile_outline(
        self, identity: AuthenticatedPersonalAssetAgent, payload: Mapping[str, object]
    ) -> dict:
        if not isinstance(payload, Mapping):
            raise PersonalAssetValidationError("request must be an object")
        request_id = str(payload.get("requestId") or "").strip()
        if not request_id:
            raise PersonalAssetValidationError("requestId is required")
        _task_context(payload.get("taskContext"))
        snapshot = self._service.snapshot()
        entries = []
        for entry in snapshot["entries"]:
            sensitive = entry["sensitivity"] == "sensitive"
            # 建档 Skill 只需目录来推导继续范围；敏感标签和所有 value 都不跨过此边界。
            entries.append(
                {
                    "id": entry["id"],
                    "category": entry["category"],
                    "label": "敏感条目" if sensitive else entry["label"],
                    "sensitivity": entry["sensitivity"],
                    "updatedAt": entry["updatedAt"],
                }
            )
        return {"revision": snapshot["revision"], "entries": entries}

    def apply_confirmed_onboarding(
        self, identity: AuthenticatedPersonalAssetAgent, payload: Mapping[str, object]
    ) -> dict:
        if not isinstance(payload, Mapping):
            raise PersonalAssetValidationError("request must be an object")
        request_id = str(payload.get("requestId") or "").strip()
        changes = payload.get("confirmedChanges")
        digest = str(payload.get("confirmationSummaryDigest") or "").strip().lower()
        if not request_id or not isinstance(changes, list):
            raise PersonalAssetValidationError("confirmed onboarding request is invalid")
        canonical = json.dumps(
            changes, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        expected_digest = hashlib.sha256(canonical).hexdigest()
        if len(digest) != 64 or not hmac.compare_digest(digest, expected_digest):
            raise PersonalAssetValidationError("confirmation summary digest does not match changes")
        task_context = _task_context(payload.get("taskContext"))
        result = self._service.apply_confirmed_batch(
            changes,
            expected_revision=payload.get("expectedRevision"),
            idempotency_key=f"onboarding:{identity.ai_id}:{request_id}",
            source={
                "kind": "onboarding",
                "agentId": identity.ai_id,
                "contextId": task_context["id"],
                "confirmationSummaryDigest": digest,
            },
        )
        # Agent 写入回执只证明保存 scope；不把完整 profile 作为写操作的隐式读取通道。
        return {
            "idempotent": bool(result.get("idempotent")),
            "revision": result["revision"],
            "savedScope": list(result.get("changeScope") or []),
        }
