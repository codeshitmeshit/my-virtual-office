from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "app" / "agent-configuration.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "agent-configuration-figma.css").read_text(
    encoding="utf-8"
)
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")


def test_configuration_uses_figma_three_column_structure_and_pixel_preview():
    assert "ac-summary-strip" not in SCRIPT
    assert "ac-profile-columns" in SCRIPT
    assert "ac-profile-primary" in SCRIPT
    assert "ac-appearance-card" in SCRIPT
    assert "data-agent-appearance-preview" in SCRIPT
    assert "agent-appearance-preview.js" in INDEX
    assert "agent-configuration-figma.css" in (
        ROOT / "app" / "agent-management.js"
    ).read_text(encoding="utf-8")


def test_figma_typography_and_column_proportions_are_explicit():
    assert "font-family: var(--vo-pixel-ui-font)" in STYLES
    assert "font-size: 7px" in STYLES
    assert "minmax(430px, 1fr) minmax(330px, 410px)" in STYLES
    assert "overflow-y: auto" in STYLES
    assert "scrollbar-gutter: stable" in STYLES
    assert "image-rendering: pixelated" in STYLES
