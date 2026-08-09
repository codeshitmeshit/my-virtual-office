# Task 8.3 Evidence: Isolated Modal Runtime

## Scope

- Added `app/project-orchestration.js` as a focused browser/runtime module for the orchestration modal.
- Loaded the module in `app/index.html` before the project board entry script.
- Implemented task/stage view-model construction from canonical `executionStage` and `orchestration` fields.
- Implemented isolated modal rendering with scoped `project-orchestration-*` classes that match the task 8.2 CSS shell.
- Implemented lifecycle cleanup for Escape, backdrop close, close/reopen replacement, previous-focus restoration, and current-session lookup.
- Implemented fit-canvas scaling against the Figma reference canvas width while preserving the existing Press Start 2P styled shell through scoped class names.
- Added `tests/check_project_orchestration_modal.mjs` to cover the runtime contract without coupling to the legacy project board script.

## Key Contracts

- Stages are grouped from positive `executionStage` values and sorted ascending.
- Tasks inside a stage sort by `order`, `createdAt`, then `id`.
- State labels normalize execution/review/done/blocked/backlog display states.
- The modal root is self-contained, receives `role="dialog"` and `aria-modal="true"`, and stores `data-project-id`.
- `open()` replaces any existing session, `close()` removes document listeners and overlay DOM, and `reopen()` leaves exactly one modal mounted.
- `fitCanvas()` clamps scale to `0.500..1.000`, writes inline transform state, and records `data-fit-scale`.
- The removed save action remains represented by `.project-orchestration-save` for CSS hiding and later removal verification.

## Verification

```bash
node --check app/project-orchestration.js
```

Result: passed

```bash
node tests/check_project_orchestration_modal.mjs
```

Result: `project orchestration modal runtime contract ok`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
