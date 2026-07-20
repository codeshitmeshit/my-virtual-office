"""VO built-in Agent HR skill exposure and no-distribution checks."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "vo-agent-hr" / "SKILL.md"
CATALOG_PATH = ROOT / "skills" / "catalog.md"
GUIDE_PATH = ROOT / "app" / "agent-guide.js"
OPERATING_PATH = ROOT / "skills" / "vo-operating-guidelines" / "SKILL.md"


def test_hr_skill_is_the_only_hr_skill_exposed_by_the_vo_builtin_catalog():
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    assert "`/skills/vo-agent-hr/SKILL.md`" in catalog
    assert "vo-agent-directory" not in catalog
    assert "'vo-agent-hr': 'human-resources'" in guide
    assert "'vo-agent-directory'" not in guide
    assert "agent_guide_cat_human_resources" in guide


def test_operating_guidelines_route_hr_intents_to_builtin_skill():
    text = OPERATING_PATH.read_text(encoding="utf-8")
    assert "区分 Agent 职责与可用性" in text
    assert "/skills/vo-agent-hr/SKILL.md" in text
    assert "/skills/vo-agent-directory/SKILL.md" not in text


def test_builtin_skill_forbids_workspace_copy_and_has_no_grant_dependency():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "不要复制、安装或维护 Agent workspace 私有副本" in text
    assert "不需要独立 bearer grant" in text
    assert ".vo/credentials/human-resources" not in text
    assert "Authorization: Bearer" not in text


def test_hr_runtime_has_no_skill_publisher_or_grant_delivery_module():
    service_dir = ROOT / "app" / "services"
    service_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in service_dir.glob("hr_*.py")
    )
    assert "class HRSkillPublisher" not in service_sources
    assert "sync_managed_skill_to_workspace" not in service_sources
    assert not (service_dir / "hr_agent_grants.py").exists()
    assert not (service_dir / "hr_directory_enablement.py").exists()
