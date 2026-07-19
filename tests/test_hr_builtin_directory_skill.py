"""VO built-in Agent-directory skill exposure and no-distribution checks."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "vo-agent-directory" / "SKILL.md"
CATALOG_PATH = ROOT / "skills" / "catalog.md"
GUIDE_PATH = ROOT / "app" / "agent-guide.js"
OPERATING_PATH = ROOT / "skills" / "vo-operating-guidelines" / "SKILL.md"


def test_directory_skill_is_exposed_by_the_vo_builtin_catalog():
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    assert "`/skills/vo-agent-directory/SKILL.md`" in catalog
    assert "'vo-agent-directory': 'human-resources'" in guide
    assert "agent_guide_cat_human_resources" in guide


def test_operating_guidelines_route_directory_intent_to_builtin_skill():
    text = OPERATING_PATH.read_text(encoding="utf-8")
    assert "区分 Agent 职责与可用性" in text
    assert "/skills/vo-agent-directory/SKILL.md" in text


def test_builtin_skill_forbids_workspace_copy_and_uses_separate_grant_reference():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "不要复制、安装或维护 Agent workspace 私有副本" in text
    assert ".vo/credentials/human-resources/grant-ref.json" in text
    assert "workspace-provisioned-grant" not in text
    assert "Authorization: Bearer <vo-provisioned-agent-grant>" in text


def test_hr_runtime_has_no_agent_directory_skill_publisher_or_workspace_target():
    service_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "app" / "services").glob("hr_*.py")
    )
    assert "class HRSkillPublisher" not in service_sources
    assert "sync_managed_skill_to_workspace" not in service_sources
    assert not re.search(
        r'workspace\s*/\s*["\']skills["\']\s*/\s*["\']vo-agent-directory["\']',
        service_sources,
    )


def test_grant_and_enablement_modules_have_no_legacy_transport_dependency():
    for relative in (
        "app/services/hr_agent_grants.py",
        "app/services/hr_directory_enablement.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "import server" not in source
        assert "OfficeHandler" not in source
        assert "http.server" not in source
