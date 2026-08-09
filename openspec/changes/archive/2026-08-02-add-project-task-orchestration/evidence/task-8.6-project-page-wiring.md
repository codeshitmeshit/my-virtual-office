# Task 8.6 Evidence: Project Page Orchestration Wiring

## Scope

- Loaded `app/project-orchestration-api.js` before `app/project-orchestration.js` in `app/index.html`.
- Wired marked `stage_pipeline_v1` project boards to the focused `ProjectOrchestration` modal through a thin `ProjMgr.openProjectOrchestration()` entry.
- Added a project-page orchestration API adapter that delegates to `ProjectOrchestrationAPI` and refreshes the current project after modal mutations.
- Added a modal add-task hook that creates a project task with the requested `executionStage`.
- Replaced the marked-project start-mode radio area with a single orchestration entry button.
- Guarded `setProjectExecutionStartModeAction()` so marked projects cannot write legacy `projectExecutionStartMode`.
- Preserved existing non-marked project start-mode behavior and existing marked-project stage badges.
- Added `tests/check_project_orchestration_page_wiring.mjs` to lock down script loading order, modal entry wiring, refresh hooks, add-task stage propagation, and old-control isolation.

## Key Contracts

- Marked project boards expose the Figma-aligned orchestration modal as the editing surface.
- Marked project boards do not expose the legacy execution-order editor.
- Marked project boards do not expose the legacy project start-mode radio controls.
- Modal save, pause, resume, skip request, and skip decision actions refresh the canonical project projection after server mutation.
- Modal-created tasks preserve the `executionStage` selected by the focused orchestration module.
- The project board remains a thin transport and refresh layer; orchestration rendering and interactions stay in focused modules.

## Verification

```bash
node --check app/projects.js
```

Result: passed

```bash
node --check app/project-orchestration-api.js && node --check app/project-orchestration.js
```

Result: passed

```bash
node tests/check_project_orchestration_page_wiring.mjs
```

Result: `project orchestration page wiring checks passed`

```bash
node tests/check_project_marked_legacy_start_removed.mjs
```

Result: `marked project legacy start removal checks passed`

```bash
node tests/check_project_marked_frontend_legacy_fields.mjs
```

Result: `marked project frontend legacy-field checks passed`

```bash
node tests/check_project_orchestration_modal.mjs
```

Result: `project orchestration modal runtime contract ok`

```bash
node tests/check_project_orchestration_api_contract.mjs
```

Result: `project orchestration API contract checks passed`

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_css.py
```

Result: `5 passed in 0.11s`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
