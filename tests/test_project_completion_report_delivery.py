#!/usr/bin/env python3
"""Notification-app-only delivery contracts for completion reports."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from feishu_notifications import validate_notification_intent
from services.project_completion_report_delivery import (
    CompletionReportDeliveryError,
    deliver_completion_report,
)


APP_CONFIG = {
    "appId": "notification-app",
    "appSecret": "notification-secret",
    "receiveIdType": "open_id",
    "receiveId": "owner-open-id",
}
REPORT = {
    "goal": "Ship the release",
    "conclusion": "Release completed successfully.",
    "keyResults": ["Package published", "Smoke tests passed"],
    "nonFatalExceptions": ["Dashboard delayed"],
    "followUps": ["Review adoption"],
    "importantArtifacts": [
        {"label": "Release notes", "path": "release/notes.md", "note": "Owner summary"},
    ],
}


def test_delivery_builds_bounded_card_and_forces_notification_app_transport():
    calls = []

    def send(intent, **kwargs):
        calls.append((intent, kwargs))
        validate_notification_intent(intent)
        return {"ok": True, "status": "sent", "messageId": "message-1"}

    result = deliver_completion_report(
        {"id": "project-1", "title": "Launch"},
        {"occurrenceId": "stage-run:run-2", "version": 2},
        REPORT,
        app_config=APP_CONFIG,
        send_notification=send,
        project_url="http://localhost:8090/#projects?projectId=project-1",
    )

    assert result == {"ok": True, "status": "sent", "messageId": "message-1"}
    intent, kwargs = calls[0]
    assert intent["id"] == "project-completion-report:project-1:stage-run:run-2"
    assert intent["target"] == "feishu-project-completion-report"
    assert kwargs == {"app_config": APP_CONFIG, "allow_webhook": False}
    assert intent["actions"] == [{
        "category": "jump",
        "text": "打开项目报告",
        "url": "http://localhost:8090/#projects?projectId=project-1",
    }]
    assert any(label == "执行版本" and value == "v2" for label, value in intent["details"])
    assert any(label == "重要产物" and "release/notes.md" in value for label, value in intent["details"])


@pytest.mark.parametrize("missing", ["appId", "appSecret", "receiveIdType", "receiveId"])
def test_delivery_fails_without_complete_owner_notification_destination(missing):
    config = {key: value for key, value in APP_CONFIG.items() if key != missing}

    with pytest.raises(CompletionReportDeliveryError) as raised:
        deliver_completion_report(
            {"id": "project-1", "title": "Launch"},
            {"occurrenceId": "stage-run:run-1", "version": 1},
            REPORT,
            app_config=config,
            send_notification=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("send called")),
            project_url="http://localhost/project",
        )

    assert raised.value.code == "project_owner_feishu_destination_missing"
    assert raised.value.recoverable is False
