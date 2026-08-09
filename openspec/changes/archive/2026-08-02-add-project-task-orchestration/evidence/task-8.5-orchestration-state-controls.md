# Task 8.5 Evidence: Orchestration State Controls

## Scope

- Extended `app/project-orchestration.js` view models with `locked`, `canEdit`, `canPause`, `canResume`, `completed`, `activeTaskIds`, and `pauseReason` projections from canonical orchestration state.
- Locked running, starting, pausing, and completed modals against drag/drop and add-task edits.
- Kept draft, paused, and blocked modals editable for re-orchestration workflows.
- Added pause and resume controls driven by orchestration state.
- Added task skip-request, skip-approve, and skip-reject controls without adding any legacy free-mode, project start-mode, or per-task start controls.
- Extended `app/project-orchestration-api.js` with pause, resume, skip-request, and skip-decision POST helpers for the existing backend routes.
- Added task-card skip-state rendering for requested, approved, and rejected skip decisions.
- Added scoped CSS for disabled controls, skip-state chips, skip actions, and locked/completed affordances.

## Key Contracts

- Running/starting/pausing/completed projects are not editable in the modal.
- Moving a task in a locked state returns `orchestration_locked` and performs no auto-save.
- Pause is exposed only for running/starting projects.
- Resume is exposed only for paused/blocked projects.
- Completed projects keep skip/add/edit controls disabled.
- Skip decisions update the task's authoritative `orchestrationSkip` state in the rendered modal.
- The focused modal module still does not expose free-mode, start-mode, restart-pipeline, or per-task start controls.

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

Result: `5 passed in 0.07s`

```bash
node tests/check_project_marked_legacy_start_removed.mjs
```

Result: `marked project legacy start removal checks passed`

```bash
node tests/check_project_marked_frontend_legacy_fields.mjs
```

Result: `marked project frontend legacy-field checks passed`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
