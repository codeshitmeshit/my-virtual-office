import json
import os
import sys
import threading


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.codex_feishu_approvals import CodexFeishuApprovalRouteStore  # noqa: E402


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
