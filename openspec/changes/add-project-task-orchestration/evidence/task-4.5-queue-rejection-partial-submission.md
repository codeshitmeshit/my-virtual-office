# Task 4.5 Evidence: Queue rejection and partial submission

Date: 2026-07-27

## Scope

Added bounded-queue rejection handling for marked project stage start.

The marked start path now:

- preserves already submitted current-stage tasks as active/executing truth;
- records a rejected dispatch submission as durable `dispatch_queue_full`;
- marks the affected task blocked and clears its active attempt because no provider work was admitted;
- marks the rejected attempt record blocked with `blockedReason: dispatch_queue_full`;
- moves orchestration to `blocked` with `pauseReason: dispatch_queue_full`;
- keeps `currentRunId` and `currentStage` unchanged so later-stage tasks remain locked;
- leaves later-stage tasks unreserved and unstarted.

## Files

- `app/services/project_stage_dispatch.py`
- `tests/test_project_stage_dispatch.py`
- `tests/test_project_stage_start_server.py`

## Verification

Focused dispatcher and server adapter regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
23 passed in 0.67s
```

Adjacent orchestration regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_http.py
58 passed in 1.30s
```

Compilation check:

```text
.venv/bin/python -m py_compile app/services/project_stage_dispatch.py app/server.py
```

## Notes

- This handles queue admission failure after some tasks in the same stage have already been admitted.
- Stage advancement and terminal reconciliation remain future work under task 5.1 and related callback migration tasks.
