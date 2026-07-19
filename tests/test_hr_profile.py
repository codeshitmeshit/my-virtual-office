"""Contract tests for the global HR system-Agent profile."""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.system_agent_profiles import load_and_render_profile
from services.system_agent_roles import HR_ROLE


PROFILE_VERSION = "2026-07-20.2"
TOKENS = {
    "HR_NAME": HR_ROLE.display_name,
    "HR_EMOJI": HR_ROLE.emoji,
    "HR_AGENT_ID": HR_ROLE.stable_id,
    "HR_PROFILE_VERSION": PROFILE_VERSION,
}


def rendered_profile():
    return load_and_render_profile(
        APP_DIR / HR_ROLE.profile_template,
        HR_ROLE,
        tokens=TOKENS,
    )


def structured_examples(agents_md):
    return [json.loads(source) for source in re.findall(r"```json\n(.*?)\n```", agents_md, re.DOTALL)]


def test_hr_role_has_stable_identity_and_protected_meeting_eligible_policy():
    assert HR_ROLE.role_key == "hr"
    assert HR_ROLE.stable_id == "hr"
    assert HR_ROLE.display_name == "HR"
    assert HR_ROLE.profile_template == "hr-profile.md"
    assert HR_ROLE.assignable is False
    assert HR_ROLE.deletable is False
    assert HR_ROLE.meeting_eligible is True
    assert HR_ROLE.automatic_work_categories == (
        "directory_coordination",
        "daily_reporting",
        "performance_assessment",
    )


def test_hr_profile_renders_every_required_file_without_unresolved_tokens():
    profile = rendered_profile()
    assert profile.version == PROFILE_VERSION
    assert set(profile.files) == set(HR_ROLE.required_files)
    for content in profile.files.values():
        assert f"hr-profile-version: {PROFILE_VERSION}" in content.lower()
        assert "{{" not in content
        assert "}}" not in content


def test_hr_profile_limits_identity_authority_and_meeting_effects():
    profile = rendered_profile()
    soul = profile.files["SOUL.md"]
    agent = profile.files["agent.md"]
    assert "single global Human Resources Agent" in soul
    assert "Only you may author, revise, or finalize HR performance assessments" in soul
    assert "not an ordinary project executor" in soul
    assert "Meeting attendance alone is never positive or negative performance evidence" in soul
    assert "do not score, rank, punish, delete, pause, or reassign Agents" in agent


def test_hr_profile_contains_versioned_machine_readable_output_contracts():
    agents = rendered_profile().files["AGENTS.md"]
    examples = structured_examples(agents)
    assert [item["schemaVersion"] for item in examples] == [
        1,
        1,
        1,
    ]
    assert examples[0]["supportingEvidence"] == [
        "<exact excerpt from the Agent response>"
    ]
    assert examples[0]["materialConflict"] is False
    daily = examples[1]
    assert set(daily) == {
        "schemaVersion", "localDate", "agentAiId", "completedWork",
        "relatedProjectsOrTasks", "artifacts", "blockers", "requestedHelp",
        "submission",
    }
    assert daily["submission"]["state"] == "submitted|late_submitted"
    assessment = examples[2]
    assert set(assessment) == {
        "schemaVersion", "agentAiId", "localDate", "principalContributions",
        "workload", "rationale", "evidenceReferences", "blockers", "strengths",
        "improvements", "runtimeDiagnosis", "informationSufficiency", "hrAiId",
        "assessedAt",
    }
    assert assessment["hrAiId"] == "hr"
    assert assessment["workload"] == "low|appropriate|high|overloaded|insufficient_information"
    assert {
        "principalContributions",
        "rationale",
        "evidenceReferences",
        "blockers",
        "strengths",
        "improvements",
        "runtimeDiagnosis",
        "informationSufficiency",
        "assessedAt",
    }.issubset(assessment)


def test_hr_profile_neutralizes_missing_reports_and_prohibits_ranking_or_punishment():
    profile_text = "\n".join(rendered_profile().files.values())
    assert "A missing response means unknown or `not_submitted`" in profile_text
    assert "use `insufficient_information`" in profile_text
    assert "Never emit a numeric score, ordinal rank, leaderboard" in profile_text
    assert "never punish, pause, delete, or reassign an Agent" in profile_text
