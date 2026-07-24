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


def test_embedded_hr_reuses_agent_management_bootstrap_data():
    management = (APP / "agent-management.js").read_text(encoding="utf-8")
    javascript = (APP / "human-resources.js").read_text(encoding="utf-8")
    assert "overview: state.overview" in management
    assert "state.overview = result.overview || null" in management
    assert "function seedFromEmbeddedContext(context)" in javascript
    assert "source.overview && !state.overview" in javascript
    assert "source.roster).length && !state.agents.length" in javascript
    assert "function summaryDetail(aiId)" in javascript
    assert "state.detailCache.get(selected) || summaryDetail(selected)" in javascript


def test_hr_daily_records_collapse_history_and_keep_raw_report_primary():
    css = (APP / "human-resources.css").read_text(encoding="utf-8")
    javascript = (APP / "human-resources.js").read_text(encoding="utf-8")
    assert "function isCurrentRecord(record)" in javascript
    assert "function renderRecordDateButton(kind, item, index)" in javascript
    assert "function renderRecordDialog()" in javascript
    assert "openRecordDetail" in javascript
    assert "closeRecordDetail" in javascript
    assert "renderReport(record, { showNormalized: true })" not in javascript
    assert "showNormalized" not in javascript
    assert "hr_normalized_report" not in javascript
    assert "reportSubmissionLabelState" in javascript
    assert "function hrDisplayState(value)" in javascript
    assert "const displayState = hrDisplayState(item.status)" in javascript
    assert "renderRecordList('reports', reports, renderReport)" in javascript
    assert "renderRecordList('assessments', assessments, renderAssessment)" in javascript
    assert '<details open><summary>' in javascript
    assert ".hr-record-date-button" in css
    assert ".hr-record-dialog" in css
