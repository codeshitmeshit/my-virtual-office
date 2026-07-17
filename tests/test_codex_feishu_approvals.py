import json
import os
import sys
import threading
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.feishu_notifications import build_feishu_card  # noqa: E402
from app.services.codex_feishu_approvals import (  # noqa: E402
    BoundedApprovalDeliveryExecutor,
    CodexFeishuApprovalCoordinator,
    CodexFeishuApprovalRouteStore,
)


def route(route_id="route-1", approval_id="approval-1"):
    return {
        "routeId": route_id,
        "approvalId": approval_id,
        "agentId": "codex-local",
        "conversationId": "feishu-dm:user-1:chat-1",
        "threadId": "thread-1",
        "turnId": "turn-1",
        "actorIds": {"openId": "ou_origin", "unionId": "on_origin"},
    }


def test_register_delivery_and_replay_survive_reload(tmp_path):
    path = tmp_path / "routes.json"
    tokens = iter(("claim-one",))
    store = CodexFeishuApprovalRouteStore(str(path), token_factory=tokens.__next__)

    registered, created = store.register(route())
    duplicate, duplicate_created = store.register(route())
    assert created is True
    assert duplicate_created is False
    assert duplicate["routeId"] == registered["routeId"]

    store.begin_delivery("route-1")
    delivered = store.record_delivery("route-1", {
        "attemptId": "primary-1",
        "application": "notification",
        "status": "sent",
        "ok": True,
        "messageId": "om_primary",
        "appSecret": "must-not-persist",
    })
    assert delivered["status"] == "delivered"
    assert delivered["deliveries"][0]["messageId"] == "om_primary"
    assert "appSecret" not in json.dumps(delivered)

    claim = store.claim("route-1", "approve", {"openId": "ou_origin"})
    assert claim.claimed is True
    committed = store.commit("route-1", claim.token, {"ok": True, "status": "approved"})
    assert committed.claimed is True

    reloaded = CodexFeishuApprovalRouteStore(str(path))
    replay = reloaded.claim("route-1", "cancel", {"unionId": "on_origin"})
    assert replay.replay is True
    assert replay.outcome == {"ok": True, "status": "approved"}
    assert reloaded.get("route-1")["decision"] == "approve"


def test_concurrent_claim_has_one_winner_and_commit_token_is_fenced(tmp_path):
    path = tmp_path / "routes.json"
    store = CodexFeishuApprovalRouteStore(str(path))
    store.register(route())
    barrier = threading.Barrier(8)
    claims = []
    lock = threading.Lock()

    def claim_once():
        barrier.wait()
        result = store.claim("route-1", "approve", {"openId": "ou_origin"})
        with lock:
            claims.append(result)

    threads = [threading.Thread(target=claim_once) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [claim for claim in claims if claim.claimed]
    assert len(winners) == 1
    assert sum(1 for claim in claims if claim.busy) == 7
    wrong = store.commit("route-1", "wrong-token", {"ok": True})
    assert wrong.claimed is False
    assert wrong.busy is True
    assert store.commit("route-1", winners[0].token, {"ok": True}).claimed is True


def test_actor_mismatch_terminal_failure_and_capacity_are_safe(tmp_path):
    path = tmp_path / "routes.json"
    store = CodexFeishuApprovalRouteStore(str(path), max_records=1)
    store.register(route())
    unauthorized = store.claim("route-1", "approve", {"openId": "ou_other"})
    assert unauthorized.unauthorized is True
    failed = store.fail("route-1", {"ok": False, "status": "delivery_failed"})
    assert failed["status"] == "failed"
    assert store.claim("route-1", "approve", {"openId": "ou_origin"}).stale is True

    second, created = store.register(route("route-2", "approval-2"))
    assert created is True
    assert second["routeId"] == "route-2"
    assert store.get("route-1") is None
    try:
        store.register(route("route-3", "approval-3"))
    except OverflowError:
        pass
    else:
        raise AssertionError("live records must not be evicted when capacity is full")


def test_ttl_expiry_and_startup_reconciliation_never_retry_uncertain_claim(tmp_path):
    now = [1_000]
    path = tmp_path / "routes.json"
    store = CodexFeishuApprovalRouteStore(
        str(path),
        retention_ms=100,
        clock_ms=lambda: now[0],
        token_factory=lambda: "uncertain-token",
    )
    store.register(route())
    claim = store.claim("route-1", "approve", {"openId": "ou_origin"})
    assert claim.claimed is True

    reloaded = CodexFeishuApprovalRouteStore(str(path), retention_ms=100, clock_ms=lambda: now[0])
    recovered = reloaded.get("route-1")
    assert recovered["status"] == "expired"
    assert recovered["outcome"]["status"] == "resolved_unknown"
    assert reloaded.claim("route-1", "approve", {"openId": "ou_origin"}).stale is True

    reloaded.register(route("route-2", "approval-2"))
    now[0] += 101
    assert reloaded.get("route-2")["status"] == "expired"
    now[0] += 100
    assert reloaded.get("route-2") is None


def test_invalid_route_identity_and_symlink_store_fail_closed(tmp_path):
    store = CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json"))
    for invalid in ({"routeId": "route-only"}, {"approvalId": "approval-only"}):
        try:
            store.register(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid route identity must fail")

    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    try:
        CodexFeishuApprovalRouteStore(str(link))
    except OSError:
        pass
    else:
        raise AssertionError("symlink stores must fail closed")


def feishu_context(**overrides):
    value = {
        "sourceApp": "feishu",
        "sourceSurface": "feishu-dm",
        "sourceMessageId": "om_source",
        "feishuChatId": "oc_origin",
        "sourceActor": {
            "openId": "ou_origin",
            "userId": "u_origin",
            "unionId": "on_origin",
            "name": "Origin User",
        },
        "agentId": "codex-local",
        "conversationId": "feishu-dm:user-1:chat-1",
    }
    value.update(overrides)
    return value


def approval(kind="command", **overrides):
    value = {
        "approval_id": f"approval-{kind}",
        "kind": kind,
        "command": "printf api_key=super-secret /Users/demo/private.txt",
        "threadId": "thread-1",
        "turnId": "turn-1",
        "profile": "local",
    }
    value.update(overrides)
    return value


class FakeNotificationSender:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, intent, **kwargs):
        self.calls.append({"intent": intent, **kwargs})
        return self.results.pop(0)


def coordinator(tmp_path, sender):
    return CodexFeishuApprovalCoordinator(
        CodexFeishuApprovalRouteStore(str(tmp_path / "routes.json")),
        send_notification=sender,
        status_dir=str(tmp_path),
        attempt_id_factory=iter((f"attempt-{index}" for index in range(20))).__next__,
    )


def test_intents_cover_only_eligible_kinds_and_expose_opaque_actions(tmp_path):
    sender = FakeNotificationSender([])
    service = coordinator(tmp_path, sender)
    for kind in ("command", "file_change", "permissions"):
        record, created = service.register(approval(kind), feishu_context())
        assert created is True
        intent = record["intent"]
        assert intent["type"] == "application_form"
        assert intent["state"] == "pending"
        assert [item["value"]["action"] for item in intent["actions"]] == ["codex_approval_once", "codex_approval_cancel"]
        assert all(set(item["value"]) == {"action", "route_id", "version"} for item in intent["actions"])
        assert record["approvalId"] not in json.dumps(intent, ensure_ascii=False)
        assert "super-secret" not in json.dumps(intent, ensure_ascii=False)
        build_feishu_card(intent)
    try:
        service.register(approval("question"), feishu_context())
    except ValueError:
        pass
    else:
        raise AssertionError("non-security interactions must not become approval cards")


def test_notification_application_uses_origin_union_id_and_fixed_recipient_is_ignored(tmp_path):
    sender = FakeNotificationSender([{"ok": True, "status": "sent", "channel": "app", "messageId": "om_primary"}])
    service = coordinator(tmp_path, sender)
    record, _ = service.register(approval(), feishu_context())
    result = service.deliver(
        record["routeId"],
        notification_config={
            "appId": "notification-app",
            "appSecret": "notification-secret",
            "receiveIdType": "chat_id",
            "receiveId": "oc_fixed_must_not_be_used",
        },
        chat_config={"appId": "chat-app", "appSecret": "chat-secret"},
    )
    assert result["ok"] is True
    assert result["application"] == "notification"
    assert len(sender.calls) == 1
    assert sender.calls[0]["app_config"]["receiveIdType"] == "union_id"
    assert sender.calls[0]["app_config"]["receiveId"] == "on_origin"
    assert "oc_fixed_must_not_be_used" not in json.dumps(sender.calls[0])


def test_missing_or_unroutable_notification_application_falls_back_to_origin_chat(tmp_path):
    for notification_config, source_actor in (
        ({}, {"openId": "ou_origin"}),
        ({"appId": "notification-app", "appSecret": "secret"}, {"openId": "ou_origin"}),
    ):
        case = "missing" if not notification_config else "unroutable"
        sender = FakeNotificationSender([{"ok": True, "status": "sent", "channel": "app", "messageId": f"om_chat_{case}"}])
        service = coordinator(tmp_path / case, sender)
        record, _ = service.register(approval(), feishu_context(sourceActor=source_actor))
        result = service.deliver(
            record["routeId"],
            notification_config=notification_config,
            chat_config={"appId": "chat-app", "appSecret": "chat-secret"},
        )
        assert result["ok"] is True
        assert result["application"] == "chat"
        assert sender.calls[-1]["app_config"]["receiveIdType"] == "chat_id"
        assert sender.calls[-1]["app_config"]["receiveId"] == "oc_origin"


def test_primary_failure_and_ambiguous_result_fall_back_with_same_route(tmp_path):
    for primary_status in ("feishu_error", "network_error"):
        sender = FakeNotificationSender([
            {"ok": False, "status": primary_status, "channel": "app", "code": 230001},
            {"ok": True, "status": "sent", "channel": "app", "messageId": f"om_fallback_{primary_status}"},
        ])
        service = coordinator(tmp_path / primary_status, sender)
        record, _ = service.register(approval(), feishu_context())
        result = service.deliver(
            record["routeId"],
            notification_config={"appId": "notification-app", "appSecret": "notification-secret"},
            chat_config={"appId": "chat-app", "appSecret": "chat-secret"},
        )
        assert result["ok"] is True
        assert result["application"] == "chat"
        assert len(sender.calls) == 2
        assert sender.calls[0]["intent"]["id"] == sender.calls[1]["intent"]["id"] == record["routeId"]
        assert result["attempts"][0]["ambiguous"] is (primary_status == "network_error")


def test_skipped_or_failed_chat_delivery_is_undeliverable(tmp_path):
    for chat_result in (
        {"ok": True, "status": "skipped_disabled"},
        {"ok": False, "status": "network_error"},
    ):
        sender = FakeNotificationSender([chat_result])
        service = coordinator(tmp_path / str(chat_result["status"]), sender)
        record, _ = service.register(approval(), feishu_context())
        result = service.deliver(
            record["routeId"],
            notification_config={},
            chat_config={"appId": "chat-app", "appSecret": "chat-secret"},
        )
        assert result["ok"] is False
        assert result["status"] == "undeliverable"
        assert service.store.get(record["routeId"])["status"] == "delivering"


def test_bounded_delivery_executor_enforces_saturation_deadline_and_one_failure():
    executor = BoundedApprovalDeliveryExecutor(max_workers=1, max_queue=0, deadline_sec=0.05)
    release = threading.Event()
    failures = []
    failed = threading.Event()

    def slow_delivery():
        release.wait(1)
        return {"ok": False, "status": "undeliverable"}

    def on_failure(reason, result):
        failures.append((reason, result))
        failed.set()

    assert executor.submit(slow_delivery, on_failure) is True
    assert executor.submit(lambda: {"ok": True}, on_failure) is False
    assert failed.wait(1)
    assert failures == [("deadline", None)]
    release.set()
    time.sleep(0.05)
    assert len(failures) == 1
    executor.shutdown(wait=True)
