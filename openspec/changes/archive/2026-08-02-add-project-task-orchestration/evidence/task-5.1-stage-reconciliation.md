# Task 5.1 Evidence: Idempotent Stage Reconciliation

## Scope

- Added `reconcile_stage(project_id, run_id, ...)` in `app/services/project_stage_dispatch.py`.
- The reconciliation key is `(projectId, currentRunId)`: stale callbacks for an old run return `stale_run_ignored`.
- The current run advances only when every task in the current stage has an accepted terminal outcome.
- Advancing reserves the next stage under a fresh `currentRunId` and assigns that run id to every next-stage task.
- Final-stage accepted outcomes mark orchestration `completed`; project-level final notification and full completion semantics remain covered by task 5.5.

## Tests Added

- `test_reconcile_stage_waits_until_every_current_stage_task_is_accepted_terminal`
- `test_reconcile_stage_advances_current_run_once_and_ignores_duplicate_callback`
- `test_reconcile_stage_serializes_parallel_terminal_callbacks_to_one_advancement`
- `test_reconcile_stage_completes_orchestration_when_final_stage_is_accepted_terminal`

## Verification

```bash
.venv/bin/pytest -q tests/test_project_stage_dispatch.py
```

Result: `24 passed in 0.50s`

```bash
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_http.py
```

Result: `62 passed in 1.38s`

```bash
.venv/bin/python -m py_compile app/services/project_stage_dispatch.py app/server.py
```

Result: passed with no output.

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest instructions apply --change add-project-task-orchestration
```

Result: `19/52 complete`
