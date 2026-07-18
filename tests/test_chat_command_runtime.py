import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.chat_command_runtime import CallbackCommandAuditPort, CommandFeatureFlags, CommandMetrics, ScopedCommandReservations
from services.chat_commands import ChatCommand, CommandRequest, CommandResult, CommandScope


def scope(conversation="c", surface="virtual-office", provider="codex"):
    return CommandScope.create(provider, "agent", "profile", conversation, surface)


def request(surface="virtual-office"):
    return CommandRequest.create(ChatCommand.NEW, scope(surface=surface), "idem", "source")


def test_flags_require_global_and_feishu_gates():
    assert CommandFeatureFlags.from_values("1", "0").allows("virtual-office") is True
    assert CommandFeatureFlags.from_values("1", "0").allows("feishu-dm") is False
    assert CommandFeatureFlags.from_values("0", "1").allows("feishu-group") is False


def test_reservations_are_nonblocking_isolated_and_bounded():
    reservations = ScopedCommandReservations(capacity=16)
    first = scope("one")
    assert reservations.try_acquire(first) is True
    assert reservations.try_acquire(first) is False
    assert reservations.try_acquire(scope("two")) is True
    reservations.release(first)
    reservations.release(scope("two"))
    for index in range(30):
        item = scope(f"scope-{index}")
        assert reservations.try_acquire(item)
        reservations.release(item)
    assert reservations.diagnostics()["scopes"] <= 16


def test_callback_audit_writes_bounded_nonsecret_started_and_terminal_rows():
    rows = []
    metrics = CommandMetrics()
    audit = CallbackCommandAuditPort(lambda _request: None, rows.append, metrics)
    current = request("feishu-group")
    audit.record_started(current, "operation", 10)
    result = CommandResult(True, "success", ChatCommand.NEW, "c", "x" * 3000, True, "operation", duration_ms=5)
    audit.record_terminal(current, result)
    assert [row["event"] for row in rows] == ["command_started", "command_completed"]
    assert len(rows[1]["reply"]) == 2000
    assert all("context" not in row and "secret" not in row for row in rows)
    assert {row["status"] for row in metrics.snapshot()} == {"recognized", "success"}


def test_started_lookup_is_reused_for_indeterminate_without_writes():
    rows = []
    audit = CallbackCommandAuditPort(lambda _request: {"state": "started", "operationId": "old"}, rows.append)
    stored = audit.lookup(request())
    assert stored["state"] == "started"
    assert rows == []


def test_metrics_collapse_unbounded_labels():
    metrics = CommandMetrics()
    metrics.increment("tenant-123", "future", "/delete-all", "weird")
    assert metrics.snapshot() == [{"surface": "unknown", "provider": "other", "command": "other", "status": "failed", "count": 1}]
