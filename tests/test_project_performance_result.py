"""Release gates for the fixed project-execution performance harness result."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGE = ROOT / "openspec" / "changes" / "extract-project-execution-services"
if not CHANGE.exists():
    archived = sorted((ROOT / "openspec" / "changes" / "archive").glob("*-extract-project-execution-services"))
    if archived:
        CHANGE = archived[-1]

BASELINE_COUNTS = {
    "start_prepare": {"load": 1, "save": 1, "provider": 0, "notification": 0, "gateway": 0, "git_scan": 1},
    "provider_completion": {"load": 2, "save": 1, "provider": 1, "notification": 0, "gateway": 0, "git_scan": 1},
    "review_start": {"load": 1, "save": 1, "provider": 0, "notification": 0, "gateway": 0, "git_scan": 0},
    "acceptance": {"load": 2, "save": 1, "provider": 0, "notification": 0, "gateway": 0, "git_scan": 0},
    "cron_dispatch": {"load": 2, "save": 1, "provider": 0, "notification": 0, "gateway": 0, "git_scan": 0},
}


def _result():
    return json.loads((CHANGE / "performance-group6-final.json").read_text(encoding="utf-8"))


def test_final_performance_result_uses_fixed_method_and_stable_counts():
    result = _result()
    assert result["measured_head"] == "a42882e24ad4e8a13d39420b33cf3230cb19b816"
    assert result["revision_label"] == "section7-final-worktree-confirmation-2"
    assert result["warmups"] == 3
    assert result["runs"] == 20
    assert set(result["scales"]) == {"small", "medium", "large"}
    for scale in result["scales"].values():
        for operation, baseline in BASELINE_COUNTS.items():
            measured = scale[operation]
            assert measured["counts_stable"] is True
            for counter, baseline_value in baseline.items():
                assert measured["counts"][counter] <= baseline_value, (operation, counter, measured, baseline)


def test_final_result_has_a_strict_store_operation_improvement():
    result = _result()
    improvements = []
    for scale_name, scale in result["scales"].items():
        for operation, baseline in BASELINE_COUNTS.items():
            measured = scale[operation]["counts"]
            if measured["load"] < baseline["load"] or measured["save"] < baseline["save"]:
                improvements.append((scale_name, operation, measured["load"], measured["save"]))
    assert improvements == [
        ("large", "cron_dispatch", 1, 1),
        ("medium", "cron_dispatch", 1, 1),
        ("small", "cron_dispatch", 1, 1),
    ]


def test_performance_result_report_references_auditable_raw_artifact():
    report = (CHANGE / "performance-result.md").read_text(encoding="utf-8")
    assert _result()["measured_head"] in report
    assert "performance-group6-final.json" in report
    assert "one project-store load is eliminated" in report
    assert "No measured operation increased" in report
