# Task 6.4 Evidence: Pause/Resume Transport Delegates

## Scope

- Added thin server delegates for marked-project pause and resume orchestration.
- Added management-token-protected routes:
  - `POST /api/projects/{projectId}/orchestration/pause`
  - `POST /api/projects/{projectId}/orchestration/resume`
- Pause transport runs phase one and phase two in sequence:
  - phase one records `pausing` and captures active attempts;
  - phase two calls provider cancellation outside the project lock and converges to `paused` when all cancellations succeed.
- Resume transport delegates to `resume_paused_project(...)`, reusing stage preflight, stage reservation, attempt preparation, bounded dispatch, and new cancel-flag registration.

## Route Semantics

- Both routes require the existing management token before mutation.
- Pause requires explicit confirmation through the phase-one service.
- Pause cancellation failure returns HTTP 409 with `pause_cancellation_failed` and leaves the project in `pausing` for retry.
- Repeated pause after the project is already `paused` returns the phase-two idempotent `paused` response without re-sending provider cancellation.
- Resume rejects non-paused projects with `orchestration_not_resumable`.
- Resume ignores forged/requested later stages and starts the first unfinished stage through the domain service.

## Verification

Commands run:

```bash
.venv/bin/pytest -q tests/test_project_orchestration_http.py
.venv/bin/python -m py_compile app/server.py app/services/project_orchestration_pause.py app/services/project_stage_dispatch.py
.venv/bin/pytest -q tests/test_project_orchestration_http.py tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_skip.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py
.venv/bin/pytest -q tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_commands.py tests/test_project_orchestration_http.py tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py
```

Results:

- Focused HTTP route suite: 17 passed.
- Adjacent pause/stage/skip/lifecycle/review suite: 81 passed.
- Broader orchestration/project-command suite: 105 passed.
- `py_compile`: passed.

## Added Coverage

- Pause route rejects missing management token before mutation.
- Pause route cancels active attempts and enters `paused`.
- Pause route preserves `pausing` on provider cancellation failure.
- Pause route is idempotent after the project is already `paused`.
- Resume route rejects missing management token before mutation.
- Resume route starts a paused project's first unfinished stage with a fresh run and attempt.
- Resume route rejects non-paused projects without mutation.
