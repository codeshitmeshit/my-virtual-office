# Task 8.4 Evidence: Drag/Add Auto-Save Runtime

## Scope

- Extended `app/project-orchestration.js` with isolated drag/drop handling for task cards and stage drop zones.
- Added optimistic task stage movement with positive contiguous stage normalization before persistence.
- Wired completed drag edits through `ProjectOrchestrationAPI.saveCompletedDrag` so a finished move performs one full-assignment auto-save call.
- Added visible modal status state for saving, saved, error, and conflict results.
- Added HTTP 409 handling that applies authoritative `assignments`, `orchestration`, `currentRevision`, or `project` payloads back into the rendered modal.
- Added add-task interaction support through `options.onAddTask`, passing `executionStage = max(existingStage) + 1`.
- Kept the runtime isolated from `projects.js`; the project page wiring remains a later task.
- Added small scoped CSS status/drag affordance rules in `app/project-orchestration.css`.

## Key Contracts

- Drag/drop mutates only the isolated modal session project copy before auto-save.
- Stage numbers remain positive and contiguous after moving a task out of a stage.
- A completed drag calls `saveCompletedDrag()` exactly once with a full `{ taskId, executionStage }` assignment list.
- Rejected writes leave the modal in `has-error` and are never marked saved.
- Revision conflicts leave the modal in `has-conflict` and reload authoritative assignments/revision from the API result.
- Add task delegates to the caller with project id, current revision, and default maximum-stage-plus-one placement.

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
node tests/check_project_orchestration_api_contract.mjs
```

Result: `project orchestration API contract checks passed`

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_css.py
```

Result: `5 passed in 0.12s`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
