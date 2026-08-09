from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
ENTRIES = {
    "setup": APP / "setup.html",
    "models": APP / "models.html",
    "cron": APP / "cron.html",
}


def _source(name: str) -> str:
    return ENTRIES[name].read_text(encoding="utf-8")


def _stylesheets(source: str) -> list[str]:
    return re.findall(r'<link[^>]+href="([^"?]+)', source, re.IGNORECASE)


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    next_function = source.find("\n        function ", start + 1)
    return source[start : next_function if next_function >= 0 else len(source)]


def test_every_standalone_entry_uses_the_shared_order_without_embedded_css():
    for name, path in ENTRIES.items():
        source = path.read_text(encoding="utf-8")
        styles = _stylesheets(source)
        assert "<style" not in source.lower(), f"{path.name} must not own an embedded stylesheet"
        assert styles.index("ui-system.css") < styles.index("ui-components.css")
        assert styles.index("ui-components.css") < styles.index(f"{name}-page.css")
        assert styles.index(f"{name}-page.css") < styles.index("ui-standalone.css")
        assert f'class="standalone-page {name}-page"' in source


def test_standalone_styles_have_one_canonical_owner_and_accessible_states():
    shared = (APP / "ui-standalone.css").read_text(encoding="utf-8")
    assert ":focus-visible" in shared
    assert "@media (max-width: 700px)" in shared
    assert ":disabled" in shared
    assert "var(--ui-danger)" in shared
    for name in ENTRIES:
        page_css = (APP / f"{name}-page.css").read_text(encoding="utf-8")
        assert ":root" not in page_css, f"{name}-page.css must not create a competing token root"


def test_existing_ids_and_inline_handler_entry_points_are_preserved():
    setup = _source("setup")
    models = _source("models")
    cron = _source("cron")
    for required in ('id="step-0"', 'id="codex-test-status"', 'onclick="testCodexConnection()"'):
        assert required in setup
    for required in ('id="panel-cloud"', "onclick=\"showTab('cloud')\""):
        assert required in models
    for required in ('id="jobs-container"', 'onclick="openCreateModal()"', 'onclick="saveJob()"'):
        assert required in cron


def test_codex_and_claude_legacy_actions_remain_explicit_save_and_test_flows():
    setup = _source("setup")
    for function_name, test_endpoint, label in (
        ("testCodexConnection", "/api/codex/test", "Saving and testing Codex"),
        ("testClaudeCodeConnection", "/api/claude-code/test", "Saving and testing Claude Code"),
    ):
        function = _function(setup, function_name)
        assert label in function, f"{function_name} must disclose its persistence side effect"
        assert function.index("/setup/save") < function.index(test_endpoint), (
            f"{function_name} must preserve save-before-test request ordering"
        )


def test_runtime_visibility_styles_remain_with_existing_handlers():
    # 动态 display 是页面状态的一部分；共享样式只提供静态默认值，不改变处理器职责。
    cron = _source("cron")
    assert 'id="project-cron-fields" style="display:none' in cron
    assert 'id="sched-every" class="form-row" style="display:none"' in cron
    assert "function toggleScheduleFields()" in cron
