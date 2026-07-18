from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.chat_commands import (
    ChatCommand,
    ChatCommandService,
    CommandRequest,
    CommandResult,
    CommandScope,
    parse_chat_command,
)


class FakeProvider:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome or {"ok": True, "status": "success"}
        self.error = error
        self.calls = []

    def execute(self, command, scope):
        self.calls.append((command, scope))
        if self.error:
            raise self.error
        return self.outcome


class FakeReservation:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.released = []

    def try_acquire(self, scope):
        return self.acquired

    def release(self, scope):
        self.released.append(scope)


class FakeAudit:
    def __init__(self, stored=None, fail_lookup=False, fail_started=False, fail_terminal=False):
        self.stored = stored
        self.fail_lookup = fail_lookup
        self.fail_started = fail_started
        self.fail_terminal = fail_terminal
        self.started = []
        self.terminal = []

    def lookup(self, request):
        if self.fail_lookup:
            raise OSError("lookup failed")
        return self.stored

    def record_started(self, request, operation_id, started_at_ms):
        if self.fail_started:
            raise OSError("start failed")
        self.started.append((request, operation_id, started_at_ms))

    def record_terminal(self, request, result):
        if self.fail_terminal:
            raise OSError("terminal failed")
        self.terminal.append((request, result))


class FixedIds:
    def new_id(self):
        return "operation-1"


class SequenceClock:
    def __init__(self):
        self.values = iter((1_000, 1_025))

    def now_ms(self):
        return next(self.values)


def request(command=ChatCommand.NEW, surface="virtual-office"):
    return CommandRequest.create(
        command,
        CommandScope.create("Codex", "codex-local", "local", "conversation-a", surface),
        "idem-1",
        "om-1" if surface.startswith("feishu-") else "",
    )


def service(provider=None, reservation=None, audit=None):
    provider = provider or FakeProvider()
    reservation = reservation or FakeReservation()
    audit = audit or FakeAudit()
    return ChatCommandService(provider, reservation, audit, FixedIds(), SequenceClock()), provider, reservation, audit


@pytest.mark.parametrize("text, expected", [
    ("/new", ChatCommand.NEW),
    ("  /compact\n", ChatCommand.COMPACT),
    ("/New", None),
    ("/new now", None),
    ("/help", None),
    ("", None),
])
def test_parser_recognizes_only_exact_commands(text, expected):
    assert parse_chat_command(text) is expected


def test_parser_rejects_command_text_with_attachments():
    assert parse_chat_command("/new", [{"name": "context.txt"}]) is None


def test_scope_normalizes_aliases_and_bounds_values():
    scope = CommandScope.create("Claude", "a" * 300, "main", "c" * 400, "FEISHU-DM")
    assert scope.provider_kind == "claude-code"
    assert len(scope.agent_id) == 160
    assert len(scope.conversation_id) == 240
    assert scope.surface == "feishu-dm"
    with pytest.raises(ValueError):
        CommandScope.create("codex", "agent", "profile", "conversation", "email")


def test_new_success_returns_bounded_next_identity_and_records_terminal():
    subject, provider, reservation, audit = service(FakeProvider({
        "ok": True,
        "status": "created",
        "nextConversationId": "next-conversation",
    }))
    result = subject.execute(request())

    assert result == CommandResult(
        True,
        "success",
        ChatCommand.NEW,
        "conversation-a",
        "New conversation created",
        changed=True,
        operation_id="operation-1",
        next_conversation_id="next-conversation",
        duration_ms=25,
    )
    assert len(provider.calls) == len(audit.started) == len(audit.terminal) == 1
    assert reservation.released == [request().scope]


@pytest.mark.parametrize("status, ok", [
    ("no_op", True),
    ("unsupported", False),
    ("failed", False),
    ("stale", False),
    ("indeterminate", False),
])
def test_provider_outcomes_are_normalized(status, ok):
    subject, _provider, _reservation, audit = service(FakeProvider({"ok": ok, "status": status}))
    result = subject.execute(request(ChatCommand.COMPACT))
    assert result.status == status
    assert result.ok is ok
    assert result.changed is (ok and status == "success")
    assert audit.terminal[-1][1] == result


def test_busy_does_not_start_audit_or_provider_work():
    subject, provider, reservation, audit = service(reservation=FakeReservation(False))
    result = subject.execute(request())
    assert result.status == "busy" and result.ok is False
    assert provider.calls == audit.started == audit.terminal == []
    assert reservation.released == []


def test_duplicate_terminal_result_is_reused_without_provider_work():
    stored = {
        "state": "terminal",
        "ok": True,
        "status": "success",
        "reply": "already done",
        "changed": True,
        "operationId": "old-operation",
    }
    subject, provider, reservation, _audit = service(audit=FakeAudit(stored=stored))
    result = subject.execute(request())
    assert result.status == "success" and result.duplicate is True and result.reply == "already done"
    assert provider.calls == [] and reservation.released == []


def test_duplicate_started_record_is_indeterminate_and_not_repeated():
    subject, provider, _reservation, _audit = service(audit=FakeAudit(stored={
        "state": "started", "operationId": "uncertain-operation"
    }))
    result = subject.execute(request(ChatCommand.COMPACT, "feishu-group"))
    assert result.status == "indeterminate" and result.duplicate is True
    assert result.operation_id == "uncertain-operation"
    assert provider.calls == []


def test_provider_exception_is_redacted_and_recorded_as_failure():
    subject, _provider, reservation, audit = service(FakeProvider(error=RuntimeError("secret provider detail")))
    result = subject.execute(request())
    assert result.status == "failed"
    assert result.reply == "Provider command failed"
    assert "secret" not in result.to_dict()["reply"]
    assert audit.terminal[-1][1] == result
    assert len(reservation.released) == 1


def test_audit_start_failure_prevents_provider_side_effect():
    subject, provider, reservation, _audit = service(audit=FakeAudit(fail_started=True))
    result = subject.execute(request())
    assert result.status == "failed" and result.reply == "Command audit start failed"
    assert provider.calls == []
    assert len(reservation.released) == 1


def test_terminal_audit_failure_returns_indeterminate_after_side_effect():
    subject, provider, reservation, _audit = service(
        FakeProvider({"ok": True, "status": "success", "changed": True}),
        audit=FakeAudit(fail_terminal=True),
    )
    result = subject.execute(request(ChatCommand.COMPACT, "feishu-dm"))
    assert result.status == "indeterminate" and result.changed is True
    assert len(provider.calls) == len(reservation.released) == 1


def test_audit_lookup_failure_fails_closed_before_reservation():
    subject, provider, reservation, _audit = service(audit=FakeAudit(fail_lookup=True))
    result = subject.execute(request())
    assert result.status == "failed" and result.reply == "Command audit lookup failed"
    assert provider.calls == [] and reservation.released == []
