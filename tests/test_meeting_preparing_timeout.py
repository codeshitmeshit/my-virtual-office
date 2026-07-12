#!/usr/bin/env python3
"""Coverage for executable meeting preparing timeout release."""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-timeout-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server


def with_store(status_dir, timeout_sec=None):
    old = (server.STATUS_DIR, server.STATUS_FILE, server.WORKFLOW_STATE_FILE, server.VO_CONFIG)
    server.STATUS_DIR = status_dir
    server.STATUS_FILE = os.path.join(status_dir, "virtual-office-status.json")
    server.WORKFLOW_STATE_FILE = os.path.join(status_dir, "workflow-state.json")
    server.VO_CONFIG = {**server.VO_CONFIG, "meetings": {"preparingTimeoutSec": timeout_sec} if timeout_sec is not None else {}}
    return old


def restore_store(old):
    server.STATUS_DIR, server.STATUS_FILE, server.WORKFLOW_STATE_FILE, server.VO_CONFIG = old


def create_preparing_meeting(idempotency_key="timeout-create"):
    result = server._handle_executable_meeting_create({
        "topic": "Preparing timeout fixture",
        "purpose": "Validate timeout release.",
        "participants": ["agent-a", "agent-b"],
        "moderator": "agent-a",
        "meetingType": "discussion",
        "maxRounds": 1,
        "idempotencyKey": idempotency_key,
    })
    assert result["ok"] is True
    assert result["meeting"]["stage"] == "preparing"
    return result["meeting"]


def age_meeting(meeting_id, seconds):
    store = server._load_exec_meeting_store()
    meeting = store["meetings"][meeting_id]
    old = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    meeting["preparingStartedAt"] = old
    meeting["createdAt"] = old
    meeting["updatedAt"] = old
    server._save_exec_meeting_store(store)


def test_preparing_timeout_defaults_to_300_and_releases_occupancy():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            assert server._meeting_preparing_timeout_sec() == 300
            meeting = create_preparing_meeting("default-timeout")
            age_meeting(meeting["id"], 301)

            active = server._meeting_active_projection()
            store = server._load_exec_meeting_store()
            released = store["meetings"][meeting["id"]]

            assert all(item["id"] != meeting["id"] for item in active)
            assert released["stage"] == "cancelled"
            assert released["cancelReason"] == "preparing_timeout"
            assert released["preparingTimeoutSec"] == 300
            assert store["occupancy"] == {}
            events = store["events"][meeting["id"]]
            assert len([e for e in events if e["type"] == "meeting_preparing_timed_out"]) == 1
        finally:
            restore_store(old)


def test_preparing_timeout_uses_config_and_keeps_unexpired_meeting():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir, timeout_sec=120)
        try:
            assert server._meeting_preparing_timeout_sec() == 120
            meeting = create_preparing_meeting("configured-timeout")
            age_meeting(meeting["id"], 60)

            active = server._meeting_active_projection()
            store = server._load_exec_meeting_store()

            assert any(item["id"] == meeting["id"] for item in active)
            assert store["meetings"][meeting["id"]]["stage"] == "preparing"
            assert store["occupancy"]["agent-a"] == meeting["id"]
            assert store["occupancy"]["agent-b"] == meeting["id"]
        finally:
            restore_store(old)


def test_preparing_timeout_invalid_config_falls_back_to_default():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir, timeout_sec="bad")
        try:
            assert server._meeting_preparing_timeout_sec() == 300
        finally:
            restore_store(old)


def test_preparing_timeout_does_not_release_other_stages_or_other_occupancy():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir, timeout_sec=30)
        try:
            meeting = create_preparing_meeting("active-not-released")
            transitioned = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "active_opening",
                "expectedVersion": meeting["version"],
            })
            assert transitioned["ok"] is True
            age_meeting(meeting["id"], 60)
            store = server._load_exec_meeting_store()
            store["meetings"]["other-meeting"] = {
                "id": "other-meeting", "stage": "active_discussion", "participants": ["other-agent"],
            }
            store["events"]["other-meeting"] = []
            store["occupancy"]["other-agent"] = "other-meeting"
            server._save_exec_meeting_store(store)

            server._meeting_active_projection()
            store = server._load_exec_meeting_store()

            assert store["meetings"][meeting["id"]]["stage"] == "active_opening"
            assert store["occupancy"]["other-agent"] == "other-meeting"
        finally:
            restore_store(old)


def test_preparing_timeout_blocks_run_after_expiry():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir, timeout_sec=30)
        try:
            meeting = create_preparing_meeting("run-blocked")
            age_meeting(meeting["id"], 60)

            result = server._handle_executable_meeting_run(meeting["id"], {})
            store = server._load_exec_meeting_store()

            assert result["alreadyTerminal"] is True
            assert result["preparingTimedOut"] is True
            assert store["meetings"][meeting["id"]]["stage"] == "cancelled"
            assert store["occupancy"] == {}
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_preparing_timeout_defaults_to_300_and_releases_occupancy()
    test_preparing_timeout_uses_config_and_keeps_unexpired_meeting()
    test_preparing_timeout_invalid_config_falls_back_to_default()
    test_preparing_timeout_does_not_release_other_stages_or_other_occupancy()
    test_preparing_timeout_blocks_run_after_expiry()
    print("test_meeting_preparing_timeout.py passed")
