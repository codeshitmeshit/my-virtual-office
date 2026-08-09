# Task 4.2 Evidence: Stage preflight and atomic reservation

Date: 2026-07-27

## Scope

Extended `app/services/project_stage_dispatch.py` with reusable stage-run preflight and atomic reservation.

The reservation command now:

- validates the stage-pipeline marker and contiguous stage invariants;
- checks optimistic orchestration `revision`;
- checks orchestration startability before reservation;
- runs whole-stage workspace validation and dirty-worktree confirmation before the repository lock;
- resolves executor/reviewer roles for every task in the requested stage;
- checks management/owner authorization through an injected port;
- rejects active or already reserved tasks before starting new stage work;
- revalidates pure project state inside `ProjectRepository.update`;
- atomically writes one `currentRunId` to `orchestration.currentRunId` and the same run id to every task in the stage;
- leaves later-stage tasks unreserved.

This task intentionally does not create task attempts or invoke providers. Follow-up task 4.3 will use the reservation result to create per-task attempts concurrently and idempotently.

## Files

- `app/services/project_stage_dispatch.py`
- `tests/test_project_stage_dispatch.py`

## Verification

Focused dispatcher and reservation regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py
12 passed in 0.26s
```

Adjacent orchestration regression:

```text
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_http.py
47 passed in 1.04s
```

Compilation check:

```text
.venv/bin/python -m py_compile app/services/project_stage_dispatch.py
```

## Notes

- External workspace, Git, role, and authorization checks happen outside the project repository lock.
- The lock-internal recheck is deliberately pure and guards against stale revision, changed workspace path, stage changes, active attempts, and existing stage reservations before the atomic write.
