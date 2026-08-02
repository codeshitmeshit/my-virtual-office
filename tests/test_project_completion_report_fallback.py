#!/usr/bin/env python3
"""Behavior contracts for deterministic completion-report chat fallback."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_audit import append_completion_report_delivery_audit
from services.project_completion_report_delivery import CompletionReportDeliveryError
from services.project_completion_report_fallback import deliver_with_chat_fallback


PROJECT = {"id": "project-1", "title": "Demo"}
OCCURRENCE = {"occurrenceId": "stage-run:run-1", "version": 1}
REPORT = {
    "goal": "Ship",
    "conclusion": "Done",
    "keyResults": ["Artifact ready"],
    "nonFatalExceptions": [],
    "followUps": ["Review it"],
    "importantArtifacts": [{"label": "Final", "path": "FINAL.md", "note": "Primary result"}],
}


def test_primary_success_returns_notification_channel_without_chat_fallback():
    chats = []
    events = []

    result = deliver_with_chat_fallback(
        PROJECT,
        OCCURRENCE,
        REPORT,
        primary_delivery=lambda: {"ok": True, "status": "sent", "messageId": "notification-message"},
        chat_delivery=lambda chat_id, markdown: chats.append((chat_id, markdown)) or {"ok": True},
        owner_chat_id="owner-chat",
        audit=events.append,
    )

    assert result["deliveryChannel"] == "notification_app"
    assert result["messageId"] == "notification-message"
    assert chats == []
    assert events == [{
        "projectId": "project-1",
        "occurrenceId": "stage-run:run-1",
        "primaryStatus": "sent",
        "primaryCode": "",
        "fallbackDecision": "not_needed",
        "fallbackStatus": "",
        "fallbackCode": "",
        "finalChannel": "notification_app",
        "messageId": "notification-message",
    }]


def test_missing_notification_app_falls_back_once_to_fixed_owner_chat():
    chats = []
    events = []

    result = deliver_with_chat_fallback(
        PROJECT,
        OCCURRENCE,
        REPORT,
        primary_delivery=lambda: {
            "ok": False,
            "status": "notification_app_required",
            "error": "notification app missing",
        },
        chat_delivery=lambda chat_id, markdown: chats.append((chat_id, markdown)) or {
            "ok": True,
            "status": "sent",
            "messageId": "chat-message",
        },
        owner_chat_id="owner-chat",
        audit=events.append,
    )

    assert result == {
        "ok": True,
        "status": "sent",
        "messageId": "chat-message",
        "deliveryChannel": "chat_app_fallback",
        "primaryStatus": "notification_app_required",
    }
    assert chats[0][0] == "owner-chat"
    assert "项目完成汇报：Demo" in chats[0][1]
    assert "Artifact ready" in chats[0][1]
    assert events[-1]["fallbackDecision"] == "attempted"
    assert events[-1]["fallbackStatus"] == "sent"
    assert events[-1]["finalChannel"] == "chat_app_fallback"


def test_primary_configuration_exception_is_a_deterministic_fallback_trigger():
    def missing_notification_destination():
        raise CompletionReportDeliveryError(
            "project_owner_feishu_destination_missing",
            "notification app is not configured",
            recoverable=False,
        )

    result = deliver_with_chat_fallback(
        PROJECT,
        OCCURRENCE,
        REPORT,
        primary_delivery=missing_notification_destination,
        chat_delivery=lambda _chat_id, _markdown: {"ok": True, "status": "sent", "messageId": "chat"},
        owner_chat_id="owner-chat",
        audit=lambda _event: None,
    )

    assert result["ok"] is True
    assert result["deliveryChannel"] == "chat_app_fallback"
    assert result["primaryStatus"] == "project_owner_feishu_destination_missing"


def test_explicit_primary_failure_falls_back_but_unknown_result_does_not():
    for primary_status, expected_chat_calls in (
        ("feishu_error", 1),
        ("invalid_app_config", 1),
        ("network_error", 0),
        ("timeout", 0),
        ("delivery_timeout", 0),
    ):
        chats = []
        result = deliver_with_chat_fallback(
            PROJECT,
            OCCURRENCE,
            REPORT,
            primary_delivery=lambda value=primary_status: {"ok": False, "status": value, "code": 500},
            chat_delivery=lambda chat_id, markdown: chats.append((chat_id, markdown)) or {
                "ok": True, "status": "sent", "messageId": "chat-message",
            },
            owner_chat_id="owner-chat",
            audit=lambda _event: None,
        )
        assert len(chats) == expected_chat_calls, primary_status
        if expected_chat_calls:
            assert result["deliveryChannel"] == "chat_app_fallback"
        else:
            assert result["status"] == primary_status
            assert result.get("deliveryChannel") is None


def test_chat_fallback_failure_preserves_both_channel_outcomes():
    result = deliver_with_chat_fallback(
        PROJECT,
        OCCURRENCE,
        REPORT,
        primary_delivery=lambda: {"ok": False, "status": "notification_app_required"},
        chat_delivery=lambda _chat_id, _markdown: {
            "ok": False, "status": "feishu_error", "code": 403, "error": "chat rejected",
        },
        owner_chat_id="owner-chat",
        audit=lambda _event: None,
    )

    assert result["ok"] is False
    assert result["status"] == "feishu_error"
    assert result["primaryStatus"] == "notification_app_required"
    assert result["fallbackStatus"] == "feishu_error"
    assert result["code"] == 403


def test_missing_fixed_owner_chat_returns_deterministic_failure_without_sending():
    result = deliver_with_chat_fallback(
        PROJECT,
        OCCURRENCE,
        REPORT,
        primary_delivery=lambda: {"ok": False, "status": "notification_app_required"},
        chat_delivery=lambda *_args: (_ for _ in ()).throw(AssertionError("must not send")),
        owner_chat_id="",
        audit=lambda _event: None,
    )

    assert result["status"] == "chat_fallback_destination_missing"
    assert result["primaryStatus"] == "notification_app_required"


def test_audit_writer_allows_only_bounded_redacted_routing_metadata(tmp_path):
    append_completion_report_delivery_audit(tmp_path, {
        "projectId": "p1",
        "occurrenceId": "o1",
        "primaryStatus": "feishu_error",
        "primaryCode": "401",
        "fallbackDecision": "attempted",
        "fallbackStatus": "sent",
        "fallbackCode": "",
        "finalChannel": "chat_app_fallback",
        "messageId": "m1",
        "error": "api_key=super-secret",
        "report": "THIS REPORT BODY MUST NOT BE LOGGED",
        "appSecret": "secret-value",
    }, now=lambda: "2026-08-03T00:00:00+00:00")

    line = (tmp_path / "project-completion-report-delivery.jsonl").read_text().strip()
    saved = json.loads(line)
    assert saved == {
        "at": "2026-08-03T00:00:00+00:00",
        "projectId": "p1",
        "occurrenceId": "o1",
        "primaryStatus": "feishu_error",
        "primaryCode": "401",
        "fallbackDecision": "attempted",
        "fallbackStatus": "sent",
        "fallbackCode": "",
        "finalChannel": "chat_app_fallback",
        "messageId": "m1",
    }
    assert "super-secret" not in line
    assert "REPORT BODY" not in line
    assert "secret-value" not in line
