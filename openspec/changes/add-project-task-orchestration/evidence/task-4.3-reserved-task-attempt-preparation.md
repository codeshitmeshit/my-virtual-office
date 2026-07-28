# Task 4.3 Evidence: Reserved task attempt preparation

Date: 2026-07-27

## Scope

Extended `app/services/project_stage_dispatch.py` with reserved task attempt preparation for stage orchestration.

The new preparation path:

- only accepts tasks already reserved by the current `orchestration.currentRunId`;
- creates task-level attempts keyed by `stageRunId`;
- returns the existing active attempt idempotently for the same `(projectId, taskId, currentRunId)`;
- allows multiple tasks in the same current stage to hold active attempts concurrently;
- rejects mismatched run ids, unreserved tasks, and active attempts owned by another run;
- sets task execution state through the injected transition port;
- does not write singular project-level authorities such as `activeTaskId`, `activeAgent`, or `projectExecutionFlowActive`.

This task intentionally does not wire the project-start route to reservation and dispatch. Follow-up tasks 4.4 and 4.5 connect project start, bounded queue submission, queue rejection, and partial-submission handling.

## Files

- `app/services/project_stage_dispatch.py`
- `tests/test_project_stage_dispatch.py`

## Verification

Focused dispatcher, reservation, and reserved-attempt regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py
17 passed in 0.17s
```

Adjacent orchestration regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_http.py
52 passed in 2.65s
```

Compilation check:

```text
.venv/bin/python -m py_compile app/services/project_stage_dispatch.py
```

## Notes

- The function is intentionally independent of provider launch and cancel-registry creation. It prepares durable attempt state; later dispatch tasks can enqueue provider work using the returned attempt id.
- Rejection paths raise internal exceptions inside `ProjectRepository.update` so failed preparation does not commit an unchanged or partially changed project snapshot.
