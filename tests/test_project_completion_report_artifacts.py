#!/usr/bin/env python3
"""Final-artifact collection contracts for completion reporting."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_artifacts import (
    MAX_ARTIFACT_REFS,
    MAX_AGENT_TEXT_BYTES,
    collect_completion_report_artifacts,
)


def _reader(files, calls):
    def read(path, *, allow_text=False, associated_only=False):
        calls.append((path, allow_text, associated_only))
        if path not in files:
            return {"error": "Artifact not found", "_status": 404}
        content = files[path]
        return {
            "ok": True,
            "artifact": {
                "path": path,
                "kind": "markdown",
                "size": len(content.encode("utf-8")),
                "truncated": False,
                "content": content,
            },
        }
    return read


def test_collector_reads_only_explicit_final_result_references_in_stable_order():
    project = {
        "orchestration": {"finalReport": {"markdownPath": "PROJECT_FINAL_REPORT.md"}},
        "tasks": [
            {
                "id": "task-2",
                "executionStage": 2,
                "finalResult": {
                    "markdownPath": "task-2/TASK_FINAL_RESULT.md",
                    "artifactRefs": [{"path": "deliverables/result.json"}],
                },
                "evidence": {"changedFiles": ["internal/debug.log"]},
            },
            {
                "id": "task-1",
                "executionStage": 1,
                "finalResult": {
                    "markdownPath": "task-1/TASK_FINAL_RESULT.md",
                    "artifactRefs": ["deliverables/result.json", {"path": "media/final.pdf"}],
                },
                "evidence": {"artifactRefs": [{"path": "internal/evidence.md"}]},
            },
        ],
    }
    files = {
        "PROJECT_FINAL_REPORT.md": "project",
        "task-1/TASK_FINAL_RESULT.md": "task one",
        "task-2/TASK_FINAL_RESULT.md": "task two",
        "deliverables/result.json": '{"ok": true}',
    }
    calls = []

    result = collect_completion_report_artifacts(project, read_artifact=_reader(files, calls))

    assert [item["path"] for item in result["artifacts"]] == [
        "deliverables/result.json",
        "media/final.pdf",
    ]
    assert [item[0] for item in calls] == [
        "deliverables/result.json",
    ]
    assert all(allow_text and associated_only for _, allow_text, associated_only in calls)
    assert "internal/debug.log" not in repr(result)
    assert "internal/evidence.md" not in repr(result)
    assert "PROJECT_FINAL_REPORT.md" not in repr(result)
    assert "TASK_FINAL_RESULT.md" not in repr(result)
    pdf = next(item for item in result["artifacts"] if item["path"] == "media/final.pdf")
    assert pdf["inline"] is False
    assert pdf["content"] == ""


def test_collector_prefers_business_outputs_and_relativizes_workspace_paths():
    workspace = "/tmp/project-workspace"
    project = {
        "workspacePath": workspace,
        "orchestration": {
            "finalReport": {"markdownPath": "PROJECT_FINAL_REPORT.md"},
        },
        "tasks": [{
            "id": "task-1",
            "executionStage": 1,
            "finalResult": {
                "markdownPath": "internal/TASK_FINAL_RESULT.md",
                "artifactRefs": [
                    {"kind": "file", "path": f"{workspace}/FINAL.md"},
                    {"kind": "file", "path": f"{workspace}/supporting-data.json"},
                ],
            },
        }],
    }
    files = {
        "FINAL.md": "# Market analysis\nThe business conclusion is demand growth.",
        "supporting-data.json": '{"growth": true}',
        "internal/TASK_FINAL_RESULT.md": "Task execution summary",
        "PROJECT_FINAL_REPORT.md": "Project status and task counts",
    }
    calls = []

    result = collect_completion_report_artifacts(
        project,
        read_artifact=_reader(files, calls),
    )

    assert [item["path"] for item in result["artifacts"]] == [
        "FINAL.md",
        "supporting-data.json",
    ]
    assert [item[0] for item in calls] == ["FINAL.md", "supporting-data.json"]
    assert "business conclusion" in result["artifacts"][0]["content"]
    assert "Project status and task counts" not in repr(result)


def test_collector_reports_missing_artifact_without_substituting_process_data():
    project = {
        "tasks": [{
            "id": "task-1",
            "executionStage": 1,
            "finalResult": {"markdownPath": "missing.md", "artifactRefs": []},
            "evidence": {"executorSummary": "internal fallback must not appear"},
        }],
    }

    result = collect_completion_report_artifacts(
        project,
        read_artifact=_reader({}, []),
    )

    assert result["artifacts"] == []
    assert result["omissions"] == [{
        "path": "missing.md",
        "reason": "unavailable",
        "detail": "Artifact not found",
    }]
    assert "internal fallback" not in repr(result)


def test_collector_enforces_reference_and_total_text_limits():
    refs = [{"path": f"final/{index}.md"} for index in range(MAX_ARTIFACT_REFS + 2)]
    project = {"tasks": [{"id": "task", "executionStage": 1, "finalResult": {"artifactRefs": refs}}]}
    large = "x" * (MAX_AGENT_TEXT_BYTES // 2 + 100)
    files = {ref["path"]: large for ref in refs}

    result = collect_completion_report_artifacts(project, read_artifact=_reader(files, []))

    assert sum(len(item["content"].encode("utf-8")) for item in result["artifacts"]) <= MAX_AGENT_TEXT_BYTES
    assert any(item["reason"] == "reference_limit" for item in result["omissions"])
    assert any(item["reason"] == "text_limit" for item in result["omissions"])


def test_collector_rejects_sensitive_paths_before_reading_them():
    project = {"tasks": [{
        "id": "task",
        "executionStage": 1,
        "finalResult": {"artifactRefs": [
            {"path": ".env"},
            {"path": "release/client-secret.json"},
            {"path": "release/final.md"},
        ]},
    }]}
    calls = []

    result = collect_completion_report_artifacts(
        project,
        read_artifact=_reader({"release/final.md": "safe"}, calls),
    )

    assert [item[0] for item in calls] == ["release/final.md"]
    assert [item["path"] for item in result["omissions"]] == [
        ".env",
        "release/client-secret.json",
    ]
    assert all(item["reason"] == "sensitive_path" for item in result["omissions"])


def test_collector_scrubs_credentials_and_private_keys_before_returning_agent_input():
    project = {"tasks": [{
        "id": "task",
        "executionStage": 1,
        "finalResult": {"markdownPath": "release/final.md"},
    }]}
    sensitive = """# Final\napi_key = super-secret-value\nAuthorization: Bearer bearer-value\nwebhook=https://open.feishu.cn/open-apis/bot/v2/hook/hook-value\n-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----\n"""

    result = collect_completion_report_artifacts(
        project,
        read_artifact=_reader({"release/final.md": sensitive}, []),
    )

    content = result["artifacts"][0]["content"]
    assert content.count("[REDACTED]") >= 4
    for secret in ("super-secret-value", "bearer-value", "hook-value", "private-material"):
        assert secret not in content
