from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "app" / "mcp-registry-ui.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "mcp-registry.css").read_text(encoding="utf-8")


def test_registered_mcp_view_uses_structured_management_card():
    assert "mcp-registry.css" in INDEX
    assert "mcp-registry-section-heading" in INDEX
    assert "mcp-card-connection" in SCRIPT
    assert "mcp-client-grid" in SCRIPT
    assert "mcp-assignment-summary" in SCRIPT
    assert "mcp-guide-row" in SCRIPT
    assert "copy-command" in SCRIPT


def test_registered_clients_are_states_instead_of_duplicate_actions():
    assert "server[client] && server[client].registered" in SCRIPT
    assert "mcp-client-state" in SCRIPT
    assert "mcp-client-connect" in SCRIPT
    assert "mcp_client_cwd_not_persisted" in SCRIPT
    assert "legacyMatch" in SCRIPT


def test_agent_assignment_does_not_install_a_generated_skill():
    assert "/assign-agent" in SCRIPT
    assert "/skill'" not in SCRIPT
    assert "toggleMcpGuide" in SCRIPT
    assert "saveMcpGuide" in SCRIPT


def test_registry_card_has_responsive_layout_and_safe_overflow():
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in STYLES
    assert "text-overflow: ellipsis" in STYLES
    assert "@media (max-width: 560px)" in STYLES
