from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-archive-coordinator-test-")
)

import server  # noqa: E402
from services.archive_manager_work_coordinator import (  # noqa: E402
    ArchiveManagerWorkCoordinator,
)


OPERATIONS = {
    "manual": (
        "_archive_manager_manual_maintain_uncoordinated",
        lambda: server._handle_archive_manager_manual_maintain("project-1"),
    ),
    "refine": (
        "_archive_manager_ai_refine_uncoordinated",
        lambda: server._handle_archive_manager_ai_refine("project-1", {}),
    ),
    "audit": (
        "_archive_room_audit_count_uncoordinated",
        server._handle_archive_room_audit_count,
    ),
}


@pytest.mark.parametrize(
    ("holder_name", "contender_name"),
    [
        ("manual", "refine"),
        ("manual", "audit"),
        ("refine", "manual"),
        ("refine", "audit"),
        ("audit", "manual"),
        ("audit", "refine"),
    ],
)
def test_archive_operations_reject_every_later_pair_without_queueing(
    monkeypatch, holder_name, contender_name
):
    coordinator = ArchiveManagerWorkCoordinator()
    monkeypatch.setattr(server, "ARCHIVE_MANAGER_WORK_COORDINATOR", coordinator)
    monkeypatch.setattr(
        server, "_archive_manager_finalize_coordinated_work", lambda _error: None
    )
    started = threading.Event()
    release = threading.Event()
    called: list[str] = []

    for name, (implementation_name, _invoke) in OPERATIONS.items():
        def operation(*_args, operation_name=name, **_kwargs):
            called.append(operation_name)
            if operation_name == holder_name:
                started.set()
                assert release.wait(timeout=2)
            return {"ok": True, "operation": operation_name}

        monkeypatch.setattr(server, implementation_name, operation)

    first_result: list[dict] = []
    thread = threading.Thread(
        target=lambda: first_result.append(OPERATIONS[holder_name][1]())
    )
    thread.start()
    assert started.wait(timeout=1)

    contender = OPERATIONS[contender_name][1]()

    assert contender["ok"] is False
    assert contender["status"] == "busy"
    assert contender["code"] == "archive_manager_busy"
    assert contender["_status"] == 409
    assert called == [holder_name]
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert first_result == [{"ok": True, "operation": holder_name}]
    assert coordinator.holder() is None


def test_handler_exception_releases_lease_and_finalizes_manager(monkeypatch):
    coordinator = ArchiveManagerWorkCoordinator()
    finalized: list[BaseException | None] = []
    monkeypatch.setattr(server, "ARCHIVE_MANAGER_WORK_COORDINATOR", coordinator)
    monkeypatch.setattr(
        server,
        "_archive_manager_manual_maintain_uncoordinated",
        lambda _project_id: (_ for _ in ()).throw(RuntimeError("broken archive")),
    )
    monkeypatch.setattr(
        server,
        "_archive_manager_finalize_coordinated_work",
        finalized.append,
    )

    with pytest.raises(RuntimeError, match="broken archive"):
        server._handle_archive_manager_manual_maintain("project-1")

    assert len(finalized) == 1
    assert str(finalized[0]) == "broken archive"
    assert coordinator.holder() is None


def test_archive_manager_projection_mirrors_current_lease(monkeypatch):
    coordinator = ArchiveManagerWorkCoordinator()
    monkeypatch.setattr(server, "ARCHIVE_MANAGER_WORK_COORDINATOR", coordinator)
    monkeypatch.setattr(
        server,
        "_archive_manager_shared_adapter",
        lambda: type(
            "Adapter",
            (),
            {
                "public_state": lambda _self, ensure=True: {
                    "status": "working",
                    "label": "处理中",
                    "paused": False,
                }
            },
        )(),
    )

    with coordinator.lease(
        "archive-count-audit",
        label="检查档案数目",
        metadata={"source": "archive-room"},
    ):
        projected = server._archive_manager_public_state(ensure=False)

    assert projected["status"] == "working"
    assert projected["label"] == "检查档案数目"
    assert projected["activeWork"]["kind"] == "archive-count-audit"
    assert server._archive_manager_public_state(ensure=False)["activeWork"] is None


@pytest.mark.parametrize(
    ("paused", "error", "expected_status", "expected_label"),
    [
        (False, None, "idle", "已接入"),
        (True, None, "paused", "已暂停"),
        (False, RuntimeError("failed"), "error", "档案管理员工作失败"),
    ],
)
def test_terminal_state_reconciliation_clears_stale_working_presentation(
    monkeypatch, paused, error, expected_status, expected_label
):
    state = {"status": "working", "label": "处理中", "paused": paused}
    saved: list[dict] = []
    monkeypatch.setattr(server, "_archive_manager_load_state", lambda: dict(state))
    monkeypatch.setattr(
        server, "_archive_manager_save_state", lambda value: saved.append(dict(value))
    )

    server._archive_manager_finalize_coordinated_work(error)

    assert saved[-1]["status"] == expected_status
    assert saved[-1]["label"] == expected_label
    if error is not None:
        assert saved[-1]["lastError"] == "failed"
