from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = (ROOT / "app" / "branch-agent-selector.js").read_text(encoding="utf-8")
SELECTOR_STYLES = (ROOT / "app" / "branch-agent-selector.css").read_text(encoding="utf-8")
SKILLS = (ROOT / "app" / "skills-library-ui.js").read_text(encoding="utf-8")
MCP = (ROOT / "app" / "mcp-registry-ui.js").read_text(encoding="utf-8")
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")


def test_shared_selector_matches_meeting_branch_then_agent_interaction():
    assert "branch-agent-selector-branches" in SELECTOR
    assert "branch-agent-selector-hint" in SELECTOR
    assert "branch-agent-selector-agents" in SELECTOR
    assert "branchTogglePlacement === 'group-title'" in SELECTOR
    assert "branch-agent-selector-group-toggle" in SELECTOR
    assert "applyBranch" in SELECTOR
    assert "syncBranches" in SELECTOR
    assert "indeterminate" in SELECTOR
    assert "border-radius" not in SELECTOR_STYLES


def test_mcp_and_skill_library_use_the_shared_branch_selector():
    assert "AgentBranchSelector.render" in MCP
    assert "AgentBranchSelector.render" in SKILLS
    assert "branchTogglePlacement: 'group-title'" in MCP
    assert "skl-branch-toggle" in SKILLS
    assert "branchTogglePlacement: 'group-title'" in SKILLS
    assert "skl-agent-toggle" in SKILLS
    assert "applySkillToSelectedAgents" in SKILLS
    assert "branch-agent-selector.js" in INDEX
    assert "branch-agent-selector.css" in INDEX
