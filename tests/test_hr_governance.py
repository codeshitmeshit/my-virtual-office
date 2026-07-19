"""Exhaustive caller-role disclosure and self-audit projection matrix."""

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_governance import HRCaller, HRDisclosurePolicy, HRGovernanceError


def record():
    return {
        "aiId": "agent-2",
        "name": "Builder",
        "introduction": "Builds features",
        "availability": "available",
        "status": "active",
        "agentKind": "project",
        "providerKind": "openclaw",
        "introductionProvenance": {"source": "hr"},
        "identityHistory": [{"name": "Old Builder"}],
        "publicWorkSummary": ["Completed feature"],
        "workload": "appropriate",
        "reports": [
            {
                "rawResponse": "private report",
                "claimToken": "claim-secret",
                "providerApiToken": "nested-api-secret",
            }
        ],
        "assessments": [{"rationale": "private judgment", "workload": "appropriate"}],
        "evidence": [{"referenceId": "task-1", "credential": "private-credential"}],
        "improvements": ["sensitive feedback"],
        "workflowState": "complete",
        "hrContactState": "ready",
        "accessHistory": [
            {"viewerAiId": "agent-1", "targetAiId": "agent-2", "scope": "public"},
            {"viewerAiId": "agent-2", "targetAiId": "agent-1", "scope": "public"},
        ],
        "skillReadiness": "ready",
        "grantReadiness": "ready",
        "createdAt": "2026-07-19T00:00:00+00:00",
        "updatedAt": "2026-07-19T10:00:00+00:00",
        "secretDigest": "digest-secret",
        "bearerToken": "bearer-secret",
        "providerEnvelope": {"password": "provider-password"},
        "unknownInternalField": "must not escape",
    }


@pytest.mark.parametrize(
    "caller,target,scope",
    (
        (HRCaller.human(), "agent-2", "full"),
        (HRCaller.hr(), "agent-2", "full"),
        (HRCaller.agent("agent-2"), "agent-2", "self"),
        (HRCaller.agent("agent-1"), "agent-2", "public"),
    ),
)
def test_automatic_scope_matrix(caller, target, scope):
    result = HRDisclosurePolicy.project(record(), caller=caller, target_ai_id=target)
    assert result["scope"] == scope


def test_full_projection_uses_allowlist_and_recursively_drops_credentials():
    result = HRDisclosurePolicy.project(
        record(), caller=HRCaller.human(), target_ai_id="agent-2"
    )
    assert set(result) == HRDisclosurePolicy.FULL_FIELDS | {"scope"}
    assert result["reports"][0] == {"rawResponse": "private report"}
    assert result["evidence"][0] == {"referenceId": "task-1"}
    encoded = str(result)
    for forbidden in (
        "claim-secret",
        "nested-api-secret",
        "private-credential",
        "digest-secret",
        "bearer-secret",
        "provider-password",
        "must not escape",
    ):
        assert forbidden not in encoded


def test_cross_agent_public_projection_has_exact_safe_fields():
    result = HRDisclosurePolicy.project(
        record(), caller=HRCaller.agent("agent-1"), target_ai_id="agent-2"
    )
    assert set(result) == HRDisclosurePolicy.PUBLIC_FIELDS | {"scope"}
    assert result == {
        "aiId": "agent-2",
        "name": "Builder",
        "introduction": "Builds features",
        "availability": "available",
        "publicWorkSummary": ["Completed feature"],
        "workload": "appropriate",
        "scope": "public",
    }
    for forbidden in ("reports", "assessments", "evidence", "improvements"):
        assert forbidden not in result


def test_self_projection_includes_own_feedback_and_only_own_targeted_access_history():
    result = HRDisclosurePolicy.project(
        record(), caller=HRCaller.agent("agent-2"), target_ai_id="agent-2"
    )
    assert set(result) == HRDisclosurePolicy.SELF_FIELDS | {"scope"}
    assert result["reports"][0]["rawResponse"] == "private report"
    assert result["assessments"][0]["rationale"] == "private judgment"
    assert result["improvements"] == ["sensitive feedback"]
    assert result["accessHistory"] == [
        {"viewerAiId": "agent-1", "targetAiId": "agent-2", "scope": "public"}
    ]


@pytest.mark.parametrize(
    "caller, target, requested, code",
    (
        (HRCaller.agent("agent-1"), "agent-2", "full", "hr_full_view_forbidden"),
        (HRCaller.agent("agent-1"), "agent-2", "self", "hr_self_view_forbidden"),
        (HRCaller.agent("agent-1", active=False), "agent-1", "self", "hr_inactive_caller"),
        (HRCaller.unknown(), "agent-2", "public", "hr_unknown_caller"),
        (HRCaller("unexpected", "x", True), "agent-2", "public", "hr_unknown_caller"),
    ),
)
def test_denial_matrix_has_stable_codes(caller, target, requested, code):
    with pytest.raises(HRGovernanceError) as raised:
        HRDisclosurePolicy.project(
            record(),
            caller=caller,
            target_ai_id=target,
            requested_scope=requested,
        )
    assert raised.value.code == code


def test_active_agent_can_view_inactive_target_only_through_public_projection():
    inactive = record()
    inactive["status"] = "disabled"
    inactive["availability"] = "unavailable"
    result = HRDisclosurePolicy.project(
        inactive,
        caller=HRCaller.agent("agent-1"),
        target_ai_id="agent-2",
    )
    assert result["availability"] == "unavailable"
    assert "status" not in result


def test_explicit_public_scope_is_available_to_human_without_expanding_fields():
    result = HRDisclosurePolicy.project(
        record(),
        caller=HRCaller.human(),
        target_ai_id="agent-2",
        requested_scope="public",
    )
    assert set(result) == HRDisclosurePolicy.PUBLIC_FIELDS | {"scope"}


def test_audit_projection_matrix_filters_self_and_denies_unrelated_history():
    logs = record()["accessHistory"]
    assert len(
        HRDisclosurePolicy.project_access_log(logs, caller=HRCaller.human())
    ) == 2
    assert len(HRDisclosurePolicy.project_access_log(logs, caller=HRCaller.hr())) == 2
    own = HRDisclosurePolicy.project_access_log(
        logs,
        caller=HRCaller.agent("agent-2"),
    )
    assert own == (
        {"viewerAiId": "agent-1", "targetAiId": "agent-2", "scope": "public"},
    )
    with pytest.raises(HRGovernanceError) as raised:
        HRDisclosurePolicy.project_access_log(
            logs,
            caller=HRCaller.agent("agent-1"),
            target_ai_id="agent-2",
        )
    assert raised.value.code == "hr_audit_view_forbidden"


def test_projection_does_not_mutate_authoritative_input():
    source = record()
    original = copy.deepcopy(source)
    projected = HRDisclosurePolicy.project(
        source, caller=HRCaller.human(), target_ai_id="agent-2"
    )
    projected["reports"][0]["rawResponse"] = "changed"
    assert source == original


def test_record_identity_must_match_requested_target():
    with pytest.raises(HRGovernanceError) as raised:
        HRDisclosurePolicy.project(
            record(), caller=HRCaller.human(), target_ai_id="agent-other"
        )
    assert raised.value.code == "hr_record_target_mismatch"


def test_governance_module_has_no_transport_or_storage_dependency():
    source = (APP_DIR / "services" / "hr_governance.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "hr_repository" not in source
