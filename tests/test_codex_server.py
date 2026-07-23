#!/usr/bin/env python3
"""Server-side lifecycle tests for Codex conversation state and busy handling."""

import os
import sys
import tempfile
import threading
import time

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


def test_vo_provider_guidance_prefix_is_idempotent():
    message = server._with_vo_provider_guidance("请创建一个 VO 项目")
    assert "http://127.0.0.1:<port>/skills/index.md" in message
    assert "use known VO_PORT/.env; default 8090" in message
    assert "follow that entry to the specific VO skill" in message
    assert "no explicit escalated/sandbox_permissions parameter" in message
    assert "provider-runtime localhost connection failure before user approval is not the final VO result" in message
    assert "current approval/command channel" in message
    assert "After the user approves that exact ordinary command" in message
    assert "execute the local VO HTTP curl" in message
    assert "reads and writes" in message
    assert "issue the exact ordinary local VO curl command" in message
    assert "do not merely ask the user in prose" in message
    assert "report the access failure" in message
    assert "directly operate VO data stores" in message
    assert message.endswith("请创建一个 VO 项目")

    repeated = server._with_vo_provider_guidance(message)
    assert repeated == message
    assert repeated.count("[Virtual Office routing guidance]") == 1


def test_codex_approval_identifies_host_side_vo_skill_read_only_curl():
    approval = {
        "command": "/bin/zsh -lc 'curl -fsS --max-time 5 http://127.0.0.1:8090/skills/index.md'",
    }
    assert server._codex_approval_is_host_side_vo_skill_read(approval) is True
    assert server._codex_approval_host_side_vo_access_block_reason(approval) == ""

    reference = {
        "command": "/bin/zsh -lc 'curl -fsS http://localhost:8090/skills/vo-operating-guidelines/references/meeting-requests.md'",
    }
    assert server._codex_approval_is_host_side_vo_skill_read(reference) is True

    port_expression = {
        "command": "/bin/zsh -lc 'curl --max-time 5 -fsS http://localhost:${VO_PORT:-8090}/skills/index.md'",
    }
    assert server._codex_approval_is_host_side_vo_skill_read(port_expression) is True


def test_codex_approval_accepts_approved_local_vo_api_curl():
    approval = {
        "command": "/bin/zsh -lc 'curl -fsS --max-time 5 http://127.0.0.1:8090/api/projects'",
    }
    assert server._codex_approval_is_host_side_vo_skill_read(approval) is False
    assert server._codex_approval_is_host_side_vo_curl(approval) is True
    assert server._codex_approval_host_side_vo_access_block_reason(approval) == ""


def test_codex_approval_allows_host_side_vo_agents_roster_read_only_curl():
    approval = {
        "command": "/bin/zsh -lc 'curl -fsS --max-time 5 http://127.0.0.1:8090/api/agents'",
    }
    assert server._codex_approval_is_host_side_vo_skill_read(approval) is False
    assert server._codex_approval_is_host_side_vo_read(approval) is True
    assert server._codex_approval_host_side_vo_access_block_reason(approval) == ""


def test_codex_approval_identifies_multiline_host_side_vo_project_authoring_curl():
    approval = {
        "command": (
            "/bin/zsh -lc \"curl -fsS --max-time 3 -X POST "
            "'http://127.0.0.1:8090/api/agent/project-authoring/projects' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -H 'X-VO-Agent-Action: project-authoring' \\\n"
            "  -H 'X-VO-Agent-Id: codex-local' \\\n"
            "  --data-binary '{\"confirmation\":{\"confirmed\":true,"
            "\"summaryText\":\"x\",\"summaryDigest\":\""
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}}'\""
        ),
    }

    parsed = server._codex_approval_parse_curl(approval)

    assert parsed is not None
    assert parsed["method"] == "POST"
    assert parsed["parsed"].path == "/api/agent/project-authoring/projects"
    assert server._codex_approval_is_host_side_vo_curl(approval) is True
    assert server._codex_approval_host_side_vo_access_block_reason(approval) == ""


def test_codex_approval_identifies_wrapped_host_side_vo_skill_shell():
    approval = {
        "command": (
            "/bin/zsh -lc 'VO_PROJECT_ROOT=\"${VO_PROJECT_ROOT:-$(pwd)}\"; "
            "VO_LOCAL_URL=\"http://127.0.0.1:${VO_PORT:-8090}\"; "
            "curl --max-time 5 -sS \"$VO_LOCAL_URL/skills/index.md\"'"
        ),
    }

    assert server._codex_approval_is_host_side_vo_shell(approval) is True
    assert server._codex_approval_vo_shell_path(approval["command"]) == "/skills/index.md"
    assert server._codex_approval_vo_shell_method(approval["command"]) == "GET"


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


def test_host_side_vo_continuation_reply_delivery_is_triggered_from_append_reply():
    old_status_dir = server.STATUS_DIR
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_send = server._feishu_chat_app_text_send
    old_record = server._record_feishu_channel_event
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        sends = []
        records = []

        class ReplyProvider:
            def __init__(self, workspace):
                self.workspace = workspace

            def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
                return {
                    "ok": True,
                    "status": "completed",
                    "reply": "continuation proposal",
                    "threadId": thread_id or "thr-continuation",
                    "turnId": "turn-continuation",
                    "modifiedFiles": [],
                }

        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: ReplyProvider(workspace)
        server._feishu_chat_app_text_send = lambda chat_id, text: (
            sends.append((chat_id, text))
            or {"ok": True, "status": "sent", "messageId": "om-sent-continuation"}
        )
        server._record_feishu_channel_event = lambda record: records.append(record) or {**record, "id": "channel-1"}
        try:
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "[Host-side VO operation succeeded]",
                "conversationId": "feishu-dm:continuation",
                "fromType": "chat",
                "fromDisplayName": "Feishu User",
                "sourceApp": "feishu",
                "sourceSurface": "feishu-dm",
                "sourceLabel": "Virtual Office",
                "sourceMessageId": "vo-host-side-read-test",
                "originalSourceMessageId": "om-original-user",
                "feishuChatId": "oc-continuation",
                "chatType": "p2p",
                "representativeAgentId": "codex-local",
                "threadId": "thr-continuation",
                "_hostSideVoSkillContinuation": True,
                "_hostSideVoReadContinuation": True,
            })
            assert result["ok"] is True
            assert sends == [("oc-continuation", "continuation proposal")]
            assert records
            assert records[0]["sourceMessageId"] == "vo-host-side-read-test"
            assert records[0]["continuationForSourceMessageId"] == "om-original-user"
            assert records[0]["sendResult"]["messageId"] == "om-sent-continuation"
        finally:
            server.STATUS_DIR = old_status_dir
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider
            server._feishu_chat_app_text_send = old_send
            server._record_feishu_channel_event = old_record


def test_feishu_group_codex_request_and_reply_are_never_visible_in_office():
    old_status_dir = server.STATUS_DIR
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        class ReplyProvider:
            def __init__(self, workspace):
                self.workspace = workspace

            def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
                return {
                    "ok": True,
                    "status": "completed",
                    "reply": "group reply from codex",
                    "threadId": "thr-group-history",
                    "turnId": "turn-group-history",
                    "modifiedFiles": [],
                }

        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: ReplyProvider(workspace)
        try:
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "group request to codex",
                "conversationId": "feishu-group:visibility-test",
                "fromType": "human",
                "fromDisplayName": "Group Member",
                "fromUserId": "ou_group_member",
                "sourceApp": "feishu",
                "sourceSurface": "feishu-group",
                "sourceLabel": "Feishu Group",
                "channel": "feishu",
                "sourceMessageId": "om_group_visibility",
                "idempotencyKey": "om_group_visibility",
                "feishuChatId": "oc_group_visibility",
                "representativeAgentId": "codex-local",
            })
            assert result["ok"] is True
            events = server._load_comm_history(
                limit=20,
                conversation_id="feishu-group:visibility-test",
                agent_id="codex-local",
            )
            messages = [event for event in events if event.get("type") == "message"]
            assert [event.get("direction") for event in messages] == ["request", "reply"]
            assert all(server._comm_is_feishu_group(event) for event in messages)
            assert all(event.get("visibleInOffice") is False for event in messages)
            request = type("Request", (), {
                "agent_id": "codex-local", "conversation_id": "feishu-group:visibility-test",
            })()
            assert all(not server._chat_history_comm_event_matches(request, event) for event in messages)
            server._append_comm_event({
                "type": "message",
                "direction": "reply",
                "conversationId": "feishu-group:legacy-visibility",
                "from": {"id": "codex-local", "providerKind": "codex"},
                "to": {"id": "user", "providerKind": "human", "sourceSurface": "feishu-group"},
                "text": "legacy group reply",
                "metadata": {"sourceApp": "feishu", "sourceSurface": "feishu-group", "chatType": "group"},
                "visibleInOffice": True,
            })
            assert server._repair_feishu_group_comm_visibility() == {"repaired": 1}
            repaired = server._load_comm_history(limit=20, conversation_id="feishu-group:legacy-visibility")
            assert len(repaired) == 1
            assert repaired[0]["visibleInOffice"] is False
            assert server._repair_feishu_group_comm_visibility() == {"repaired": 0}
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
            self.calls.append((thread_id, message))
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
            conversation_id = server.feishu_chat_channel.group_conversation_id("oc_recovery")
            server._record_feishu_channel_event({
                "event": "turn_completed", "sourceMessageId": "om_old",
                "conversationId": conversation_id, "feishuChatId": "oc_recovery",
                "chatType": "group", "sourceSurface": "feishu-group",
                "text": "old group question", "reply": "old group answer",
                "sender": {"name": "Alice", "openId": "ou_alice"},
            })
            server._record_feishu_channel_event({
                "event": "turn_completed", "sourceMessageId": "om_other",
                "conversationId": server.feishu_chat_channel.group_conversation_id("oc_other"),
                "feishuChatId": "oc_other", "chatType": "group", "sourceSurface": "feishu-group",
                "text": "other group secret", "reply": "other answer",
                "sender": {"name": "Mallory", "openId": "ou_mallory"},
            })
            server._set_codex_thread_id("codex-local", conversation_id, "thr-archived")
            result = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "current group question",
                "conversationId": conversation_id,
                "sourceApp": "feishu", "sourceSurface": "feishu-group",
                "sourceMessageId": "om_current", "feishuChatId": "oc_recovery",
                "fromType": "human", "fromDisplayName": "Carol", "fromUserId": "ou_carol",
            })
            assert result["ok"] is True
            assert result["reply"] == "fresh thread reply"
            assert result["threadId"] == "thr-fresh"
            assert result["recoveredFromArchivedThread"] == "thr-archived"
            assert [call[0] for call in provider.calls] == ["thr-archived", ""]
            recovery_prompt = provider.calls[1][1]
            assert "old group question" in recovery_prompt and "old group answer" in recovery_prompt
            assert recovery_prompt.count("current group question") == 1
            assert "other group secret" not in recovery_prompt
            assert server._get_codex_thread_id("codex-local", conversation_id) == "thr-fresh"
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
            assert reasoning["timelineItem"]["itemKind"] == "reasoning"
            assert reasoning["timelineItem"]["thinking"] == reasoning["text"]
            assert reasoning["timelineItem"]["status"] == "running"
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


def test_codex_approval_blocks_direct_project_store_write():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config

    class ApprovalProvider:
        def __init__(self):
            self.calls = []
            self.messages = []

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

        def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False, attachments=None):
            self.messages.append((message, conversation_id, thread_id, allow_interaction))
            return {"ok": True, "status": "completed", "reply": "continued", "threadId": thread_id, "turnId": "turn-continued"}

    provider = ApprovalProvider()
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    try:
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "approvalId": "approval-project-write",
            "choice": "approve",
            "sessionId": "thr-project",
            "approval": {
                "command": "PYTHONPATH=app python - <<'PY'\nfrom project_store import MarkdownProjectStore\nstore = MarkdownProjectStore('data')\nstore._write_project({'title':'Oops'})\nPY",
            },
        })

        assert responded["ok"] is True
        assert responded["status"] == "cancelled_by_policy"
        assert responded["code"] == "project_authoring_skill_required"
        assert responded["approvalChoice"] == "cancel"
        assert responded["approval"]["status"] == "cancelled"
        assert provider.calls[-1] == ("local", "approval-project-write", "cancel", "thr-project")
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider


def test_codex_approval_executes_approved_local_vo_api_curl():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_run = server.subprocess.run

    class ApprovalProvider:
        def __init__(self):
            self.calls = []
            self.messages = []

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

        def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False, attachments=None):
            self.messages.append((message, conversation_id, thread_id, allow_interaction))
            return {"ok": True, "status": "completed", "reply": "continued", "threadId": thread_id, "turnId": "turn-continued"}

    provider = ApprovalProvider()
    captured_runs = []

    class Completed:
        returncode = 0
        stdout = '{"ok":true,"projects":[]}'
        stderr = ""

    def fake_run(parts, cwd=None, env=None, text=None, capture_output=None, timeout=None, check=None):
        captured_runs.append((parts, cwd, env, text, capture_output, timeout, check))
        return Completed()

    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    server.subprocess.run = fake_run
    try:
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "approvalId": "approval-vo-api",
            "choice": "approve",
            "sessionId": "thr-vo-api",
            "approval": {
                "command": "/bin/zsh -lc 'curl -fsS --max-time 5 http://127.0.0.1:8090/api/projects'",
            },
        })

        assert responded["ok"] is True
        assert responded["status"] == "host_side_vo_curl_queued"
        assert responded["approvalSafety"] == "host_side_vo_curl"
        assert responded["policyScope"] == "vo_approved_local_curl"
        assert responded["hostSideRead"]["ok"] is True
        assert responded["hostSideRead"]["path"] == "/api/projects"
        assert responded["approvalChoice"] == "approve"
        assert provider.calls[-1] == ("local", "approval-vo-api", "cancel", "thr-vo-api")
        assert captured_runs
        assert captured_runs[-1][0][-1] == "http://127.0.0.1:8090/api/projects"
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider
        server.subprocess.run = old_run


def test_codex_approval_allows_host_side_vo_skill_read_only():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_handle_chat = server._handle_codex_chat

    class ApprovalProvider:
        def __init__(self):
            self.calls = []

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

    provider = ApprovalProvider()
    continuation_bodies = []
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    server._handle_codex_chat = lambda body: continuation_bodies.append(body) or {
        "ok": True,
        "status": "completed",
        "reply": "continued",
        "threadId": body.get("threadId") or "",
        "turnId": "turn-continued",
    }
    try:
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-vo-skill",
            "approvalId": "approval-vo-skill",
            "choice": "approve",
            "sessionId": "thr-vo-skill",
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceMessageId": "om_source_message",
            "feishuChatId": "oc_chat",
            "actorIds": {"openId": "ou_user", "unionId": "on_user"},
            "actorName": "Feishu User",
            "approval": {
                "command": "/bin/zsh -lc 'curl -fsS --max-time 5 http://127.0.0.1:8090/skills/index.md'",
            },
        })

        assert responded["ok"] is True
        assert responded["status"] == "host_side_vo_curl_queued"
        assert responded["approvalSafety"] == "host_side_vo_curl"
        assert responded["policyScope"] == "vo_approved_local_curl"
        assert responded["hostSideRead"]["ok"] is True
        assert responded["approvalChoice"] == "approve"
        assert provider.calls[-1] == ("local", "approval-vo-skill", "cancel", "thr-vo-skill")
        deadline = time.time() + 2
        while not continuation_bodies and time.time() < deadline:
            time.sleep(0.01)
        assert continuation_bodies
        body = continuation_bodies[-1]
        continuation = body["message"]
        assert "[Host-side VO operation succeeded]" in continuation
        assert "Do not retry the localhost curl command" in continuation
        assert "issue the exact ordinary local GET curl command" in continuation
        assert "no explicit escalated/sandbox_permissions parameter" in continuation
        assert "do not ask the user in prose" in continuation
        assert "vo-operating-guidelines" in continuation
        assert body["conversationId"] == "conv-vo-skill"
        assert body["threadId"] == "thr-vo-skill"
        assert body["fromType"] == "chat"
        assert body["sourceApp"] == "feishu"
        assert body["sourceSurface"] == "feishu-dm"
        assert body["feishuChatId"] == "oc_chat"
        assert body["chatType"] == "p2p"
        assert body["sourceActor"] == {"openId": "ou_user", "unionId": "on_user", "name": "Feishu User"}
        assert body["sourceMessageId"].startswith("vo-host-side-read-")
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider
        server._handle_codex_chat = old_handle_chat


def test_codex_approval_allows_host_side_vo_agents_roster_read_only():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_handle_chat = server._handle_codex_chat

    class ApprovalProvider:
        def __init__(self):
            self.calls = []

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

    provider = ApprovalProvider()
    continuation_bodies = []
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    server._handle_codex_chat = lambda body: continuation_bodies.append(body) or {
        "ok": True,
        "status": "completed",
        "reply": "continued",
        "threadId": body.get("threadId") or "",
        "turnId": "turn-continued",
    }
    try:
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-vo-agents",
            "approvalId": "approval-vo-agents",
            "choice": "approve",
            "sessionId": "thr-vo-agents",
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceMessageId": "om_source_message",
            "feishuChatId": "oc_chat",
            "actorIds": {"openId": "ou_user", "unionId": "on_user"},
            "actorName": "Feishu User",
            "approval": {
                "command": "/bin/zsh -lc 'curl -fsS --max-time 5 http://127.0.0.1:8090/api/agents'",
            },
        })

        assert responded["ok"] is True
        assert responded["status"] == "host_side_vo_curl_queued"
        assert responded["hostSideRead"]["ok"] is True
        assert responded["hostSideRead"]["path"] == "/api/agents"
        assert provider.calls[-1] == ("local", "approval-vo-agents", "cancel", "thr-vo-agents")
        deadline = time.time() + 2
        while not continuation_bodies and time.time() < deadline:
            time.sleep(0.01)
        assert continuation_bodies
        body = continuation_bodies[-1]
        assert body["conversationId"] == "conv-vo-agents"
        assert body["threadId"] == "thr-vo-agents"
        assert body["sourceActor"] == {"openId": "ou_user", "unionId": "on_user", "name": "Feishu User"}
        assert body["sourceMessageId"].startswith("vo-host-side-read-")
        assert "```json" in body["message"]
        assert '"codex-local"' in body["message"]
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider
        server._handle_codex_chat = old_handle_chat


def test_codex_approval_executes_approved_local_vo_project_authoring_curl_host_side():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_handle_chat = server._handle_codex_chat
    old_run = server.subprocess.run

    class ApprovalProvider:
        def __init__(self):
            self.calls = []

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

    class Completed:
        returncode = 0
        stdout = '{"ok":true,"project":{"id":"proj_1"}}'
        stderr = ""

    provider = ApprovalProvider()
    continuation_bodies = []
    run_calls = []
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    server._handle_codex_chat = lambda body: continuation_bodies.append(body) or {
        "ok": True,
        "status": "completed",
        "reply": "continued",
        "threadId": body.get("threadId") or "",
        "turnId": "turn-continued",
    }
    server.subprocess.run = lambda parts, **kwargs: run_calls.append((parts, kwargs)) or Completed()
    try:
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-vo-create",
            "approvalId": "approval-vo-create",
            "choice": "approve",
            "sessionId": "thr-vo-create",
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceMessageId": "om_source_message",
            "feishuChatId": "oc_chat",
            "actorIds": {"openId": "ou_user"},
            "actorName": "Feishu User",
            "approval": {
                "command": (
                    "/bin/zsh -lc 'curl -fsS --max-time 10 -X POST "
                    "http://127.0.0.1:8090/api/agent/project-authoring/projects "
                    "-H \"Content-Type: application/json\" "
                    "-H \"X-VO-Agent-Action: project-authoring\" "
                    "-d \"{\\\"confirmation\\\":{\\\"confirmed\\\":true,\\\"summaryText\\\":\\\"x\\\",\\\"summaryDigest\\\":\\\""
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\"}}\"'"
                ),
            },
        })

        assert responded["ok"] is True
        assert responded["status"] == "host_side_vo_curl_queued"
        assert responded["approvalSafety"] == "host_side_vo_curl"
        assert responded["hostSideRead"]["ok"] is True
        assert provider.calls[-1] == ("local", "approval-vo-create", "cancel", "thr-vo-create")
        assert run_calls
        assert run_calls[-1][0][0] == "curl"
        assert "http://127.0.0.1:8090/api/agent/project-authoring/projects" in run_calls[-1][0]
        deadline = time.time() + 2
        while not continuation_bodies and time.time() < deadline:
            time.sleep(0.01)
        assert continuation_bodies
        assert "[Host-side VO operation succeeded]" in continuation_bodies[-1]["message"]
        assert '"project"' in continuation_bodies[-1]["message"]
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider
        server._handle_codex_chat = old_handle_chat
        server.subprocess.run = old_run


def test_codex_approval_executes_wrapped_local_vo_project_authoring_shell_host_side():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_handle_chat = server._handle_codex_chat
    old_run = server.subprocess.run

    class ApprovalProvider:
        def __init__(self):
            self.calls = []

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

    class Completed:
        returncode = 0
        stdout = '{"ok":true,"project":{"id":"proj_wrapped"}}'
        stderr = ""

    provider = ApprovalProvider()
    continuation_bodies = []
    run_calls = []
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    server._handle_codex_chat = lambda body: continuation_bodies.append(body) or {
        "ok": True,
        "status": "completed",
        "reply": "continued",
        "threadId": body.get("threadId") or "",
        "turnId": "turn-continued",
    }
    server.subprocess.run = lambda parts, **kwargs: run_calls.append((parts, kwargs)) or Completed()
    try:
        command = (
            "/bin/zsh -lc \"node -e 'process.stdout.write(JSON.stringify({"
            "confirmation:{confirmed:true,summaryText:\\\"x\\\",summaryDigest:\\\""
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\"}}))' "
            "| curl -sS --max-time 5 -X POST 'http://127.0.0.1:8090/api/agent/project-authoring/projects' "
            "-H 'Content-Type: application/json' "
            "-H 'X-VO-Agent-Action: project-authoring' "
            "-H 'X-VO-Agent-Id: codex-local' "
            "-d @-\""
        )
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-vo-create-wrapped",
            "approvalId": "approval-vo-create-wrapped",
            "choice": "approve",
            "sessionId": "thr-vo-create-wrapped",
            "sourceApp": "feishu",
            "sourceSurface": "feishu-dm",
            "sourceMessageId": "om_source_message",
            "feishuChatId": "oc_chat",
            "actorIds": {"openId": "ou_user"},
            "actorName": "Feishu User",
            "approval": {"command": command},
        })

        assert responded["ok"] is True
        assert responded["status"] == "host_side_vo_curl_queued"
        assert responded["approvalSafety"] == "host_side_vo_shell"
        assert responded["hostSideRead"]["ok"] is True
        assert provider.calls[-1] == ("local", "approval-vo-create-wrapped", "cancel", "thr-vo-create-wrapped")
        assert run_calls
        assert run_calls[-1][0][0].endswith("zsh")
        assert "/api/agent/project-authoring/projects" in run_calls[-1][0][2]
        deadline = time.time() + 2
        while not continuation_bodies and time.time() < deadline:
            time.sleep(0.01)
        assert continuation_bodies
        assert "proj_wrapped" in continuation_bodies[-1]["message"]
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider
        server._handle_codex_chat = old_handle_chat
        server.subprocess.run = old_run


def test_codex_approval_respond_hydrates_pending_command_before_host_side_proxy():
    old_roster = server.get_roster
    old_provider = server._codex_provider_from_config
    old_handle_chat = server._handle_codex_chat

    class ApprovalProvider:
        def __init__(self):
            self.calls = []

        def pending_approval(self, profile, session_id=None):
            return {
                "ok": True,
                "pending": {
                    "id": "approval-hydrate",
                    "command": "/bin/zsh -lc 'curl -sS --max-time 3 http://127.0.0.1:8090/skills/index.md'",
                    "threadId": session_id or "thr-hydrate",
                },
            }

        def respond_approval(self, profile, approval_id, choice="cancel", session_id=None):
            self.calls.append((profile, approval_id, choice, session_id))
            return {"ok": True, "status": "submitted", "approvalId": approval_id, "sessionId": session_id}

    provider = ApprovalProvider()
    continuation_bodies = []
    server.get_roster = lambda: [AGENT]
    server._codex_provider_from_config = lambda: provider
    server._handle_codex_chat = lambda body: continuation_bodies.append(body) or {
        "ok": True,
        "status": "completed",
        "reply": "continued",
        "threadId": body.get("threadId") or "",
        "turnId": "turn-continued",
    }
    try:
        responded = server._handle_codex_approval_respond({
            "agentId": "codex-local",
            "conversationId": "conv-hydrate",
            "approvalId": "approval-hydrate",
            "choice": "approve",
            "sessionId": "thr-hydrate",
        })

        assert responded["ok"] is True
        assert responded["status"] == "host_side_vo_curl_queued"
        assert responded["approvalSafety"] == "host_side_vo_curl"
        assert provider.calls[-1] == ("local", "approval-hydrate", "cancel", "thr-hydrate")
    finally:
        server.get_roster = old_roster
        server._codex_provider_from_config = old_provider
        server._handle_codex_chat = old_handle_chat


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


def test_pending_codex_approval_has_presence_priority_until_resolution():
    agent_id = "codex-presence-priority"
    conversation_id = "conv-presence-priority"
    key = (agent_id, conversation_id)
    previous = server._CODEX_ACTIVE_OPERATIONS.get(key)
    server._CODEX_ACTIVE_OPERATIONS[key] = {
        "agentId": agent_id,
        "conversationId": conversation_id,
        "status": "running",
        "threadId": "thread-priority",
    }
    try:
        server._update_codex_active_from_record(agent_id, conversation_id, {
            "type": "interaction", "status": "pending", "interactionId": "interaction-1",
            "threadId": "thread-priority", "turnId": "turn-priority",
        })
        active = server._CODEX_ACTIVE_OPERATIONS[key]
        assert active["status"] == "pending"
        assert active["pending"]["interactionId"] == "interaction-1"

        server._update_codex_active_from_record(agent_id, conversation_id, {
            "type": "activity", "status": "completed", "name": "tool.completed",
            "threadId": "thread-priority", "turnId": "turn-priority",
        })
        assert active["status"] == "pending"
        assert active["pending"] is not None

        assert server._mark_codex_active_approval_resolving(agent_id, conversation_id, "approval-native") is True
        server._update_codex_active_from_record(agent_id, conversation_id, {
            "type": "activity", "status": "idle", "threadId": "thread-priority",
        })
        assert active["status"] == "resolving"

        server._update_codex_active_from_record(agent_id, conversation_id, {
            "type": "interaction", "status": "resolved", "interactionId": "interaction-1",
            "threadId": "thread-priority", "turnId": "turn-priority",
        })
        assert active["status"] == "resolved"
        assert active["pending"] is None
    finally:
        if previous is None:
            server._CODEX_ACTIVE_OPERATIONS.pop(key, None)
        else:
            server._CODEX_ACTIVE_OPERATIONS[key] = previous


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
