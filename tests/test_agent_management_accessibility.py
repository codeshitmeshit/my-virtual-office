from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
INDEX = (APP / "index.html").read_text(encoding="utf-8")
SHELL = (APP / "agent-management.js").read_text(encoding="utf-8")
CONFIGURATION = (APP / "agent-configuration.js").read_text(encoding="utf-8")
GAME = (APP / "game.js").read_text(encoding="utf-8")
SHELL_CSS = (APP / "agent-management.css").read_text(encoding="utf-8")
CONFIGURATION_CSS = (APP / "agent-configuration.css").read_text(encoding="utf-8")


REQUIRED_LOCALE_KEYS = {
    "agent_management",
    "agent_management_subtitle",
    "agent_management_close",
    "agent_management_empty",
    "agent_configuration",
    "agent_configuration_loading",
    "agent_configuration_failed",
    "human_resources_loading",
    "agent_responsibility_hint",
    "agent_introduction",
    "agent_responsibilities",
    "agent_specialties",
    "agent_appearance",
    "agent_restricted_configuration",
    "agent_provider",
    "agent_branch",
    "agent_workspace",
    "agent_assignment",
    "agent_binding",
    "agent_change",
    "agent_confirm_change",
    "agent_target",
    "agent_action",
    "agent_before",
    "agent_after",
    "agent_change_invalid",
    "agent_change_applied",
    "agent_change_failed",
    "agent_save_saving",
    "agent_save_saved",
    "agent_save_conflict",
    "agent_save_denied",
    "agent_save_failed",
    "agent_save_undone",
}


def test_merged_management_copy_is_complete_in_english_and_chinese():
    locales = {
        language: json.loads(
            (APP / "locales" / f"{language}.json").read_text(encoding="utf-8")
        )
        for language in ("en", "zh")
    }

    for language, messages in locales.items():
        missing = REQUIRED_LOCALE_KEYS.difference(messages)
        assert not missing, f"{language} is missing {sorted(missing)}"
        assert all(str(messages[key]).strip() for key in REQUIRED_LOCALE_KEYS)


def test_tabs_panel_and_nested_confirmation_have_complete_semantics():
    assert 'id="agent-management-tab-configuration"' in INDEX
    assert 'id="agent-management-tab-human-resources"' in INDEX
    assert INDEX.count('aria-controls="agent-management-panel"') == 2
    assert 'role="tabpanel"' in INDEX
    assert 'aria-labelledby="agent-management-tab-configuration"' in INDEX
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in SHELL
    assert "event.key === 'Tab'" in SHELL
    assert 'role="alertdialog"' in CONFIGURATION
    assert 'aria-describedby="ac-confirm-impact"' in CONFIGURATION
    assert "event.stopPropagation()" in CONFIGURATION
    assert CONFIGURATION.count("tr('agent_before'") == 1
    assert CONFIGURATION.count("tr('agent_after'") >= 1


def test_focus_responsive_and_reduced_motion_contracts_are_explicit():
    assert ":focus-visible" in SHELL_CSS
    assert "@media (max-width: 820px)" in SHELL_CSS
    assert "@media (prefers-reduced-motion: reduce)" in SHELL_CSS
    assert ":focus-visible" in CONFIGURATION_CSS
    assert "@media (max-width: 620px)" in CONFIGURATION_CSS
    assert "@media (prefers-reduced-motion: reduce)" in CONFIGURATION_CSS


def test_old_independent_hr_modal_is_absent_and_new_modules_are_decoupled():
    assert 'id="humanResourcesModal"' not in INDEX
    assert INDEX.count('id="agent-management-close"') == 1
    assert INDEX.index('src="game.js?') < INDEX.index('src="agent-management.js?')
    assert "_acp" not in SHELL
    assert "_acp" not in CONFIGURATION
    assert "_acp" not in GAME
    assert "function toggleAgentPanel" not in GAME
    assert "window.AgentManagement.setRoster(agents)" in GAME
