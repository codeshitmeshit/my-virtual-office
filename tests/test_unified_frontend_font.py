from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
ENTRY_POINTS = (
    APP / "index.html",
    APP / "setup.html",
    APP / "models.html",
    APP / "cron.html",
    ROOT / "website" / "index.html",
)


def _font_declarations(source: str) -> list[str]:
    source = re.sub(r"--ui-font-family\s*:[^;]+;", "", source)
    return [value.strip() for value in re.findall(r"font-family\s*:\s*([^;}]+)", source)]


def test_every_entry_uses_local_fonts_without_remote_font_dependencies():
    for entry in ENTRY_POINTS:
        source = entry.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in source, f"{entry.name} still loads a remote font"
        assert "fonts.gstatic.com" not in source, f"{entry.name} still preconnects to a remote font"
        assert "fonts.css" in source
        assert source.index("fonts.css") < source.index("ui-system.css")


def test_canonical_tokens_resolve_pixel_and_technical_compatibility_to_one_family():
    fonts = (APP / "fonts.css").read_text(encoding="utf-8")
    system = (APP / "ui-system.css").read_text(encoding="utf-8")
    assert "font-family: 'VO Sans'" in fonts
    assert "font-weight: 100 900" in fonts
    assert "NotoSansSC-VF.woff2" in fonts
    assert '--ui-font-family: "VO Sans", sans-serif' in system
    assert "--vo-pixel-ui-font: var(--ui-font-family)" in system
    assert "--vo-technical-font: var(--ui-font-family)" in system


def test_dom_styles_use_only_the_canonical_font_token():
    sources = [*APP.glob("*.css"), ROOT / "website" / "styles.css"]
    for path in sources:
        declarations = _font_declarations(path.read_text(encoding="utf-8"))
        for value in declarations:
            if path.name == "fonts.css" and value == "'VO Sans'":
                continue
            assert value in {"var(--ui-font-family)", "var(--ui-font-family) !important"}, (
                f"{path.relative_to(ROOT)} has a non-canonical DOM font: {value}"
            )


def test_inline_and_dom_authored_styles_do_not_reintroduce_other_font_families():
    for path in [*ENTRY_POINTS, *APP.glob("*.js")]:
        source = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), 1):
            if "font-family" not in line:
                continue
            assert "var(--ui-font-family)" in line, (
                f"{path.relative_to(ROOT)}:{line_number} has a non-canonical DOM font"
            )
