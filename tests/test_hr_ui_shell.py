"""Static shell guarantees for the embedded Human Resources module."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def test_hr_is_registered_inside_the_merged_agent_management_entry():
    html = (APP / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-human-resources"' not in html
    assert 'id="btn-agent-settings"' in html
    assert 'id="agentManagementModal"' in html
    assert 'data-agent-management-tab="humanResources"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'human-resources.css?' in html
    assert 'human-resources.js?' in html
    assert html.index('id="btn-agent-settings"') < html.index('id="agentManagementModal"')
    assert 'id="human-resources-status"' not in html
    assert "hr-overview-hero" in (APP / "human-resources.js").read_text(encoding="utf-8")


def test_hr_panel_has_embedded_responsive_detail_boundary():
    html = (APP / "index.html").read_text(encoding="utf-8")
    css = (APP / "human-resources.css").read_text(encoding="utf-8")
    javascript = (APP / "human-resources.js").read_text(encoding="utf-8")
    for marker in ("hr-shell", "hr-agent-list", "hr-agent-detail"):
        assert f".{marker}" in css
    assert "@media (max-width: 760px)" in css
    assert "archiveRoom" not in javascript
    assert "ArchiveRoom" not in javascript
    assert "function mountPanel(context)" in javascript
    assert "hr-shell-embedded" in javascript
    assert "hr-selection-dialog" in javascript
    assert "/api/human-resources/daily-sync" in javascript
    assert ".hr-selection-dialog" in css
