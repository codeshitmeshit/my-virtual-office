from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
COMPONENTS = (APP / "ui-components.css").read_text(encoding="utf-8")
WINDOW_CONTROLS = (APP / "window-controls.css").read_text(encoding="utf-8")
INDEX = (APP / "index.html").read_text(encoding="utf-8")


def test_shared_component_layer_loads_after_tokens_and_before_feature_styles():
    system = INDEX.index('href="ui-system.css')
    components = INDEX.index('href="ui-components.css')
    feature = INDEX.index('href="style.css')
    assert system < components < feature


def test_shared_controls_expose_every_required_interaction_state():
    for state in (":hover", ":active", ":focus-visible", ":disabled", "aria-busy", "aria-invalid", "is-error"):
        assert state in COMPONENTS, f"ui-components.css 缺少组件状态：{state}"
    assert "prefers-reduced-motion: reduce" in COMPONENTS


def test_close_is_neutral_and_delete_remains_danger():
    assert "var(--ui-text-muted)" in WINDOW_CONTROLS
    assert "var(--ui-panel)" in WINDOW_CONTROLS
    assert "var(--ui-info)" in WINDOW_CONTROLS
    assert "#f44336" not in WINDOW_CONTROLS.lower()
    assert ".ui-button--danger" in COMPONENTS
    assert "var(--ui-danger)" in COMPONENTS


def test_invalid_and_disabled_states_are_not_color_only():
    assert "[aria-invalid=\"true\"]" in COMPONENTS
    assert ".ui-field-error" in COMPONENTS
    assert "[data-ui-field-error]" in COMPONENTS
    assert "cursor: not-allowed" in COMPONENTS
    assert "filter: saturate" in COMPONENTS


def test_action_semantics_remain_distinct():
    assert ".ui-button--primary" in COMPONENTS
    assert ".ui-button--secondary" in COMPONENTS
    assert ".ui-button--danger" in COMPONENTS
    assert ".ui-button--test" in COMPONENTS
    assert "[data-action-tone=\"danger\"]" in COMPONENTS
    assert "[data-action-tone=\"test\"]" in COMPONENTS
