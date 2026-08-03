from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "vo-human-decision" / "SKILL.md"
GUIDE = ROOT / "skills" / "vo-operating-guidelines" / "SKILL.md"


def test_skill_is_discoverable_for_task_meeting_and_chat_execution():
    text = SKILL.read_text(encoding="utf-8")
    assert "name: vo-human-decision" in text
    assert "Use when" in text
    for source in ("task", "meeting", "chat"):
        assert f"`{source}`" in text
    assert "/api/agent/human-decisions" in text
    assert "X-VO-Agent-Action: human-decision" in text
    assert "idempotencyKey" in text
    assert "A、B、C、D" in text
    assert "自定义" in text
    assert "只暂停受影响" in text
    assert "置信度不足" in text
    assert "不要用普通聊天提问代替" in text
    assert "先调查" in text
    assert "source.id` 必须使用当前 Prompt" in text
    assert "结束当前 turn" in text
    assert "不要轮询" in text


def test_operating_guide_routes_human_decision_work():
    guide = GUIDE.read_text(encoding="utf-8")
    assert "/skills/vo-human-decision/SKILL.md" in guide
