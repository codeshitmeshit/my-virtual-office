"""Structured task-comment projection for resolved project decisions."""

from __future__ import annotations

from typing import Any, Callable, Mapping


COMMENT_KIND = "human_decision"
COMMENT_AUTHOR = "human_decision"


def _text(value: Any) -> str:
    return str(value or "").strip()


def ensure_decision_comment(
    task: dict[str, Any],
    decision: Mapping[str, Any],
    *,
    decision_id: str,
    new_id: Callable[[], str],
    now: Callable[[], str],
) -> tuple[dict[str, Any], bool]:
    comments = task.setdefault("comments", [])
    existing = next(
        (
            item
            for item in comments
            if isinstance(item, dict)
            and item.get("kind") == COMMENT_KIND
            and item.get("decisionId") == decision_id
        ),
        None,
    )
    if existing is not None:
        return existing, False
    resolution = decision.get("resolution") if isinstance(decision.get("resolution"), Mapping) else {}
    title = _text(decision.get("title"))
    answer = _text(resolution.get("answer"))
    readable = f"{title}：{answer}" if title else answer
    if title and title.isascii():
        readable = f"{title}: {answer}"
    comment = {
        "id": new_id(),
        "kind": COMMENT_KIND,
        "author": COMMENT_AUTHOR,
        "text": readable,
        "createdAt": now(),
        "decisionId": decision_id,
        "decisionTitle": title,
        "decisionAnswer": answer,
        "customAnswer": "",
    }
    comments.append(comment)
    return comment, True


__all__ = ["COMMENT_AUTHOR", "COMMENT_KIND", "ensure_decision_comment"]
