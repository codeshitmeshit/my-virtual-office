import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
WEBSITE = ROOT / "website"

ENTRY_POINTS: tuple[Path, ...] = (
    APP / "index.html",
    APP / "setup.html",
    APP / "models.html",
    APP / "cron.html",
    WEBSITE / "index.html",
)

SYSTEM_TOKENS: dict[str, str] = {
    "--ui-canvas": "#0a0a0f",
    "--ui-surface": "#12121e",
    "--ui-toolbar": "#151520",
    "--ui-panel": "#1a1a2e",
    "--ui-text-primary": "#e8e8f0",
    "--ui-text-muted": "#888888",
    "--ui-accent": "#ffd700",
    "--ui-success": "#4caf50",
    "--ui-info": "#4fc3f7",
    "--ui-warning": "#ffb300",
    "--ui-danger": "#f44336",
}

# 这些例外只覆盖领域视觉或运行时几何，不能扩展到导航、表单、弹窗和反馈。
DOMAIN_VISUAL_EXCEPTIONS: dict[Path, set[str]] = {
    APP / "style.css": {"--pq-", "--eng-", "--gba-", "--vo-font-scale"},
    APP / "project-orchestration.css": {"pipeline-canvas"},
    WEBSITE / "styles.css": {"hero-artwork", "demo-artwork", "marketing-display"},
}

PROHIBITED_GLOBAL_ROOTS: set[Path] = {
    APP / "fonts.css",
    APP / "window-controls.css",
    APP / "project-orchestration.css",
}

INLINE_STYLE_BASELINE: dict[Path, int] = {
    APP / "index.html": 125,
    APP / "setup.html": 96,
    APP / "models.html": 15,
    APP / "cron.html": 35,
    WEBSITE / "index.html": 17,
}

STANDALONE_ENTRIES = (APP / "setup.html", APP / "models.html", APP / "cron.html")
ROOT_RE = re.compile(r":root\s*\{(?P<body>.*?)\}", re.DOTALL)
DEFINITION_RE = re.compile(r"(?P<name>--[\w-]+)\s*:\s*(?P<value>[^;]+);")
REFERENCE_RE = re.compile(r"var\(\s*(?P<name>--[\w-]+)\s*(?P<fallback>,[^)]*)?\)")
STYLESHEET_RE = re.compile(
    r"<link\b(?=[^>]*\brel=[\"']stylesheet[\"'])[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>",
    re.IGNORECASE,
)


def _entry_stylesheets(entry: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for href in STYLESHEET_RE.findall(entry.read_text(encoding="utf-8")):
        href = href.split("?", 1)[0]
        if href.startswith(("http://", "https://")):
            continue
        if href.startswith("/"):
            candidate = APP / href.removeprefix("/")
        else:
            candidate = entry.parent / href
        if candidate.exists():
            paths.append(candidate.resolve())
    return tuple(paths)


def _definitions(source: str) -> dict[str, str]:
    return {match.group("name"): match.group("value").strip() for match in DEFINITION_RE.finditer(source)}


def _required_references(source: str) -> set[str]:
    return {
        match.group("name")
        for match in REFERENCE_RE.finditer(source)
        if not match.group("fallback")
    }


def test_canonical_foundation_owns_exact_figma_tokens():
    foundation = APP / "ui-system.css"
    assert foundation.exists(), f"缺少共享 UI 基础层：{foundation.relative_to(ROOT)}"
    definitions = _definitions(foundation.read_text(encoding="utf-8"))
    for name, expected in SYSTEM_TOKENS.items():
        actual = definitions.get(name, "").lower().replace(" ", "")
        assert actual == expected, f"{foundation.relative_to(ROOT)}: {name} 应为 {expected}，实际为 {actual or '未定义'}"


def test_every_entry_loads_foundation_before_feature_styles():
    for entry in ENTRY_POINTS:
        stylesheets = _entry_stylesheets(entry)
        names = [path.name for path in stylesheets]
        assert "ui-system.css" in names, f"{entry.relative_to(ROOT)} 未加载 ui-system.css；当前顺序：{names}"
        foundation_index = names.index("ui-system.css")
        feature_indexes = [
            index
            for index, name in enumerate(names)
            if name not in {"ui-system.css", "fonts.css"}
        ]
        if feature_indexes:
            assert foundation_index < min(feature_indexes), (
                f"{entry.relative_to(ROOT)} 必须在 feature stylesheet 前加载 ui-system.css；当前顺序：{names}"
            )


def test_entry_stylesheets_have_no_undefined_required_custom_properties():
    for entry in ENTRY_POINTS:
        sources: list[tuple[Path, str]] = []
        entry_source = entry.read_text(encoding="utf-8")
        sources.append((entry, entry_source))
        for stylesheet in _entry_stylesheets(entry):
            sources.append((stylesheet, stylesheet.read_text(encoding="utf-8")))

        definitions: set[str] = set()
        for _path, source in sources:
            definitions.update(_definitions(source))

        missing: list[str] = []
        for path, source in sources:
            for name in sorted(_required_references(source) - definitions):
                missing.append(f"{path.relative_to(ROOT)} -> {name}")
        assert not missing, f"{entry.relative_to(ROOT)} 存在未定义且无 fallback 的 CSS 变量：\n" + "\n".join(missing)


def test_competing_global_roots_are_removed_or_reduced_to_compatibility_aliases():
    violations: list[str] = []
    for path in PROHIBITED_GLOBAL_ROOTS:
        if not path.exists():
            continue
        if ROOT_RE.search(path.read_text(encoding="utf-8")):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "以下 feature/font 文件仍在声明竞争 :root：" + ", ".join(violations)


def test_standalone_entries_do_not_embed_static_stylesheets():
    violations = [
        str(path.relative_to(ROOT))
        for path in STANDALONE_ENTRIES
        if re.search(r"<style(?:\s[^>]*)?>", path.read_text(encoding="utf-8"), re.IGNORECASE)
    ]
    assert not violations, "独立页面的静态样式应迁入 ui-standalone.css：" + ", ".join(violations)


def test_inline_style_attributes_never_increase_above_the_recorded_baseline():
    for path, baseline in INLINE_STYLE_BASELINE.items():
        count = len(re.findall(r"\sstyle\s*=", path.read_text(encoding="utf-8"), re.IGNORECASE))
        assert count <= baseline, f"{path.relative_to(ROOT)} 新增了 inline style：baseline={baseline}, current={count}"
