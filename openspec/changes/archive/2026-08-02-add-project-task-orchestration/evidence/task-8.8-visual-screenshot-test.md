# Task 8.8 Evidence: Deterministic Visual Screenshot Test

## Scope

- Added `tests/check_project_orchestration_visual_snapshot.mjs`, a CDP/Chromium screenshot test with a deterministic `1512x742` viewport.
- The test renders a self-contained project orchestration modal fixture with `9 TASKS · 5 STEPS`, matching the Figma reference scenario from task 8.1.
- The test captures a candidate screenshot at `openspec/changes/add-project-task-orchestration/evidence/figma/candidate-8.8-orchestration-overlay.png`.
- The test validates Figma reference PNG dimensions and candidate PNG dimensions.
- The test compares key runtime geometry against Figma evidence: complete overlay, modal placement and size, header, notice, `1184x350` canvas, footer, task count, stage count, connector count, typography family, modal/canvas colors, and absence of the removed save button.
- Adjusted `app/project-orchestration.css` workspace horizontal padding from `18px` to `16px` so the bordered modal's rendered canvas measures the Figma target `1184px` while preserving the visual `18px` offset from the modal border.

## Candidate Screenshot

- `openspec/changes/add-project-task-orchestration/evidence/figma/candidate-8.8-orchestration-overlay.png`
- PNG dimensions: `1512x742`
- File size: `40K`

## Measured Candidate Geometry

- Viewport: `1512x742`
- Overlay: `0,0,1512x742`
- Modal: `x=146,y=91,width=1220,height=560`
- Header: `height=57`
- Notice: `height=32` including border-box rendering, within tolerance of the Figma `30px` content height
- Canvas: `x=164,y=228,width=1184,height=350`
- Footer: `height=55` including border-box rendering, within tolerance of the Figma `53px` content height
- Tasks: `9`
- Stages: `5`
- Connectors: `4`
- Save button count: `0`
- Title: `任务流水线编排`
- Count label: `9 TASKS · 5 STEPS`
- Modal background: `rgb(17, 17, 36)`
- Modal border: `rgb(255, 215, 0)`
- Canvas background: `rgb(9, 9, 26)`

## Verification

```bash
node tests/check_project_orchestration_visual_snapshot.mjs
```

Result: passed and generated `candidate-8.8-orchestration-overlay.png`

```bash
node --check app/project-orchestration.js && node --check tests/check_project_orchestration_visual_snapshot.mjs && node tests/check_project_orchestration_modal.mjs && node tests/check_project_orchestration_page_wiring.mjs && node tests/check_project_orchestration_api_contract.mjs
```

Result: passed

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_css.py
```

Result: `5 passed in 0.14s`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
