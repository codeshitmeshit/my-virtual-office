# Task 1.3 Legacy Characterization Tests

## Scope

Added focused failing-before characterization coverage for the legacy Project Execution behavior that will be intentionally replaced by stage orchestration.

Test file:

- `tests/test_project_execution_legacy_characterization.py`

## Covered Legacy Contracts

| Requirement from task 1.3 | Test coverage |
|---|---|
| single/continuous project start | `test_manual_task_start_is_single_mode_and_sets_singular_active_task`, `test_project_start_continuous_selects_one_execution_order_task_and_blocks_parallel_start` |
| unique execution order / order-driven eligibility | `test_execution_order_blocks_later_manual_task_until_prior_task_is_complete` |
| singular active-task projection | `test_manual_task_start_is_single_mode_and_sets_singular_active_task`, `test_project_start_continuous_selects_one_execution_order_task_and_blocks_parallel_start` |
| task-level manual start | `test_manual_task_start_is_single_mode_and_sets_singular_active_task`, `test_execution_order_blocks_later_manual_task_until_prior_task_is_complete` |
| completion-triggered next-task start | `test_project_start_after_completion_selects_next_single_task_by_execution_order` |
| restart recovery | `test_status_recovery_marks_non_live_singular_attempt_blocked` |
| scheduled execution | `test_project_cron_dispatch_passes_legacy_start_mode_to_project_start` |

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_execution_legacy_characterization.py
.venv/bin/python -m pytest -q tests/test_project_execution_legacy_characterization.py tests/test_execution_lifecycle.py tests/test_project_execution_ordering.py
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result:

```text
6 passed in 0.41s
17 passed in 39.22s
Change 'add-project-task-orchestration' is valid
```

## Notes For Later Migration

- These tests intentionally assert old fields such as `projectExecutionStartMode`, `projectExecutionFlowActive`, `workflowActive`, `workflowPhase`, `activeTaskId`, and `activeAgent`.
- They should fail or be rewritten when stage orchestration replaces single/free/manual progression.
- The cron characterization confirms legacy scheduled project execution passes the stored `projectExecutionStartMode` into project start; stage orchestration should replace this with explicit pipeline start semantics.
