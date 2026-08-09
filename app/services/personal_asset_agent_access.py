"""按任务最小披露个人资产；敏感决策组合在此边界内完成。"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .personal_asset_agent_auth import AuthenticatedPersonalAssetAgent
from .personal_asset_store import PersonalAssetStore, PersonalAssetValidationError


JsonDict = dict[str, Any]
MAX_REQUESTED_ENTRIES = 30


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise PersonalAssetValidationError(f"{field} is invalid")
    return value.strip()


def _task_context(value: object) -> JsonDict:
    if not isinstance(value, Mapping):
        raise PersonalAssetValidationError("taskContext must be an object")
    task_type = _text(value.get("type"), "taskContext.type", 20)
    if task_type not in {"task", "meeting", "chat"}:
        raise PersonalAssetValidationError("taskContext.type is invalid")
    result = {
        "type": task_type,
        "id": _text(value.get("id"), "taskContext.id", 240),
        "label": _text(value.get("label"), "taskContext.label", 240),
    }
    if task_type == "task" and value.get("projectId"):
        result["projectId"] = _text(value.get("projectId"), "taskContext.projectId", 240)
    return result


class PersonalAssetAgentAccess:
    def __init__(
        self,
        store: PersonalAssetStore,
        *,
        decision_workflow: Any | None = None,
        now: Any | None = None,
    ):
        if not isinstance(store, PersonalAssetStore):
            raise TypeError("store must be a PersonalAssetStore")
        self.store = store
        self._decision_workflow = decision_workflow
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _now_utc(self) -> datetime:
        current = self._now()
        if not isinstance(current, datetime):
            raise PersonalAssetValidationError("clock returned an invalid time")
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc)

    def normalize_request(
        self, identity: AuthenticatedPersonalAssetAgent, payload: Mapping[str, object]
    ) -> JsonDict:
        if not isinstance(identity, AuthenticatedPersonalAssetAgent):
            raise TypeError("identity must be an AuthenticatedPersonalAssetAgent")
        if not isinstance(payload, Mapping):
            raise PersonalAssetValidationError("request must be an object")
        request_id = _text(payload.get("requestId"), "requestId", 240)
        purpose = _text(payload.get("purpose"), "purpose", 1000)
        raw_ids = payload.get("entryIds")
        if (
            not isinstance(raw_ids, Sequence)
            or isinstance(raw_ids, (str, bytes))
            or not raw_ids
            or len(raw_ids) > MAX_REQUESTED_ENTRIES
        ):
            raise PersonalAssetValidationError("entryIds must be a bounded non-empty list")
        entry_ids = [_text(item, "entryId", 160) for item in raw_ids]
        if len(set(entry_ids)) != len(entry_ids) or "*" in entry_ids:
            raise PersonalAssetValidationError("entryIds must name distinct entries")
        if any(term in purpose.lower() for term in ("全部", "完整档案", "full profile", "all assets")):
            raise PersonalAssetValidationError("purpose is too broad")
        return {
            "requestId": request_id,
            "purpose": purpose,
            "entryIds": entry_ids,
            "taskContext": _task_context(payload.get("taskContext")),
            "agentId": identity.ai_id,
        }

    def request_context(
        self, identity: AuthenticatedPersonalAssetAgent, payload: Mapping[str, object]
    ) -> JsonDict:
        request = self.normalize_request(identity, payload)
        internal = self.store.internal_snapshot()
        entries: list[JsonDict] = []
        for entry_id in request["entryIds"]:
            entry = internal["entries"].get(entry_id)
            if not isinstance(entry, dict):
                raise PersonalAssetValidationError("personal asset entry was not found")
            entries.append(copy.deepcopy(entry))
        # 混合请求不做部分披露，敏感 scope 未决时整次请求都不返回值。
        if any(item.get("sensitivity") == "sensitive" for item in entries):
            return self._sensitive_context(identity, request, entries)
        self.store.record_usage(
            request_id=request["requestId"],
            agent_id=identity.ai_id,
            task_context=request["taskContext"],
            entry_ids=request["entryIds"],
            outcome="disclosed",
        )
        return {"status": "disclosed", "requestId": request["requestId"], "entries": entries}

    @staticmethod
    def _same_task(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
        keys = ("type", "id", "projectId")
        return all(str(left.get(key) or "") == str(right.get(key) or "") for key in keys)

    def _decision(self, decision_id: str) -> JsonDict | None:
        if self._decision_workflow is None:
            return None
        snapshot = self._decision_workflow.snapshot()
        for decision in snapshot.get("decisions") or []:
            if isinstance(decision, dict) and decision.get("id") == decision_id:
                return decision
        return None

    def _create_sensitive_decision(
        self,
        identity: AuthenticatedPersonalAssetAgent,
        request: Mapping[str, Any],
        entries: Sequence[Mapping[str, Any]],
    ) -> JsonDict:
        if self._decision_workflow is None:
            raise PersonalAssetValidationError("HUMAN DECISIONS is unavailable")
        expires = self._now_utc() + timedelta(hours=1)
        labels = [str(item.get("label") or item.get("category") or item.get("id")) for item in entries]
        decision_payload = {
            "idempotencyKey": f"personal-assets:{identity.ai_id}:{request['requestId']}",
            "source": copy.deepcopy(request["taskContext"]),
            "title": "个人资产敏感信息读取",
            "situation": f"Agent {identity.ai_id} 请求读取：{', '.join(labels)}",
            "reason": str(request["purpose"]),
            "risk": "high",
            "urgency": "normal",
            "deadlineAt": expires.isoformat(),
            "timeoutConsequence": "超时默认拒绝，不向 Agent 披露任何敏感值。",
            "options": [
                {"id": "A", "label": "拒绝", "impact": "Agent 不使用这些信息继续任务。"},
                {"id": "B", "label": "仅允许一次", "impact": "只允许本请求成功披露一次。"},
                {"id": "C", "label": "允许当前任务", "impact": "仅同一 Agent、任务与范围内有效。"},
                {"id": "D", "label": "缩小范围或自定义处理", "impact": "不会自动授权，需形成新的结构化范围。"},
            ],
            "recommendation": {
                "optionId": "A",
                "reason": "敏感信息读取在没有明确批准时必须保持拒绝。",
            },
            "taskDetail": {
                "summary": "按任务范围读取个人资产敏感条目",
                "completed": [],
                "blocked": "等待 owner 决策",
                "context": f"requestId={request['requestId']}; entryCount={len(entries)}",
                "nextStep": "按决策结果重试当前读取请求",
            },
        }
        result = self._decision_workflow.create(decision_payload, agent_id=identity.ai_id)
        decision = result.get("decision") if isinstance(result, dict) else None
        if not isinstance(decision, dict) or not decision.get("id"):
            raise PersonalAssetValidationError("HUMAN DECISIONS did not create a request")
        self.store.put_access_link(
            request["requestId"],
            {
                "decisionId": decision["id"],
                "agentId": identity.ai_id,
                "taskContext": request["taskContext"],
                "entryIds": request["entryIds"],
                "expiresAt": expires.isoformat(),
            },
        )
        return decision

    def _sensitive_context(
        self,
        identity: AuthenticatedPersonalAssetAgent,
        request: Mapping[str, Any],
        entries: Sequence[JsonDict],
    ) -> JsonDict:
        link = self.store.get_access_link(request["requestId"])
        if link is None:
            decision = self._create_sensitive_decision(identity, request, entries)
            return {
                "status": "decision_required",
                "requestId": request["requestId"],
                "decisionId": decision["id"],
            }
        requested_scope = set(request["entryIds"])
        linked_scope = set(link.get("entryIds") or [])
        if (
            link.get("agentId") != identity.ai_id
            or not self._same_task(link.get("taskContext") or {}, request["taskContext"])
            or not requested_scope.issubset(linked_scope)
        ):
            return {"status": "denied", "requestId": request["requestId"]}
        try:
            expires = datetime.fromisoformat(str(link.get("expiresAt") or "").replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            return {"status": "denied", "requestId": request["requestId"]}
        if expires.astimezone(timezone.utc) <= self._now_utc():
            return {"status": "denied", "requestId": request["requestId"]}
        decision = self._decision(str(link.get("decisionId") or ""))
        if not decision or decision.get("status") != "resolved":
            return {
                "status": "decision_required",
                "requestId": request["requestId"],
                "decisionId": str(link.get("decisionId") or ""),
            }
        resolution = decision.get("resolution") if isinstance(decision.get("resolution"), dict) else {}
        option_id = resolution.get("optionId")
        # resolved 并不等于 approved；只有本能力定义的 B/C 才能释放数据。
        if resolution.get("channel") == "timeout" or option_id not in {"B", "C"}:
            return {"status": "denied", "requestId": request["requestId"]}
        if option_id == "B":
            consumed = self.store.consume_access_and_record_usage(
                request["requestId"], once=True, outcome="disclosed"
            )
            if not consumed.get("consumed"):
                return {"status": "denied", "requestId": request["requestId"]}
        else:
            self.store.record_usage(
                request_id=request["requestId"],
                agent_id=identity.ai_id,
                task_context=request["taskContext"],
                entry_ids=request["entryIds"],
                outcome="disclosed",
            )
        return {"status": "disclosed", "requestId": request["requestId"], "entries": list(entries)}
