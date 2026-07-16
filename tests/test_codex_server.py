#!/usr/bin/env python3
"""Server-side lifecycle tests for Codex conversation state and busy handling."""

import os
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-server-test-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_CODEX_CHAT_FAST_PATH_ENABLED"] = "0"

import server


AGENT = {
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "providerKind": "codex",
    "name": "Codex",
    "profile": "local",
}


class BlockingProvider:
    def __init__(self, workspace, started, release):
        self.workspace = workspace
        self.started = started
        self.release = release

    def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
        self.started.set()
        if event_callback:
            event_callback({
                "id": "event-1", "sequence": 1, "type": "activity", "status": "running",
                "threadId": thread_id or "thr-server-test", "turnId": "turn-server-test",
                "itemId": "cmd-1", "name": "commandExecution", "input": {"token": "secret-value"},
                "ts": 1,
            })
        self.release.wait(5)
        return {
            "ok": True,
            "status": "completed",
            "reply": "done",
            "threadId": thread_id or "thr-server-test",
            "turnId": "turn-server-test",
            "modifiedFiles": [],
        }


class RaisingProvider:
    def __init__(self, workspace):
        self.workspace = workspace

    def send_message(self, *args, **kwargs):
        raise RuntimeError("provider exploded")


def test_different_conversations_do_not_share_agent_admission_lock():
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as status_dir:
        release = threading.Event()
        both_started = threading.Event()
        started = []
        started_lock = threading.Lock()

        class ParallelProvider:
            def __init__(self):
                self.workspace = workspace

            def send_message(self, message, conversation_id="", **_kwargs):
                with started_lock:
                    started.append(conversation_id)
                    if len(started) == 2:
                        both_started.set()
                release.wait(2)
                return {"ok": True, "status": "completed", "reply": f"done-{conversation_id}", "threadId": f"thr-{conversation_id}", "turnId": f"turn-{conversation_id}"}

        old = (server.STATUS_DIR, server.get_roster, server._codex_provider_from_config)
        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        provider = ParallelProvider()
        server._codex_provider_from_config = lambda: provider
        results = {}

        def run(conversation_id):
            results[conversation_id] = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": conversation_id,
                "conversationId": conversation_id,
            })

        workers = [threading.Thread(target=run, args=(conversation_id,)) for conversation_id in ("conv-one", "conv-two")]
        try:
            for worker in workers:
                worker.start()
            assert both_started.wait(1)
            diagnostics = server._codex_admission_diagnostics()
            assert diagnostics["activeConversations"] >= 2
            release.set()
            for worker in workers:
                worker.join(2)
            assert set(started) == {"conv-one", "conv-two"}
            assert all(result["ok"] for result in results.values())
            assert server._get_codex_active("codex-local", "conv-one") is None
            assert server._get_codex_active("codex-local", "conv-two") is None
        finally:
            release.set()
            for worker in workers:
                worker.join(2)
            server.STATUS_DIR, server.get_roster, server._codex_provider_from_config = old


def test_busy_rejects_second_request_and_releases_lock():
    with tempfile.TemporaryDirectory() as workspace:
        started = threading.Event()
        release = threading.Event()
        provider = BlockingProvider(workspace, started, release)
        old_roster = server.get_roster
        old_provider = server._codex_provider_from_config
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: provider
        first_result = {}

        def run_first():
            first_result.update(server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "first",
                "conversationId": "conv-busy",
            }))

        worker = threading.Thread(target=run_first)
        try:
            worker.start()
            assert started.wait(2)
            second = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "second",
                "conversationId": "conv-busy",
            })
            assert second["ok"] is False
            assert second["status"] == "busy"
            assert second["busyCode"] == "busy_by_conversation"
            assert second["_status"] == 409

            release.set()
            worker.join(5)
            assert first_result["ok"] is True

            third = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "third",
                "conversationId": "conv-busy",
            })
            assert third["ok"] is True
        finally:
            release.set()
            worker.join(5)
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_provider_exception_clears_active_operation():
    with tempfile.TemporaryDirectory() as workspace:
        old_roster = server.get_roster
        old_provider = server._codex_provider_from_config
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: RaisingProvider(workspace)
        try:
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "boom",
                "conversationId": "conv-exception",
            })
            assert result["ok"] is False
            assert result["status"] == "execution_failed"
            assert "provider exploded" in result["error"]
            assert server._get_codex_active("codex-local") is None
        finally:
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_review_codex_chat_forces_provider_read_only_sandbox():
    with tempfile.TemporaryDirectory() as workspace:
        old_roster = server.get_roster
        old_provider = server._codex_provider_from_config

        class ReviewProvider:
            def __init__(self):
                self.workspace = workspace
                self.sandbox = "workspace-write"
                self.approval_policy = "on-request"

            def send_message(self, *args, **kwargs):
                assert self.sandbox == "read-only"
                assert self.approval_policy == "never"
                return {"ok": True, "status": "completed", "reply": "reviewed", "modifiedFiles": []}

        provider = ReviewProvider()
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: provider
        try:
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "read-only review",
                "conversationId": "conv-review-read-only",
                "workspace": workspace,
                "_reviewReadOnly": True,
            })
            assert result["ok"] is True
            assert provider.sandbox == "read-only"
            assert provider.approval_policy == "never"
        finally:
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_codex_chat_forwards_validated_image_attachments_to_provider():
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as status_dir:
        image_path = os.path.join(status_dir, "latest.png")
        with open(image_path, "wb") as stream:
            stream.write(b"image")
        calls = []

        class AttachmentProvider:
            def __init__(self):
                self.workspace = workspace

            def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False, attachments=None):
                calls.append(list(attachments or []))
                return {"ok": True, "status": "completed", "reply": "saw latest image", "threadId": "thr-image", "turnId": "turn-image", "modifiedFiles": []}

        old_status_dir = server.STATUS_DIR
        old_roster = server.get_roster
        old_provider = server._codex_provider_from_config
        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = AttachmentProvider
        try:
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "inspect image",
                "conversationId": "conv-image",
                "attachments": [{"path": image_path, "mimeType": "image/png", "name": "latest.png"}],
            })
            assert result["ok"] is True
            assert len(calls) == 1 and len(calls[0]) == 1
            assert calls[0][0]["path"] == os.path.realpath(image_path)
            assert calls[0][0]["mimeType"] == "image/png"
            assert calls[0][0]["name"] == "latest.png"
        finally:
            server.STATUS_DIR = old_status_dir
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_human_codex_chat_persists_user_and_reply_to_comm_history():
    old_status_dir = server.STATUS_DIR
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        class ReplyProvider:
            def __init__(self, workspace):
                self.workspace = workspace

            def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
                assert allow_interaction is True
                return {
                    "ok": True,
                    "status": "completed",
                    "reply": "reply from codex",
                    "threadId": "thr-history",
                    "turnId": "turn-history",
                    "modifiedFiles": [],
                }

        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: ReplyProvider(workspace)
        try:
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "hello codex history",
                "conversationId": "conv-history",
                "fromType": "human",
                "fromDisplayName": "User",
                "sourceApp": "virtual-office",
                "sourceSurface": "chat-window",
            })
            assert result["ok"] is True
            events = server._load_comm_history(limit=20, conversation_id="conv-history", agent_id="codex-local")
            texts = [event.get("text") for event in events]
            assert "hello codex history" in texts
            assert "reply from codex" in texts
            user_event = next(event for event in events if event.get("text") == "hello codex history")
            reply_event = next(event for event in events if event.get("text") == "reply from codex")
            assert user_event["from"]["id"] == "user"
            assert user_event["to"]["id"] == "codex-local"
            assert reply_event["from"]["id"] == "codex-local"
            assert reply_event["to"]["id"] == "user"
            assert reply_event["inReplyTo"] == user_event["id"]
        finally:
            server.STATUS_DIR = old_status_dir
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_thread_mapping_persists_and_resets():
    old_status_dir = server.STATUS_DIR
    with tempfile.TemporaryDirectory() as status_dir:
        server.STATUS_DIR = status_dir
        try:
            server._set_codex_thread_id("codex-local", "conv-1", "thr-1")
            assert server._get_codex_thread_id("codex-local", "conv-1") == "thr-1"
            assert server._get_codex_thread_id("codex-local", "conv-2") == ""
            assert server._reset_codex_thread_id("codex-local", "conv-1") is True
            assert server._get_codex_thread_id("codex-local", "conv-1") == ""
        finally:
            server.STATUS_DIR = old_status_dir


def test_archived_codex_thread_mapping_is_reset_and_retried():
    old_status_dir = server.STATUS_DIR
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config

    class ArchivedThenOkProvider:
        def __init__(self, workspace):
            self.workspace = workspace
            self.calls = []

        def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
            self.calls.append(thread_id)
            if thread_id == "thr-archived":
                return {
                    "ok": False,
                    "status": "execution_failed",
                    "error": "session thr-archived is archived. Run `codex unarchive thr-archived` to unarchive it first.",
                    "threadId": "thr-archived",
                    "modifiedFiles": [],
                }
            return {
                "ok": True,
                "status": "completed",
                "reply": "fresh thread reply",
                "threadId": "thr-fresh",
                "turnId": "turn-fresh",
                "modifiedFiles": [],
            }

    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        provider = ArchivedThenOkProvider(workspace)
        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: provider
        try:
            server._set_codex_thread_id("codex-local", "conv-archived", "thr-archived")
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "hello",
                "conversationId": "conv-archived",
            })
            assert result["ok"] is True
            assert result["reply"] == "fresh thread reply"
            assert result["threadId"] == "thr-fresh"
            assert result["recoveredFromArchivedThread"] == "thr-archived"
            assert provider.calls == ["thr-archived", ""]
            assert server._get_codex_thread_id("codex-local", "conv-archived") == "thr-fresh"
        finally:
            server.STATUS_DIR = old_status_dir
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_codex_test_exposes_safe_native_bridge_metadata():
    old_provider = server._codex_provider_from_config

    class MetadataProvider:
        def test(self):
            return {
                "ok": True,
                "protocol": "app-server",
                "mode": "app-server",
                "nativeRuntime": True,
                "binary": "/usr/bin/codex",
                "binaryDetected": True,
                "bridgeConfigured": True,
                "agents": [],
            }

    server._codex_provider_from_config = lambda: MetadataProvider()
    try:
        result = server._handle_codex_test()
        assert result["ok"] is True
        assert result["protocol"] == "app-server"
        assert result["nativeRuntime"] is True
        assert result["binaryDetected"] is True
        assert "apiKey" not in str(result)
        assert "token" not in str(result).lower()
    finally:
        server._codex_provider_from_config = old_provider


def test_activity_persists_redacted_and_reports_active_conversation():
    old_status_dir = server.STATUS_DIR
    with tempfile.TemporaryDirectory() as status_dir:
        server.STATUS_DIR = status_dir
        try:
            server._append_codex_activity("codex-local", "conv-activity", {
                "id": "evt", "sequence": 1, "type": "activity", "status": "running",
                "input": {"Authorization": "Bearer top-secret", "nested": {"api_key": "abc"}},
            })
            result = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-activity"]})
            assert result["ok"] is True
            payload = str(result["events"])
            assert "top-secret" not in payload
            assert "abc" not in payload
            assert "[REDACTED]" in payload
            server._append_codex_activity("codex-local", "conv-activity", {
                "id": "reasoning-sensitive", "sequence": 2, "type": "reasoning", "status": "running",
                "itemId": "reason-1", "text": "Authorization: Bearer private-token " + ("x" * 13000),
            })
            result = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-activity"]})
            reasoning = next(event for event in result["events"] if event.get("type") == "reasoning")
            assert "private-token" not in reasoning["text"]
            assert "[REDACTED]" in reasoning["text"]
            assert reasoning["text"].endswith("[TRUNCATED]")
            server._append_codex_activity("codex-local", "conv-activity", {
                "id": "evt-2", "sequence": 1, "type": "turn", "status": "running",
            })
            result = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-activity"]})
            assert [event["sequence"] for event in result["events"]] == [1, 2, 3]
            assert result["events"][2]["providerSequence"] == 1
            server._append_codex_activity("codex-local", "conv-orphan", {
                "id": "pending", "sequence": 1, "type": "interaction", "status": "pending",
                "operationId": "old-operation", "interactionId": "10",
            })
            orphan = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-orphan"]})
            assert orphan["events"][0]["status"] == "unavailable"
        finally:
            server.STATUS_DIR = old_status_dir


def test_codex_agent_create_delete_handlers_use_native_provider():
    old_config = server.VO_CONFIG
    old_roster = server.get_roster
    old_refresh = server.refresh_agent_maps
    with tempfile.TemporaryDirectory() as tmp:
        server.VO_CONFIG = {
            **server.VO_CONFIG,
            "codex": {
                "enabled": True,
                "homePath": os.path.join(tmp, "home"),
                "binary": "codex",
                "workspace": os.path.join(tmp, "legacy"),
                "workspaceRoot": os.path.join(tmp, "agents"),
                "mainWorkspace": os.path.join(tmp, "main"),
                "name": "Codex",
                "agentId": "local",
                "model": "gpt-test",
                "replyText": "ok",
                "bridgeUrl": "",
                "includeMain": True,
                "includeNativeAgents": True,
                "registerNativeAgents": True,
            },
        }
        server.refresh_agent_maps = lambda: None
        try:
            created = server._handle_agent_create({
                "agentPlatform": "codex",
                "name": "Review Bot",
                "id": "review-bot",
                "role": "Reviewer",
            })
            assert created["ok"] is True
            assert created["providerKind"] == "codex"
            assert os.path.isdir(created["workspace"])

            server.get_roster = lambda: [{
                "id": "codex-review-bot",
                "statusKey": "codex-review-bot",
                "providerKind": "codex",
                "providerAgentId": "review-bot",
                "profile": "review-bot",
                "name": "Review Bot",
            }]
            deleted = server._handle_agent_delete({"id": "codex-review-bot"})
            assert deleted["ok"] is True
            assert not os.path.exists(created["workspace"])
        finally:
            server.VO_CONFIG = old_config
            server.get_roster = old_roster
            server.refresh_agent_maps = old_refresh


def test_codex_approval_pending_and_respond_handlers_delegate_to_provider():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config

    class ApprovalProvider:
        calls = []

        def pending_approval(self, profile):
            self.calls.append(("pending", profile))
            return {"ok": True, "pending": {"id": "approval-1", "status": "pending"}, "pending_count": 1}

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append(("respond", profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

    provider = ApprovalProvider()
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    try:
        pending = server._handle_codex_approval_pending({"agentId": ["codex-local"]})
        assert pending["ok"] is True
        assert pending["pending"]["id"] == "approval-1"
        assert pending["profile"] == "local"
        assert provider.calls[-1] == ("pending", "local")

        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "approvalId": "approval-1",
            "choice": "approve",
            "sessionId": "thr-1",
        })
        assert responded["ok"] is True
        assert responded["_status"] == 200
        assert provider.calls[-1] == ("respond", "local", "approval-1", "approve", "thr-1")

        missing = server._handle_codex_approval_respond({"agentId": "codex-local"})
        assert missing["ok"] is False
        assert missing["_status"] == 400
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider


def test_codex_approval_respond_persists_history_once_and_emits_presence():
    old_status_dir = server.STATUS_DIR
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_presence = server.gateway_presence.set_provider_event
    presence_events = []

    class ApprovalProvider:
        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            return {
                "ok": True,
                "status": "submitted",
                "approvalId": approval_id,
                "approval": {
                    "id": approval_id,
                    "approval_id": approval_id,
                    "threadId": session_id,
                    "turnId": "turn-approval",
                },
            }

    with tempfile.TemporaryDirectory() as status_dir:
        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: ApprovalProvider()
        server.gateway_presence.set_provider_event = lambda status_key, provider, payload: presence_events.append((status_key, provider, payload))
        try:
            body = {
                "agentId": "codex-local",
                "conversationId": "conv-approval",
                "approvalId": "approval-1",
                "choice": "approve",
                "sessionId": "thr-approval",
            }
            first = server._handle_codex_approval_respond(body)
            second = server._handle_codex_approval_respond(body)

            assert first["ok"] is True
            assert first["approvalChoice"] == "approve"
            assert first["approval"]["status"] == "approved"
            assert first["message"]["approval"]["status"] == "approved"
            assert second["ok"] is True

            events = server._load_comm_history(limit=20, conversation_id="conv-approval", agent_id="codex-local")
            approval_events = [
                event for event in events
                if (event.get("metadata") or {}).get("event") == "approval.responded"
            ]
            assert len(approval_events) == 1
            assert approval_events[0]["text"] == "Codex approval approved."
            assert approval_events[0]["metadata"]["approvalId"] == "approval-1"
            assert approval_events[0]["metadata"]["threadId"] == "thr-approval"
            assert approval_events[0]["metadata"]["turnId"] == "turn-approval"

            assert presence_events
            status_key, provider, payload = presence_events[-1]
            assert status_key == "codex-local"
            assert provider == "codex"
            assert payload["event"] == "approval.responded"
            assert payload["approval_id"] == "approval-1"
            assert payload["thread_id"] == "thr-approval"
            assert payload["turn_id"] == "turn-approval"
            assert payload["choice"] == "approve"
        finally:
            server.STATUS_DIR = old_status_dir
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider
            server.gateway_presence.set_provider_event = old_presence


def test_conversation_lock_reference_prevents_split_lock_identity():
    agent_id = "codex-lock-race"
    conversation_id = "conv-lock-race"
    key = (agent_id, conversation_id)
    first = server._codex_operation_lock(agent_id, conversation_id)
    assert first.acquire(blocking=False)
    waiting_reference = server._codex_operation_lock(agent_id, conversation_id)
    try:
        assert waiting_reference is first
        server._release_codex_operation_lock(agent_id, conversation_id, first)

        newcomer = server._codex_operation_lock(agent_id, conversation_id)
        assert newcomer is waiting_reference
        assert waiting_reference.acquire(blocking=False)
        assert newcomer.acquire(blocking=False) is False
        server._discard_codex_operation_lock(agent_id, conversation_id, newcomer)
        server._release_codex_operation_lock(agent_id, conversation_id, waiting_reference)
        assert key not in server._CODEX_OPERATION_LOCKS
        assert key not in server._CODEX_OPERATION_LOCK_REFERENCES
    finally:
        with server._CODEX_OPERATION_LOCKS_GUARD:
            server._CODEX_OPERATION_LOCKS.pop(key, None)
            server._CODEX_OPERATION_LOCK_REFERENCES.pop(key, None)


if __name__ == "__main__":
    test_busy_rejects_second_request_and_releases_lock()
    test_provider_exception_clears_active_operation()
    test_thread_mapping_persists_and_resets()
    test_archived_codex_thread_mapping_is_reset_and_retried()
    test_codex_test_exposes_safe_native_bridge_metadata()
    test_activity_persists_redacted_and_reports_active_conversation()
    test_codex_agent_create_delete_handlers_use_native_provider()
    test_codex_approval_pending_and_respond_handlers_delegate_to_provider()
    test_codex_approval_respond_persists_history_once_and_emits_presence()
    test_conversation_lock_reference_prevents_split_lock_identity()
    print("ok")
