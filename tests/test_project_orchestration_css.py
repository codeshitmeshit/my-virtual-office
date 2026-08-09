from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "project-orchestration.css").read_text(encoding="utf-8")


def test_orchestration_css_is_loaded_after_project_board_styles():
    projects = INDEX.index('href="projects.css')
    orchestration = INDEX.index('href="project-orchestration.css')

    assert projects < orchestration


def test_figma_modal_shell_dimensions_and_surface_tokens_are_scoped():
    assert ".project-orchestration-modal" in CSS
    assert ".proj-orchestration-modal" in CSS
    assert "width: min(1220px, calc(100vw - 64px));" in CSS
    assert "height: min(560px, calc(100vh - 48px));" in CSS
    assert "border: 2px solid var(--project-orchestration-gold);" in CSS
    assert "border-radius: 9px;" in CSS
    assert ":root" not in CSS
    assert "--project-orchestration-bg: var(--ui-surface);" in CSS
    assert "--project-orchestration-gold: var(--ui-accent);" in CSS
    assert "--project-orchestration-blue: var(--ui-info);" in CSS


def test_figma_workspace_canvas_and_card_geometry_are_explicit():
    assert "flex: 1 1 auto;" in CSS
    assert "overflow: auto;" in CSS
    assert "scrollbar-gutter: stable both-edges;" in CSS
    assert ".project-orchestration-canvas::-webkit-scrollbar" in CSS
    assert ".project-orchestration-canvas-surface" in CSS
    assert "min-height: 100%;" in CSS
    assert "border: 1px solid var(--project-orchestration-line);" in CSS
    assert "width: 190px;" in CSS
    assert "height: 68px;" in CSS
    assert "padding: 9px;" in CSS
    assert "gap: 12px;" in CSS


def test_draggable_task_text_does_not_steal_drag_pointer_events():
    assert '.project-orchestration-task[draggable="true"] .project-orchestration-task-row' in CSS
    assert "pointer-events: none;" in CSS
    assert '.project-orchestration-task[draggable="true"] .project-orchestration-icon-action' in CSS
    assert "pointer-events: auto;" in CSS


def test_figma_stage_positions_and_state_colors_are_represented():
    for expected in (
        '[data-stage="1"] { left: 24px; top: 141px; }',
        '[data-stage="2"] { left: 257px; top: 141px; }',
        '[data-stage="3"] { left: 490px; top: 141px; }',
        '[data-stage="4"] { left: 723px; top: 141px; }',
        '[data-stage="5"] { left: 956px; top: 141px; }',
    ):
        assert expected in CSS
    assert "border-color: var(--project-orchestration-blue);" in CSS
    assert "border-color: var(--project-orchestration-review);" in CSS
    assert "color: var(--project-orchestration-muted);" in CSS


def test_auto_save_delta_hides_figma_save_button():
    assert ".project-orchestration-save" in CSS
    assert ".proj-orchestration-save" in CSS
    assert "display: none;" in CSS
