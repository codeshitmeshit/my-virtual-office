from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "agent-configuration.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "app" / "agent-configuration.js").read_text(encoding="utf-8")


def test_appearance_options_are_collapsed_scrollable_single_open_dropdowns():
    assert ".ac-option-popover.hidden { display: none; }" in CSS
    assert "max-height: min(320px, 45vh)" in CSS
    assert "overflow-y: auto" in CSS
    assert "otherToggle.setAttribute('aria-expanded', 'false')" in SCRIPT
    assert "toggle.setAttribute('aria-expanded', opening ? 'true' : 'false')" in SCRIPT
