# Task 8.2 Evidence: Figma CSS Shell

## Scope

- Added `app/project-orchestration.css` as the focused stylesheet for the stage-pipeline orchestration modal.
- Loaded the stylesheet after `projects.css` in `app/index.html` so the scoped orchestration styles can override project-board defaults without expanding the legacy project stylesheet.
- Encoded the Figma-derived modal shell, typography, dimensions, spacing, colors, borders, radii, shadows, controls, canvas, task-card, parallel-group, connector, footer, state, and responsive containment rules from task 8.1 evidence.
- Preserved the approved auto-save visual delta by hiding any `.project-orchestration-save` / `.proj-orchestration-save` footer action.

## Key Contracts

- Modal root: `1220x560`, gold `2px` border, `9px` radius, `#111124` background, `0 16px 36px rgba(0,0,0,0.65)` shadow.
- Header: `57px` high, `#0d0d1e`, `18px 14px` padding.
- Notice: `30px` high, `#0d1a29`, blue border/text treatment.
- Workspace/canvas: `1184x350` reference canvas, dark `#09091a`, `7px` radius.
- Task cards: `190x68`, `9px` padding, `7px` radius, state colors for in-progress, backlog, and review.
- Footer: `53px` high, hint text retained, save action hidden.
- Responsive containment: modal constrains to viewport, horizontal workspace overflow is enabled under the reference width.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_css.py
```

Result: `5 passed in 0.16s`

```bash
.venv/bin/python -m py_compile tests/test_project_orchestration_css.py
```

Result: passed

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
