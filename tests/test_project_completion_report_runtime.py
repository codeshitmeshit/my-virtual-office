from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_runtime import CompletionReportRuntimeDependencies, build_completion_report_worker


class _Repository:
    pass


def test_runtime_factory_connects_final_artifacts_agent_storage_and_notification_app():
    calls = []
    project = {"id": "p1", "workspacePath": "/tmp/work", "title": "Demo"}
    occurrence = {"occurrenceId": "stage-run:r1", "version": 1}

    dependencies = CompletionReportRuntimeDependencies(
        reporting_agent_id=lambda: "agent-reporting",
        artifact_context=lambda value: {"ok": True, "root": value["workspacePath"]},
        read_artifact=lambda context, path, **options: calls.append(
            ("read", context["root"], path, options)
        ) or {"ok": True, "artifact": {"content": "done", "kind": "markdown"}},
        generate_agent=lambda **options: calls.append(("agent", options)) or {
            "ok": True,
            "reply": (
                '{"goal":"Ship","conclusion":"Done","keyResults":[],"nonFatalExceptions":[],'
                '"followUps":[],"importantArtifacts":[]}'
            ),
        },
        notification_app_config=lambda: {
            "appId": "app",
            "appSecret": "secret",
            "receiveIdType": "open_id",
            "receiveId": "owner",
        },
        send_notification=lambda intent, **options: calls.append(("notify", intent, options)) or {"ok": True},
        project_url=lambda project_id: f"https://office/projects/{project_id}",
        now=lambda: "2026-08-03T00:00:00+00:00",
        new_token=lambda: "token",
    )

    worker = build_completion_report_worker(_Repository(), dependencies)
    collected = worker._ports.collect({
        **project,
        "orchestration": {"finalReport": {"markdownPath": "FINAL.md"}},
    })
    generated = worker._ports.generate(project, occurrence, collected)
    delivered = worker._ports.deliver(project, occurrence, generated["report"])

    assert generated["reportingAgentId"] == "agent-reporting"
    assert calls[0] == (
        "read",
        "/tmp/work",
        "FINAL.md",
        {"allow_text": True, "associated_only": True},
    )
    assert calls[1][0] == "agent"
    assert calls[1][1]["agent_id"] == "agent-reporting"
    assert calls[1][1]["conversation_id"] == "project-completion-report:p1:stage-run:r1"
    assert calls[2][0] == "notify"
    assert calls[2][2]["allow_webhook"] is False
    assert calls[2][2]["app_config"]["receiveId"] == "owner"
    assert delivered == {"ok": True}


def test_runtime_factory_turns_invalid_artifact_context_into_omissions():
    dependencies = CompletionReportRuntimeDependencies(
        reporting_agent_id=lambda: "agent-reporting",
        artifact_context=lambda _project: {"ok": False, "error": "workspace unavailable"},
        read_artifact=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not read")),
        generate_agent=lambda **_options: {"ok": False},
        notification_app_config=lambda: {},
        send_notification=lambda *_args, **_kwargs: {"ok": False},
        project_url=lambda _project_id: "",
        now=lambda: "2026-08-03T00:00:00+00:00",
        new_token=lambda: "token",
    )
    worker = build_completion_report_worker(_Repository(), dependencies)

    collected = worker._ports.collect({
        "id": "p1",
        "orchestration": {"finalReport": {"markdownPath": "FINAL.md"}},
    })

    assert collected["artifacts"] == []
    assert collected["omissions"] == [{
        "path": "FINAL.md",
        "reason": "unavailable",
        "detail": "workspace unavailable",
    }]
