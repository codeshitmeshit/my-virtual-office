# Task 6.1 Evidence: Phase-One Pause Command

## Scope

- Added `app/services/project_orchestration_pause.py` as a focused repository-backed command module.
- Implemented `request_phase_one_pause(projectId, body, repository, ports)` for marked stage-pipeline projects.
- The command requires an explicit confirmation flag (`confirm`, `confirmed`, or `confirmPause`) before mutating state.
- Authorized confirmed requests atomically enter `orchestration.state = "pausing"`, preserve `currentStage` and `currentRunId`, set `pauseReason`, increment `orchestration.revision`, and update `project.updatedAt`.
- Active unfinished attempts are snapshotted into `orchestration.pauseSnapshot` with both `activeAttemptIds` and task/attempt metadata for phase-two cancellation.
- Repeated requests while already `pausing` are idempotent and return the existing snapshot without incrementing revision.
- `orchestration_state()` now preserves extension fields such as `pauseSnapshot` so later orchestration updates do not silently drop phase-one pause data.

## Dispatch and Advancement Freeze

- `reserve_stage_run` already rejects `pausing` projects as not startable; added coverage proving no new stage dispatch reservation is made while pausing.
- `reconcile_stage` now treats a matching current run on a `pausing` project as `stage_pausing` and does not advance to the next stage or complete the project.
- Phase-two provider cancellation and transition to `paused` remain out of scope for this task and are covered by task 6.2.
- Pause/resume HTTP delegates remain out of scope for this task and are covered by task 6.4.

## Verification

Commands run:

```bash
.venv/bin/pytest -q tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py
.venv/bin/python -m py_compile app/services/project_orchestration.py app/services/project_orchestration_pause.py app/services/project_stage_dispatch.py
.venv/bin/pytest -q tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py
.venv/bin/pytest -q tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py
```

Results:

- Focused pause/stage dispatch suite: 32 passed.
- `py_compile`: passed.
- Model/command/pause/stage dispatch suite: 63 passed.
- Adjacent lifecycle, HTTP, skip, and review regression suite: 99 passed.

## Added Coverage

- Explicit confirmation is required before entering `pausing`.
- Confirmed pause snapshots active attempt IDs and active attempt metadata while leaving task attempts active for phase-two cancellation.
- Already-pausing requests are idempotent and reuse the stored snapshot.
- Unauthorized and non-pausable projects reject without mutation.
- Stage reconciliation does not advance while the project is pausing.
- New dispatch reservation is rejected while the project is pausing.
