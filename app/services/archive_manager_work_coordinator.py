"""Process-wide, non-queued coordination for archive-manager work."""

from __future__ import annotations

import copy
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, TypeVar


class ArchiveManagerCoordinatorError(RuntimeError):
    """Base error for archive-manager work coordination."""


class ArchiveManagerBusyError(ArchiveManagerCoordinatorError):
    """Raised when a later operation attempts to acquire the active manager."""

    code = "archive_manager_busy"

    def __init__(self, holder: Mapping[str, Any]):
        self.holder = copy.deepcopy(dict(holder))
        super().__init__(
            f"archive manager is busy with {self.holder.get('kind') or 'work'}"
        )


class InvalidArchiveManagerLease(ArchiveManagerCoordinatorError):
    """Raised when a lease from another coordinator is released."""


@dataclass(frozen=True)
class ArchiveManagerWorkLease:
    """Opaque ownership proof returned by the coordinator."""

    _coordinator_id: str
    _token: str
    kind: str
    label: str
    started_at: str
    metadata: Mapping[str, Any]

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "startedAt": self.started_at,
            "metadata": copy.deepcopy(dict(self.metadata)),
        }


_Record = TypeVar("_Record")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ArchiveManagerCoordinatorError(f"{field} is required")
    if len(text) > limit or any(ord(char) < 32 for char in text):
        raise ArchiveManagerCoordinatorError(f"{field} is invalid")
    return text


class ArchiveManagerWorkCoordinator:
    """Allow one archive-manager operation at a time without queueing."""

    def __init__(
        self,
        *,
        clock: Callable[[], str] = _utc_now,
        token_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        coordinator_id: str | None = None,
    ):
        self._clock = clock
        self._token_factory = token_factory
        self._coordinator_id = coordinator_id or uuid.uuid4().hex
        self._lock = threading.RLock()
        self._holder: ArchiveManagerWorkLease | None = None

    def holder(self) -> dict[str, Any] | None:
        """Return detached metadata for the current holder."""

        with self._lock:
            return self._holder.snapshot() if self._holder else None

    def acquire(
        self,
        kind: object,
        *,
        label: object | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArchiveManagerWorkLease:
        """Acquire immediately or reject; callers are never queued."""

        normalized_kind = _normalize_text(kind, field="kind", limit=80)
        normalized_label = (
            _normalize_text(label, field="label", limit=160)
            if label is not None
            else normalized_kind
        )
        try:
            detached_metadata = copy.deepcopy(dict(metadata or {}))
        except (TypeError, ValueError) as exc:
            raise ArchiveManagerCoordinatorError("metadata is invalid") from exc

        with self._lock:
            if self._holder is not None:
                raise ArchiveManagerBusyError(self._holder.snapshot())
            lease = ArchiveManagerWorkLease(
                _coordinator_id=self._coordinator_id,
                _token=str(self._token_factory()),
                kind=normalized_kind,
                label=normalized_label,
                started_at=str(self._clock()),
                metadata=MappingProxyType(detached_metadata),
            )
            self._holder = lease
            return lease

    def release(self, lease: ArchiveManagerWorkLease) -> bool:
        """Release exactly the matching live lease; repeated release is a no-op."""

        if not isinstance(lease, ArchiveManagerWorkLease):
            raise InvalidArchiveManagerLease("invalid archive-manager lease")
        if lease._coordinator_id != self._coordinator_id:
            raise InvalidArchiveManagerLease(
                "archive-manager lease belongs to another coordinator"
            )
        with self._lock:
            if self._holder is None:
                return False
            if self._holder._token != lease._token:
                raise InvalidArchiveManagerLease(
                    "archive-manager lease is not the current holder"
                )
            self._holder = None
            return True

    @contextmanager
    def lease(
        self,
        kind: object,
        *,
        label: object | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Iterator[ArchiveManagerWorkLease]:
        """Acquire a lease and guarantee release after success or failure."""

        acquired = self.acquire(kind, label=label, metadata=metadata)
        try:
            yield acquired
        finally:
            self.release(acquired)

    def reconcile_stale_start(
        self,
        records: Iterable[_Record],
        *,
        is_stale: Callable[[_Record], bool],
        recover: Callable[[_Record], None],
    ) -> int:
        """Recover persisted running records before this process accepts work."""

        with self._lock:
            if self._holder is not None:
                raise ArchiveManagerBusyError(self._holder.snapshot())
            recovered = 0
            for record in records:
                if not is_stale(record):
                    continue
                recover(record)
                recovered += 1
            return recovered
