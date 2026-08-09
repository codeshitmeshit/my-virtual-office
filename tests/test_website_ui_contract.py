from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "website" / "styles.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "website" / "script.js").read_text(encoding="utf-8")


def test_website_loads_foundation_before_marketing_styles():
    assert HTML.index('/ui-system.css') < HTML.index('styles.css')
    assert HTML.index('/fonts.css') < HTML.index('/ui-system.css')


def test_marketing_aliases_resolve_to_canonical_semantics():
    expected = {
        "--bg": "var(--ui-canvas)",
        "--surface": "var(--ui-surface)",
        "--text": "var(--ui-text-primary)",
        "--accent": "var(--ui-accent)",
        "--green": "var(--ui-success)",
        "--red": "var(--ui-danger)",
    }
    for name, value in expected.items():
        assert re.search(rf"{re.escape(name)}\s*:\s*{re.escape(value)}\s*;", CSS)


def test_focus_responsive_and_reduced_motion_contracts_exist():
    assert ":focus-visible" in CSS
    assert "@media (max-width: 900px)" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert ".is-reveal-pending.is-visible" in CSS


def test_navigation_and_cta_targets_are_preserved():
    for target in (
        '#features', '#demo', '#pricing', '#setup',
        'https://github.com/yourvirtualoffice/app',
        'https://github.com/openclaw/openclaw',
        'https://discord.com/invite/clawd',
        'mailto:support@yourvirtualoffice.com',
    ):
        assert f'href="{target}"' in HTML
    assert 'id="buy-btn"' in HTML
    assert 'id="buy-full-btn"' in HTML


def test_presentation_state_uses_classes_without_changing_menu_or_scroll_targets():
    assert "classList.toggle('is-scrolled'" in SCRIPT
    assert "classList.add('is-visible'" in SCRIPT
    assert ".style.borderBottomColor" not in SCRIPT
    assert ".style.opacity" not in SCRIPT
    assert "scrollIntoView({ behavior: 'smooth', block: 'start' })" in SCRIPT


def test_marketing_artwork_and_display_type_exceptions_remain_narrow():
    # 营销插画、演示画布与大标题保留内容表达，不扩展为第二套表单/组件系统。
    assert ".preview-canvas" in CSS
    assert ".p-agent" in CSS
    assert "font-size: clamp(40px, 7vw, 72px)" in CSS
    assert ".btn:focus-visible" in CSS
