"""个人资产 owner 命令；HTTP 与 Skill 共用同一事务语义。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .personal_asset_store import PersonalAssetStore


JsonDict = dict[str, Any]
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PersonalAssetServiceResult:
    payload: JsonDict

    def to_dict(self) -> JsonDict:
        return dict(self.payload)


class PersonalAssetService:
    def __init__(
        self,
        store: PersonalAssetStore,
        *,
        on_mutation: Callable[[JsonDict], None] | None = None,
    ):
        if not isinstance(store, PersonalAssetStore):
            raise TypeError("store must be a PersonalAssetStore")
        if on_mutation is not None and not callable(on_mutation):
            raise TypeError("on_mutation must be callable")
        self.store = store
        self._on_mutation = on_mutation or (lambda _profile: None)

    @staticmethod
    def _profile(result: Mapping[str, Any]) -> JsonDict:
        snapshot = result.get("snapshot") if isinstance(result.get("snapshot"), dict) else result
        return {
            "revision": int(snapshot.get("revision") or 0),
            "entries": list(snapshot.get("entries") or []),
            "suggestions": list(snapshot.get("suggestions") or []),
        }

    def snapshot(self) -> JsonDict:
        return self._profile(self.store.snapshot())

    def _notify_mutation(self, profile: JsonDict) -> None:
        try:
            self._on_mutation(profile)
        except Exception as exc:
            # Observers run strictly after the local commit and may never alter its result.
            _LOGGER.warning(
                "Personal Assets post-commit observer failed code=%s",
                str(getattr(exc, "code", "personal_asset_observer_failed")),
            )

    def _mutation(self, result: JsonDict) -> JsonDict:
        profile = self._profile(result)
        self._notify_mutation(profile)
        return {**result, "profile": profile}

    def create_entry(self, payload: Mapping[str, object], *, expected_revision: int) -> JsonDict:
        return self._mutation(
            self.store.create_entry(payload, expected_revision=expected_revision)
        )

    def update_entry(
        self, entry_id: object, patch: Mapping[str, object], *, expected_revision: int
    ) -> JsonDict:
        return self._mutation(
            self.store.update_entry(entry_id, patch, expected_revision=expected_revision)
        )

    def delete_entry(self, entry_id: object, *, expected_revision: int) -> JsonDict:
        return self._mutation(
            self.store.delete_entry(entry_id, expected_revision=expected_revision)
        )

    def list_suggestions(self) -> list[JsonDict]:
        return list(self.snapshot()["suggestions"])

    def submit_suggestion(
        self,
        *,
        proposal: Mapping[str, object],
        source: Mapping[str, object],
        idempotency_key: object,
    ) -> JsonDict:
        result = self.store.create_suggestion(
            {"proposal": proposal, "source": source}, idempotency_key=idempotency_key
        )
        if result.get("created"):
            self._notify_mutation(self.snapshot())
        return result

    def accept_suggestion(
        self,
        suggestion_id: object,
        *,
        expected_revision: int,
        edited_proposal: Mapping[str, object] | None = None,
    ) -> JsonDict:
        # entry 写入与 suggestion 终态必须共享一次提交，前端无需承担补偿事务。
        return self._mutation(
            self.store.resolve_suggestion(
                suggestion_id,
                action="accept",
                expected_revision=expected_revision,
                edited_proposal=edited_proposal,
            )
        )

    def reject_suggestion(
        self, suggestion_id: object, *, expected_revision: int
    ) -> JsonDict:
        return self._mutation(
            self.store.resolve_suggestion(
                suggestion_id, action="reject", expected_revision=expected_revision
            )
        )

    def apply_confirmed_batch(
        self,
        changes: Sequence[Mapping[str, object]],
        *,
        expected_revision: int,
        idempotency_key: object,
        source: Mapping[str, object],
    ) -> JsonDict:
        result = self.store.apply_batch(
            changes,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            source=source,
        )
        if result.get("idempotent"):
            return {**result, "profile": self._profile(result)}
        return self._mutation(result)
