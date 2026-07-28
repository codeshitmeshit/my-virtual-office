# Task 8.7 Evidence: DOM Runtime Test Matrix

## Scope

- Extended `tests/check_project_orchestration_modal.mjs` into the focused DOM/runtime matrix for the orchestration modal.
- Covered modal rendering, view-model stage grouping, task state labels, close cleanup, Escape close, reopen replacement, and fit-canvas scaling.
- Covered direct drag completion and DOM drop-event drag completion.
- Covered auto-save success, validation failure, and stale-revision conflict authoritative reload.
- Covered add-task default placement at `max(executionStage) + 1`.
- Covered locked/running state behavior, pause to re-orchestration, blocked resume, skip request, skip approval, completed-state disabling, and absence of a manual save button.
- Removed the residual `.project-orchestration-save` button from `app/project-orchestration.js` so the auto-save-only UX is represented in DOM, not merely hidden by CSS.
- Re-ran page wiring, API, legacy-control, and CSS checks to prove the expanded runtime matrix stays compatible with earlier frontend tasks.

## Key Contracts

- The modal does not render a manual save action.
- Completed drag/drop performs exactly one full-assignment auto-save.
- Rejected auto-save responses show error state and are not presented as saved.
- Conflict responses reload authoritative assignments/revision and show conflict state.
- Locked projects do not allow drag/drop or add-task mutation.
- Pause/resume and skip decision controls update the modal from authoritative mutation results.

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
.venv/bin/python -m pytest -q tests/test_project_orchestration_css.py
```

Result: `5 passed in 0.19s`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
