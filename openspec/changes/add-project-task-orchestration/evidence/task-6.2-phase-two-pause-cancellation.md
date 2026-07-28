# Task 6.2 Evidence: Phase-Two Pause Cancellation

## Scope

- Extended `app/services/project_orchestration_pause.py` with `complete_phase_two_pause(...)`.
- Phase two starts from the `orchestration.pauseSnapshot` produced by task 6.1.
- Provider cancellation runs before the repository update through an injected `cancel_attempt` port, keeping provider work outside the project lock.
- If any captured attempt cancellation fails, the project remains in `pausing` and no project mutation is committed.
- If all captured attempts cancel successfully, a single repository update converges the project to `orchestration.state = "paused"`.

## Atomic Convergence

On successful convergence:

- Captured active attempts are updated in-place to `status = "cancelled"` with `cancelledAt`, `finishedAt`, and per-attempt `cancelResult`.
- Unfinished captured tasks clear `activeAttemptId`, clear `stageRunId`, clear transient blocker/error fields, and return to `executionState = "pending"`.
- Attempt/workspace history is preserved in the task's existing `attempts` list.
- Completed tasks keep their completed outcome and original stage/run history; they are not returned to pending.
- `orchestration.currentRunId` is cleared, `orchestration.revision` increments, and cancellation evidence is recorded under `pauseSnapshot.cancelResults`, `pauseSnapshot.cancelledAttempts`, and `pauseSnapshot.convergedAt`.
- Re-running phase two after the project is already `paused` is idempotent and does not re-send provider cancellation.

## Verification

Commands run:

```bash
.venv/bin/pytest -q tests/test_project_orchestration_pause.py
.venv/bin/python -m py_compile app/services/project_orchestration_pause.py
.venv/bin/pytest -q tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py
.venv/bin/pytest -q tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py
.venv/bin/python -m py_compile app/services/project_orchestration_pause.py app/services/project_orchestration.py app/services/project_stage_dispatch.py
```

Results:

- Focused pause suite: 8 passed.
- Core orchestration/stage/HTTP suite: 89 passed.
- Adjacent lifecycle/review/skip/HTTP suite: 69 passed.
- `py_compile`: passed.

## Added Coverage

- Phase-two cancellation invokes the provider cancellation port for each captured attempt before convergence.
- Successful cancellation records cancelled attempts and returns unfinished tasks to pending.
- Completed captured tasks preserve completed outcome and stage/run history.
- Cancellation failure leaves the project in `pausing` without committing partial state changes.
- Already-paused convergence is idempotent and skips provider cancellation.
