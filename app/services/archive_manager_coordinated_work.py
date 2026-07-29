"""Thin execution adapter for archive-manager operations."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from services.archive_manager_work_coordinator import (
    ArchiveManagerBusyError,
    ArchiveManagerWorkCoordinator,
)


def busy_result(exc: ArchiveManagerBusyError) -> dict[str, Any]:
    """Return the stable HTTP-compatible rejection for non-queued work."""

    return {
        "ok": False,
        "status": "busy",
        "code": exc.code,
        "error": "Archive manager is busy",
        "holder": exc.holder,
        "_status": 409,
    }


def execute(
    coordinator: ArchiveManagerWorkCoordinator,
    *,
    kind: str,
    label: str,
    metadata: Mapping[str, Any] | None,
    operation: Callable[[], dict[str, Any]],
    finalize: Callable[[BaseException | None], None],
) -> dict[str, Any]:
    """Run one operation under an immediate, single-holder lease."""

    try:
        lease = coordinator.acquire(kind, label=label, metadata=metadata)
    except ArchiveManagerBusyError as exc:
        return busy_result(exc)

    failure: BaseException | None = None
    try:
        return operation()
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            finalize(failure)
        finally:
            coordinator.release(lease)
