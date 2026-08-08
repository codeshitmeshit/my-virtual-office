from app.services.project_human_decision_comment import ensure_decision_comment


def decision(*, option_id="B", answer="分阶段发布"):
    return {
        "title": "确认发布策略",
        "resolution": {"answer": answer, "optionId": option_id},
    }


def test_ensure_decision_comment_adds_structured_compatible_comment_once():
    task = {"id": "task-1", "comments": []}

    first, created = ensure_decision_comment(
        task,
        decision(),
        decision_id="decision-1",
        new_id=lambda: "comment-1",
        now=lambda: "2026-08-08T17:00:00+08:00",
    )
    replay, replay_created = ensure_decision_comment(
        task,
        decision(),
        decision_id="decision-1",
        new_id=lambda: "comment-2",
        now=lambda: "later",
    )

    assert created is True
    assert replay_created is False
    assert replay is first
    assert first == {
        "id": "comment-1",
        "kind": "human_decision",
        "author": "human_decision",
        "text": "确认发布策略：分阶段发布",
        "createdAt": "2026-08-08T17:00:00+08:00",
        "decisionId": "decision-1",
        "decisionTitle": "确认发布策略",
        "decisionAnswer": "分阶段发布",
        "customAnswer": "",
    }
    assert task["comments"] == [first]


def test_custom_decision_is_not_duplicated_as_supplement():
    task = {"id": "task-1"}

    comment, _created = ensure_decision_comment(
        task,
        decision(option_id=None, answer="先在内部团队灰度一周"),
        decision_id="decision-1",
        new_id=lambda: "comment-1",
        now=lambda: "now",
    )

    assert comment["decisionAnswer"] == "先在内部团队灰度一周"
    assert comment["customAnswer"] == ""
    assert comment["text"].count("先在内部团队灰度一周") == 1
