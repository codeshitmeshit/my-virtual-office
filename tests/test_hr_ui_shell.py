"""Static shell guarantees for the independent Human Resources module."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def test_hr_first_level_entry_modal_and_assets_are_registered():
    html = (APP / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-human-resources"' in html
    assert 'onclick="openHumanResources()"' in html
    assert 'id="humanResourcesModal"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'human-resources.css?' in html
    assert 'human-resources.js?' in html
    assert html.index('id="btn-human-resources"') < html.index('id="humanResourcesModal"')
    assert 'id="human-resources-status"' not in html
    assert "hr-overview-hero" in (APP / "human-resources.js").read_text(encoding="utf-8")


def test_hr_shell_has_independent_responsive_list_and_detail_boundaries():
    html = (APP / "index.html").read_text(encoding="utf-8")
    css = (APP / "human-resources.css").read_text(encoding="utf-8")
    javascript = (APP / "human-resources.js").read_text(encoding="utf-8")
    for marker in ("hr-shell", "hr-agent-list", "hr-agent-detail"):
        assert marker in html
        assert f".{marker}" in css
    assert "@media (max-width: 760px)" in css
    assert "archiveRoom" not in javascript
    assert "ArchiveRoom" not in javascript
    assert "humanResourcesModal" in javascript
    assert "hr-selection-dialog" in javascript
    assert "/api/human-resources/daily-sync" in javascript
    assert ".hr-selection-dialog" in css
