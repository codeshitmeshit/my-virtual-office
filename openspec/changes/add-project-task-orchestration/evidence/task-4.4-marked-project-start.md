# Task 4.4 Evidence: Marked project start

Date: 2026-07-27

## Scope

Wired marked Project Execution start to the stage orchestration path.

The marked project start path now:

- ignores legacy `mode`, `startMode`, and `restartPipeline` progression selection;
- reserves the first/current stage through `reserve_stage_run`;
- aggregates reservation preflight blockers before mutation;
- prepares task-level attempts for every reserved current-stage task;
- submits every prepared attempt to the bounded dispatcher;
- returns `stage_started` with `runId`, `currentStage`, task ids, attempts, and submission diagnostics;
- rejects per-task start for marked projects with `marked_project_task_start_forbidden`.

The server remains a thin adapter. Stage reservation, attempt preparation, and submission orchestration live in `app/services/project_stage_dispatch.py`.

## Files

- `app/services/project_stage_dispatch.py`
- `app/server.py`
- `tests/test_project_stage_dispatch.py`
- `tests/test_project_stage_start_server.py`

## Verification

Focused marked-stage start and adjacent orchestration regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_http.py
56 passed in 1.33s
```

Compilation check:

```text
.venv/bin/python -m py_compile app/services/project_stage_dispatch.py app/server.py
```

## Additional check

The legacy `tests/test_project_execution.py -k "project_level_start or direct_task_start or skip_reviewer_confirmation or dirty"` subset was run as an exploratory compatibility check and failed because those tests create newly marked projects but still assert the old single-task/manual start contract. This is expected drift for this OpenSpec change and is not used as pass evidence for task 4.4.

## Notes

- Queue rejection is surfaced but not yet converted into durable `dispatch_queue_full` task blocking or stage pause; that is task 4.5.
- Provider execution is launched by the bounded dispatcher runner after successful submission.
