from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
MANAGEMENT = (ROOT / "app" / "agent-management.js").read_text(encoding="utf-8")
HUMAN_RESOURCES = (ROOT / "app" / "human-resources.js").read_text(encoding="utf-8")
FIGMA_CSS = (ROOT / "app" / "human-resources-figma.css").read_text(encoding="utf-8")


def test_hr_tab_registration_is_independent_of_script_order():
    assert "if (root.HumanResources)" in MANAGEMENT
    assert "api.mountTab('humanResources', root.HumanResources)" in MANAGEMENT
    assert "if (root.AgentManagement)" in HUMAN_RESOURCES
    assert "root.AgentManagement.mountTab('humanResources', api)" in HUMAN_RESOURCES


def test_figma_override_is_loaded_after_legacy_hr_styles():
    legacy = INDEX.index('href="human-resources.css')
    figma = INDEX.index('href="human-resources-figma.css')
    assert legacy < figma


def test_merged_hr_has_summary_and_semantic_detail_regions():
    assert "renderEmbeddedSummary()" in HUMAN_RESOURCES
    assert 'class="hr-embedded-summary"' in HUMAN_RESOURCES
    for region in (
        "hr-identity-section",
        "hr-reports-section",
        "hr-assessments-section",
        "hr-access-section",
    ):
        assert region in HUMAN_RESOURCES


def test_merged_hr_uses_pixel_type_and_independent_detail_scroll():
    assert 'font-family: var(--vo-pixel-ui-font' in FIGMA_CSS
    assert '.agent-management-panel[data-active-tab="humanResources"]' in FIGMA_CSS
    assert "grid-template-columns: minmax(0, 1fr);" in FIGMA_CSS
    assert "overflow-y: auto;" in FIGMA_CSS
    assert "overscroll-behavior: contain;" in FIGMA_CSS


def test_figma_detail_grid_matches_four_column_metadata_contract():
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in FIGMA_CSS
    assert ".hr-reports-section" in FIGMA_CSS
    assert ".hr-assessments-section" in FIGMA_CSS
    assert "font-size: 13px;" in FIGMA_CSS
    assert "font-size: 9px;" in FIGMA_CSS
