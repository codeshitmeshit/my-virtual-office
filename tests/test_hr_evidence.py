"""Bounded read-only HR evidence collection and privacy sanitization."""

import sys
from dataclasses import asdict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_evidence import (
    EvidenceCandidate,
    HREvidenceCollector,
    HREvidencePorts,
    HREvidenceValidationError,
)


LOCAL_DATE = "2026-07-19"


class FakePort:
    def __init__(self, **sources):
        self.sources = sources
        self.calls = []

    def _read(self, source, ai_id, local_date):
        self.calls.append((source, ai_id, local_date))
        value = self.sources.get(source, ())
        if isinstance(value, Exception):
            raise value
        return value

    def read_project_transitions(self, ai_id, local_date):
        return self._read("projects", ai_id, local_date)

    def read_task_transitions(self, ai_id, local_date):
        return self._read("tasks", ai_id, local_date)

    def read_meeting_contributions(self, ai_id, local_date):
        return self._read("meetings", ai_id, local_date)

    def read_artifact_metadata(self, ai_id, local_date):
        return self._read("artifacts", ai_id, local_date)

    def read_execution_results(self, ai_id, local_date):
        return self._read("executions", ai_id, local_date)

    def read_blockers_and_waiting(self, ai_id, local_date):
        return self._read("runtime", ai_id, local_date)


def ports(fake):
    return HREvidencePorts(fake, fake, fake, fake, fake, fake)


def item(evidence_type, reference_id, summary, metadata=None, date=LOCAL_DATE):
    return EvidenceCandidate(
        evidence_type,
        reference_id,
        summary,
        date,
        metadata or {},
    )


def test_collects_typed_dated_evidence_from_every_read_only_source():
    fake = FakePort(
        projects=[
            item(
                "project_transition",
                "project-1:event-2",
                "项目进入交付阶段",
                {"projectId": "project-1", "fromState": "active", "toState": "review"},
            )
        ],
        tasks=[item("task_transition", "task-1:event-3", "任务完成")],
        meetings=[item("meeting_contribution", "meeting-1:turn-4", "提出风险方案")],
        artifacts=[item("artifact", "artifact-1", "产出设计文档")],
        executions=[item("execution_result", "run-1", "测试执行通过")],
        runtime=[
            item("blocker", "blocker-1", "等待接口"),
            item("waiting_state", "wait-1", "等待评审"),
        ],
    )
    result = HREvidenceCollector(ports(fake)).collect("agent-1", local_date=LOCAL_DATE)
    assert len(result.items) == 7
    assert {entry.evidence_type for entry in result.items} == {
        "project_transition",
        "task_transition",
        "meeting_contribution",
        "artifact",
        "execution_result",
        "blocker",
        "waiting_state",
    }
    assert result.failures == ()
    assert {call[0] for call in fake.calls} == {
        "projects",
        "tasks",
        "meetings",
        "artifacts",
        "executions",
        "runtime",
    }


def test_each_source_is_capped_and_duplicate_references_are_removed():
    fake = FakePort(
        tasks=[
            item("task_transition", f"task-{index}", f"transition {index}")
            for index in range(5)
        ],
        projects=[
            item("project_transition", "same", "first"),
            item("project_transition", "same", "duplicate"),
        ],
    )
    result = HREvidenceCollector(ports(fake), per_source_cap=3).collect(
        "agent-1", local_date=LOCAL_DATE
    )
    assert len([entry for entry in result.items if entry.evidence_type == "task_transition"]) == 3
    assert len([entry for entry in result.items if entry.evidence_type == "project_transition"]) == 1
    assert result.truncated_sources == ("tasks",)


def test_cap_bounds_lazy_sources_without_materializing_the_whole_iterator():
    reads = []

    def candidates():
        for index in range(1_000):
            reads.append(index)
            yield item("task_transition", f"task-{index}", f"transition {index}")

    fake = FakePort(tasks=candidates())
    result = HREvidenceCollector(ports(fake), per_source_cap=3).collect(
        "agent-1", local_date=LOCAL_DATE
    )
    assert len(result.items) == 3
    assert reads == [0, 1, 2, 3]


def test_secret_values_are_redacted_and_private_or_raw_metadata_is_excluded():
    fake = FakePort(
        executions=[
            item(
                "execution_result",
                "run-1",
                "provider token=super-secret completed",
                {
                    "executionId": "run-1",
                    "resultState": "passed",
                    "credential": "do-not-copy",
                    "rawProviderEnvelope": "private",
                    "transcript": "private transcript",
                    "ownerEmail": "person@example.com",
                },
            )
        ]
    )
    result = HREvidenceCollector(ports(fake)).collect("agent-1", local_date=LOCAL_DATE)
    encoded = str(asdict(result))
    assert "super-secret" not in encoded
    assert "do-not-copy" not in encoded
    assert "private transcript" not in encoded
    assert "person@example.com" not in encoded
    assert "[redacted]" in result.items[0].summary
    assert result.items[0].metadata == {
        "executionId": "run-1",
        "resultState": "passed",
    }


def test_one_source_failure_is_sanitized_and_does_not_block_others():
    fake = FakePort(
        projects=RuntimeError("secret provider envelope"),
        tasks=[item("task_transition", "task-1", "完成任务")],
    )
    result = HREvidenceCollector(ports(fake)).collect("agent-1", local_date=LOCAL_DATE)
    assert [entry.reference_id for entry in result.items] == ["task-1"]
    assert result.failures[0].source == "projects"
    assert result.failures[0].error_code == "evidence_source_failed"
    assert "secret" not in str(result.failures)


@pytest.mark.parametrize(
    "candidate",
    (
        item("task_transition", "wrong-source", "bad"),
        item("project_transition", "wrong-date", "bad", date="2026-07-18"),
        item("project_transition", "bad-summary", ""),
    ),
)
def test_invalid_source_output_is_excluded_with_a_source_failure(candidate):
    fake = FakePort(projects=[candidate])
    result = HREvidenceCollector(ports(fake)).collect("agent-1", local_date=LOCAL_DATE)
    assert result.items == ()
    assert result.failures[0].source == "projects"
    assert result.failures[0].error_code == HREvidenceValidationError.code


def test_invalid_scope_or_port_configuration_is_rejected():
    with pytest.raises(HREvidenceValidationError, match="between"):
        HREvidenceCollector(ports(FakePort()), per_source_cap=0)
    collector = HREvidenceCollector(ports(FakePort()))
    with pytest.raises(HREvidenceValidationError, match="ai_id"):
        collector.collect("agent one", local_date=LOCAL_DATE)
    with pytest.raises(HREvidenceValidationError, match="YYYY-MM-DD"):
        collector.collect("agent-1", local_date="07/19/2026")


def test_evidence_module_does_not_import_mutating_domains_or_server():
    source = (APP_DIR / "services" / "hr_evidence.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "save_project" not in source
    assert "update_task" not in source
