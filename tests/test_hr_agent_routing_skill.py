"""HR directory responsibility publishing into the VO entry skill."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_agent_routing_skill import (  # noqa: E402
    ROUTING_END,
    ROUTING_START,
    publish_agent_routing_skill,
)
from services.hr_repository import HRRepository  # noqa: E402


ENTRY_SKILL = """# Virtual Office Skill 入口

### 2. 读取实例权威 Skill

完整读取当前实例返回的 `/skills/index.md`。

### 3. 路由到专用 VO Skill

根据任务意图选择。
"""


def _repository(root: Path) -> HRRepository:
    repository = HRRepository(root / "status")
    repository.initialize()
    for ai_id, name, availability in (
        ("market-analyst-team-agent", "分析师", "available"),
        ("builder-agent", "工程师", "busy"),
        ("offline-agent", "离线同事", "offline"),
        ("hr", "HR", "available"),
    ):
        repository.upsert_agent(
            ai_id=ai_id,
            name=name,
            agent_kind="project",
            provider_kind="codex",
            status="active",
            availability=availability,
            source="test",
        )
    repository.save_introduction(
        ai_id="market-analyst-team-agent",
        state="published",
        raw_response="private market role",
        introduction="负责股票研究、估值、交易风险和市场信息整理。",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    repository.save_introduction(
        ai_id="builder-agent",
        state="published",
        raw_response="private builder role",
        introduction="负责代码实现、故障排查和工程方案。",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    repository.save_introduction(
        ai_id="offline-agent",
        state="published",
        raw_response="private offline role",
        introduction="这条离线 Agent 不应出现在路由表。",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    repository.save_introduction(
        ai_id="hr",
        state="published",
        raw_response="private hr role",
        introduction="HR 自己不参与普通任务路由。",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    return repository


def test_publishes_hr_routing_table_into_entry_skill_before_routing_section():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        skill_path = root / "SKILL.md"
        skill_path.write_text(ENTRY_SKILL, encoding="utf-8")

        result = publish_agent_routing_skill(
            _repository(root),
            skill_path=skill_path,
            new_id=lambda: "test",
        )
        updated = skill_path.read_text(encoding="utf-8")

    assert result.changed is True
    assert ROUTING_START in updated
    assert ROUTING_END in updated
    assert updated.index(ROUTING_START) < updated.index("### 3. 路由到专用 VO Skill")
    assert "`market-analyst-team-agent` 分析师" in updated
    assert "股票研究、估值、交易风险" in updated
    assert "`builder-agent` 工程师" in updated
    assert "offline-agent" not in updated
    assert "`hr`" not in updated


def test_publishing_replaces_existing_hr_routing_table_in_place():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        skill_path = root / "SKILL.md"
        skill_path.write_text(
            ENTRY_SKILL.replace(
                "### 3. 路由到专用 VO Skill",
                f"{ROUTING_START}\nold table\n{ROUTING_END}\n\n### 3. 路由到专用 VO Skill",
            ),
            encoding="utf-8",
        )

        publish_agent_routing_skill(
            _repository(root),
            skill_path=skill_path,
            new_id=lambda: "test",
        )
        updated = skill_path.read_text(encoding="utf-8")

    assert "old table" not in updated
    assert updated.count(ROUTING_START) == 1
    assert updated.count(ROUTING_END) == 1


if __name__ == "__main__":
    test_publishes_hr_routing_table_into_entry_skill_before_routing_section()
    test_publishing_replaces_existing_hr_routing_table_in_place()
