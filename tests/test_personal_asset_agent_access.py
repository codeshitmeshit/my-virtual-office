import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_agent_access import PersonalAssetAgentAccess  # noqa: E402
from services.personal_asset_agent_auth import AuthenticatedPersonalAssetAgent  # noqa: E402
from services.personal_asset_store import PersonalAssetStore  # noqa: E402


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)


class Decisions:
    def __init__(self):
        self.decisions = []
        self.created_payloads = []

    def create(self, payload, *, agent_id=""):
        self.created_payloads.append((payload, agent_id))
        decision = {
            "id": f"decision-{len(self.decisions) + 1}",
            "status": "pending",
            "source": payload["source"],
            "options": payload["options"],
            "recommendation": payload["recommendation"],
            "resolution": None,
        }
        self.decisions.append(decision)
        return {"created": True, "decision": decision, "snapshot": self.snapshot()}

    def snapshot(self):
        return {"revision": len(self.decisions), "decisions": self.decisions}

    def resolve(self, option_id=None, *, custom=None, channel="local"):
        decision = self.decisions[-1]
        decision["status"] = "resolved"
        decision["resolution"] = {
            "optionId": option_id,
            "answer": custom or option_id,
            "channel": channel,
            "resolvedAt": NOW.isoformat(),
        }


@pytest.fixture
def setup(tmp_path):
    store = PersonalAssetStore(tmp_path / "assets.json", now=lambda: NOW)
    first = store.create_entry(
        {"category": "investment", "label": "资金关注", "value": "private-fund", "sensitivity": "sensitive"},
        expected_revision=0,
    )
    second = store.create_entry(
        {"category": "occupation", "label": "职业", "value": "产品", "sensitivity": "standard"},
        expected_revision=first["revision"],
    )
    decisions = Decisions()
    access = PersonalAssetAgentAccess(store, decision_workflow=decisions, now=lambda: NOW)
    agent = AuthenticatedPersonalAssetAgent("agent-1", "Agent One", "codex")
    entries = {item["category"]: item for item in second["snapshot"]["entries"]}
    return store, decisions, access, agent, entries


def payload(entry_ids, request_id="read-1", task_id="task-1"):
    return {
        "requestId": request_id,
        "entryIds": entry_ids,
        "purpose": "判断当前 VO 项目优先级",
        "taskContext": {"type": "task", "id": task_id, "label": "规划", "projectId": "project-1"},
    }


def test_sensitive_request_creates_value_free_deny_default_decision(setup):
    _store, decisions, access, agent, entries = setup
    result = access.request_context(agent, payload([entries["investment"]["id"]]))
    assert result == {"status": "decision_required", "requestId": "read-1", "decisionId": "decision-1"}
    decision_payload, agent_id = decisions.created_payloads[0]
    assert agent_id == "agent-1"
    assert decision_payload["recommendation"]["optionId"] == "A"
    assert [item["id"] for item in decision_payload["options"]] == ["A", "B", "C", "D"]
    assert "private-fund" not in json.dumps(decision_payload, ensure_ascii=False)


def test_b_discloses_once_and_second_retry_is_denied(setup):
    store, decisions, access, agent, entries = setup
    request = payload([entries["investment"]["id"]])
    access.request_context(agent, request)
    decisions.resolve("B")
    first = access.request_context(agent, request)
    second = access.request_context(agent, request)
    assert first["status"] == "disclosed"
    assert first["entries"][0]["value"] == "private-fund"
    assert second["status"] == "denied"
    assert len(store.internal_snapshot()["usageRecords"]) == 1


def test_c_allows_same_task_and_never_crosses_agent_task_or_scope(setup):
    _store, decisions, access, agent, entries = setup
    sensitive_id = entries["investment"]["id"]
    request = payload([sensitive_id])
    access.request_context(agent, request)
    decisions.resolve("C")
    assert access.request_context(agent, request)["status"] == "disclosed"
    assert access.request_context(agent, request)["status"] == "disclosed"

    other_agent = AuthenticatedPersonalAssetAgent("agent-2", "Agent Two", "codex")
    assert access.request_context(other_agent, request)["status"] == "denied"
    assert access.request_context(agent, payload([sensitive_id], task_id="task-2"))["status"] == "denied"
    expanded = payload([sensitive_id, entries["occupation"]["id"]])
    assert access.request_context(agent, expanded)["status"] == "denied"


@pytest.mark.parametrize("option_id,custom,channel", [("A", None, "local"), ("D", None, "local"), (None, "允许吧", "local"), ("A", None, "timeout")])
def test_non_structured_approval_paths_fail_closed(setup, option_id, custom, channel):
    _store, decisions, access, agent, entries = setup
    request = payload([entries["investment"]["id"]])
    access.request_context(agent, request)
    decisions.resolve(option_id, custom=custom, channel=channel)
    result = access.request_context(agent, request)
    assert result["status"] == "denied"
    assert "entries" not in result


def test_pending_and_mixed_requests_disclose_nothing(setup):
    store, _decisions, access, agent, entries = setup
    mixed = payload([entries["investment"]["id"], entries["occupation"]["id"]])
    result = access.request_context(agent, mixed)
    assert result["status"] == "decision_required"
    retry = access.request_context(agent, mixed)
    assert retry["status"] == "decision_required"
    assert "entries" not in retry
    assert store.internal_snapshot()["usageRecords"] == []
