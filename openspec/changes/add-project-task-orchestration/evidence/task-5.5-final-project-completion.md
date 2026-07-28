# Task 5.5 Evidence: Final Project Completion

## Scope

- Extended `reconcile_stage(projectId, currentRunId)` so the final stage completes the marked project when every current-stage task has an accepted terminal outcome.
- Final completion now records:
  - `orchestration.state = "completed"`
  - `orchestration.currentRunId = null`
  - `orchestration.completedAt`
  - `project.status = "completed"`
- Added an optional `on_project_completed(project, reason)` service port that runs only after the project completion update commits.
- Persisted notification markers copied from the notification callback back to the project, preserving existing Feishu dedupe markers.
- Kept notification delivery best-effort: callback exceptions return a failed notification payload without rolling back or failing the completed project reconciliation.
- Passed the project-complete notification callback through terminal reconciliation entry points and skip approval reconciliation.

## Human Acceptance Boundary

- Human acceptance remains represented as an ordinary pipeline task.
- A task with `executionState = "awaiting_user_acceptance"` and `requiresUserAcceptance = true` is not accepted terminal.
- Final project completion remains blocked with `stage_waiting` until that human-acceptance task reaches an accepted terminal outcome.

## Idempotency

- The first final-stage reconciliation for the active `(projectId, currentRunId)` completes the project and sends one project-completion notification.
- Replaying the same `currentRunId` after completion returns `stale_run_ignored` and does not send a second notification.
- Approving a skip on the final stage can complete the project and trigger the same project-complete notification path.

## Verification

Commands run:

```bash
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_orchestration_skip.py
.venv/bin/python -m py_compile app/services/project_stage_dispatch.py app/services/project_orchestration_skip.py app/server.py
.venv/bin/pytest -q tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py
```

Results:

- `tests/test_project_stage_dispatch.py tests/test_project_orchestration_skip.py`: 34 passed.
- `py_compile`: passed.
- Adjacent lifecycle/HTTP/review regression suite: 63 passed.

## Added Coverage

- Final-stage accepted tasks complete the project and set project status to completed.
- Final project completion notifies once and persists Feishu notification markers.
- Duplicate final-stage reconciliation is idempotent and does not notify twice.
- Notification failure is reported as `delivery_failed` while the project remains completed.
- Human acceptance pending task prevents final project completion.
- Final-stage skip approval completes the project and routes through project-completion notification.
