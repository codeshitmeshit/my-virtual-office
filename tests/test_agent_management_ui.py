from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
SHELL = (ROOT / "app" / "agent-management.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "agent-management.css").read_text(encoding="utf-8")
HR = (ROOT / "app" / "human-resources.js").read_text(encoding="utf-8")


def test_merged_shell_has_peer_tabs_shared_selection_and_one_close_control():
    assert 'id="agentManagementModal"' in INDEX
    assert INDEX.count('id="agent-management-close"') == 1
    assert 'data-agent-management-tab="configuration"' in INDEX
    assert 'data-agent-management-tab="humanResources"' in INDEX
    assert "selectedAiId" in SHELL
    assert "scrollTop" in SHELL
    assert "setRoster" in SHELL
    assert "selectAgent" in SHELL
    assert "setAudience" in SHELL
    assert "mountTab" in SHELL
    assert "reportMutation" in SHELL


def test_shell_is_responsive_accessible_and_has_no_global_save_button():
    assert 'role="dialog"' in INDEX
    assert 'role="tablist"' in INDEX
    assert 'aria-live="polite"' in INDEX
    assert "@media (max-width: 820px)" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    modal_start = INDEX.index('id="agentManagementModal"')
    modal_end = INDEX.index("<!-- SMS Panel -->", modal_start)
    modal = INDEX[modal_start:modal_end]
    assert "Save configuration" not in modal
    assert "保存配置" not in modal


def test_human_resources_is_embeddable_and_does_not_read_configuration_globals():
    assert "function mountPanel(context)" in HR
    assert "embeddedContext.adapter.hrRequest" in HR
    assert "embeddedContext.setRoster" in HR
    assert "AgentManagement.mountTab('humanResources', api)" in HR
    assert "if (root.HumanResources) mountTab('humanResources', root.HumanResources);" in SHELL
    assert "AgentConfiguration" not in HR
    assert "_acp" not in HR
