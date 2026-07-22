#!/usr/bin/env python3
"""Content-free compatibility comparison for conversation timeline migrations."""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = (
    ROOT
    / "openspec"
    / "changes"
    / "unify-conversation-timeline-projections"
    / "evidence"
    / "baseline"
    / "conversation-timeline-allowed-differences.json"
)
CONTENT_BEARING_KEYS = {
    "content",
    "headers",
    "message",
    "prompt",
    "reasoningtext",
    "secret",
    "text",
    "thinking",
    "thinkingtext",
    "toolarguments",
    "toolresult",
    "transcript",
}


@dataclass(frozen=True)
class Difference:
    observation_id: str
    provider: str
    surface: str
    dimension: str
    path: str
    before: Any
    after: Any


def _flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{path}/{key}"
            flattened.update(_flatten(value[key], child))
        return flattened or {path or "/": {}}
    if isinstance(value, list):
        flattened = {}
        for index, item in enumerate(value):
            flattened.update(_flatten(item, f"{path}/{index}"))
        return flattened or {path or "/": []}
    return {path or "/": value}


def _index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assert snapshot.get("schema") == 1
    assert snapshot.get("contentPolicy") == "content-free"
    observations = snapshot.get("observations")
    assert isinstance(observations, list)
    for observation in observations:
        values = observation.get("values") or {}
        assert not {
            str(key).replace("_", "").lower()
            for key in _walk_keys(values)
        }.intersection(CONTENT_BEARING_KEYS)
    indexed = {item["id"]: item for item in observations}
    assert len(indexed) == len(observations)
    return indexed


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[Difference]:
    left = _index(before)
    right = _index(after)
    differences: list[Difference] = []
    for observation_id in sorted(set(left) | set(right)):
        old = left.get(observation_id)
        new = right.get(observation_id)
        context = new or old or {}
        old_values = _flatten((old or {}).get("values", {"__observation__": "missing"}))
        new_values = _flatten((new or {}).get("values", {"__observation__": "missing"}))
        for field in ("provider", "surface", "dimension"):
            old_values[f"/__meta__/{field}"] = (old or {}).get(field, {"__value__": "missing"})
            new_values[f"/__meta__/{field}"] = (new or {}).get(field, {"__value__": "missing"})
        for path in sorted(set(old_values) | set(new_values)):
            old_value = old_values.get(path, {"__value__": "missing"})
            new_value = new_values.get(path, {"__value__": "missing"})
            if old_value != new_value:
                differences.append(
                    Difference(
                        observation_id=observation_id,
                        provider=str(context.get("provider") or ""),
                        surface=str(context.get("surface") or ""),
                        dimension=str(context.get("dimension") or ""),
                        path=path,
                        before=old_value,
                        after=new_value,
                    )
                )
    return differences


def _rule_matches(rule: dict[str, Any], difference: Difference) -> bool:
    selectors = rule.get("selectors") or {}
    for field in ("observation_id", "provider", "surface", "dimension"):
        expected = selectors.get(field)
        if expected is not None and getattr(difference, field) != expected:
            return False
    return any(fnmatch.fnmatchcase(difference.path, pattern) for pattern in rule.get("paths") or [])


def assess(before: dict[str, Any], after: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    assert policy.get("schema") == 1
    assert policy.get("contentPolicy") == "content-free"
    assert policy.get("defaultAction") == "reject"
    assert set(policy.get("comparedDimensions") or []) == {
        "dto", "status", "order", "events", "history", "interaction", "visual"
    }
    allowed = []
    rejected = []
    for difference in compare(before, after):
        rule = next((item for item in policy.get("allowedCorrections") or [] if _rule_matches(item, difference)), None)
        record = {
            "observationId": difference.observation_id,
            "provider": difference.provider,
            "surface": difference.surface,
            "dimension": difference.dimension,
            "path": difference.path,
            "correctionId": (rule or {}).get("id"),
        }
        (allowed if rule else rejected).append(record)
    return {"ok": not rejected, "allowed": allowed, "rejected": rejected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    result = assess(
        json.loads(args.before.read_text(encoding="utf-8")),
        json.loads(args.after.read_text(encoding="utf-8")),
        json.loads(args.policy.read_text(encoding="utf-8")),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
