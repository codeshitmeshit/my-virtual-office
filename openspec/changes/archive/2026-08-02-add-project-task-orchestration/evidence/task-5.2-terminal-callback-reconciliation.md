# Task 5.2 Evidence: Terminal Callback Stage Reconciliation

## Scope

- Added stage-aware terminal callback ports to `execution_lifecycle` and `review_acceptance`.
- Marked projects call the server adapter `_project_stage_reconcile_terminal(...)`, which resolves the task attempt `stageRunId` and calls `project_stage_dispatch.reconcile_stage(...)`.
- Marked execution completion, skipped-review completion, review pass, user acceptance, checklist-completion continuation, and meeting-resolution continuation no longer schedule legacy single-next-task progression.
- Legacy projects keep the existing `schedule_continue` behavior through the default port implementations.
- Marked review start and acceptance rework checks no longer use the singular active-task blocker, allowing parallel current-stage tasks to progress through review/acceptance independently.

## Tests Added

- `test_marked_project_terminal_attempt_reconciles_instead_of_scheduling_legacy_continue`
- `test_marked_project_acceptance_reconciles_stage_without_legacy_continue`
- `test_marked_project_terminal_adapter_reconciles_attempt_stage_run`

## Verification

```bash
.venv/bin/pytest -q tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py tests/test_project_stage_start_server.py tests/test_project_stage_dispatch.py
```

Result: `42 passed in 59.66s`

```bash
.venv/bin/pytest -q tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_execution_service_boundary.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_http.py
```

Result: `102 passed in 62.03s`

```bash
.venv/bin/python -m py_compile app/services/execution_lifecycle.py app/services/review_acceptance.py app/services/project_stage_dispatch.py app/server.py
```

Result: passed with no output.

## Legacy Characterization Note

```bash
.venv/bin/pytest -q tests/test_project_execution.py -k "checklist_completion_after_review or checklist_completion_does_not_bypass_user_acceptance or continuous_flow_auto_continues_when_task_does_not_require_acceptance or user_acceptance"
```

Result: `3 passed, 2 failed, 103 deselected`.

The two failures are legacy assertions that create newly marked projects while expecting old task-level/manual continuous behavior. This matches the previously recorded 4.4 compatibility note and is not used as pass evidence for marked-project orchestration.
