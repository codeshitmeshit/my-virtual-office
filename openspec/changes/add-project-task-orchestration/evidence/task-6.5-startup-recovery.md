# Task 6.5 Evidence: Startup recovery

Implemented run-aware startup recovery for marked stage-pipeline projects.

The recovery path now:

- scans marked projects left in `starting`, `running`, or `pausing`;
- repeats phase-two pause convergence for `pausing` projects without dispatching new work;
- preserves live current-stage attempts by checking the in-process cancel/review registries;
- restores a missing `activeAttemptId` when a live current-run attempt is durable but the pointer is absent;
- resubmits pure reserved current-stage tasks that have no attempt history under the same `currentRunId`;
- blocks non-live active current-run attempts with `stage_attempt_not_resumable_after_restart`;
- avoids duplicate attempts by refusing to create another attempt when the current run already has one.

Changed files:

- `app/services/project_orchestration_recovery.py`
- `app/server.py`
- `tests/test_project_orchestration_recovery.py`

Verification:

```text
.venv/bin/python -m pytest -q tests/test_project_orchestration_recovery.py
....                                                                     [100%]
4 passed in 0.27s

.venv/bin/python -m py_compile app/services/project_orchestration_recovery.py app/server.py
passed

.venv/bin/python -m pytest -q tests/test_project_orchestration_recovery.py tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
...............................................                          [100%]
47 passed in 1.26s

.venv/bin/python -m pytest -q tests/test_project_orchestration_http.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py
...............................                                          [100%]
31 passed in 44.93s

npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```

Notes:

- `npx --yes @fission-ai/openspec@latest apply add-project-task-orchestration --status` is not available in the current CLI; the supported status command is `openspec status --change add-project-task-orchestration`.
