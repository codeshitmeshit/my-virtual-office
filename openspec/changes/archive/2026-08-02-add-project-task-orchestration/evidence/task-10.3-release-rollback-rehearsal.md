# Task 10.3 Release And Rollback Rehearsal Evidence

## Added Rehearsal Tool

- `scripts/project_orchestration_release_rehearsal.py`
  - Runs a non-destructive maintenance-window rehearsal in an isolated temporary
    directory.
  - Copies the current status directory into a deploy sandbox.
  - Runs the read-only legacy-project preflight and marked-project stage
    invariant checks before accepting project mutations.
  - Verifies coordinated backend/frontend activation by compiling backend
    orchestration modules and checking that `app/index.html` includes the
    orchestration CSS/API/runtime assets.
  - Writes a temporary marked `stage_pipeline_v1` project into the sandbox,
    reloads it through `MarkdownProjectStore`, checks contiguous stages, and
    verifies removed legacy authorities are absent.
  - Starts and stops an isolated loopback service process to rehearse the stop
    control without interrupting the developer service.
  - Resolves the previous code ref for rollback.
  - Restores the 10.2 project-store backup into a rollback sandbox and reruns
    preflight to prove data rollback can recover the pre-release legacy records.
- `tests/test_project_orchestration_release_rehearsal.py`
  - Covers the CLI happy path with an empty cleaned status dir and a backup
    containing three legacy project records.

## Rehearsal Command

```bash
.venv/bin/python scripts/project_orchestration_release_rehearsal.py --status-dir /home/cosh/my-virtual-office/data --backup-dir /home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z
```

Result:

- Top-level `ok`: `true`
- `readOnlyToRealStatusDir`: `true`
- Current status dir:
  `/home/cosh/my-virtual-office/data`
- Project-store backup:
  `/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z`
- Release code ref:
  `9dae196dd79e57ab12300fe2667f996dc59bbfb9`
- Previous rollback code ref:
  `b2b66e21a4d3214a67be8d7bc5c5de5533137a53`

## Gate Results

Pre-mutation invariant and preflight:

- `canonicalProjectCount`: `0`
- `legacyDeletionCandidateCount`: `0`
- `readErrorCount`: `0`
- Marked project invariant status: `ok`
- Marked project count before smoke: `0`

Coordinated backend/frontend activation:

- Backend compile check: `ok`
  - `app/server.py`
  - `app/services/project_orchestration.py`
  - `app/services/project_orchestration_commands.py`
  - `app/services/project_stage_dispatch.py`
  - `app/services/project_orchestration_recovery.py`
- Frontend asset check: `ok`
  - `project-orchestration.css`
  - `project-orchestration-api.js`
  - `project-orchestration.js`

New-project smoke in the deploy sandbox:

- `projectId`: `release-rehearsal-project`
- `executionModel`: `stage_pipeline_v1`
- `orchestrationState`: `draft`
- `taskCount`: `3`
- `stages`: `[1, 2]`
- `forbiddenProjectFields`: `[]`
- `tasksWithExecutionOrder`: `[]`
- Post-smoke marked project invariant status: `ok`

Service stop rehearsal:

- Isolated loopback process started healthy.
- The process was stopped.
- Post-stop connection was refused.
- Result: `ok`

Rollback rehearsal:

- Previous code ref `HEAD^` resolved to
  `b2b66e21a4d3214a67be8d7bc5c5de5533137a53`.
- The 10.2 backup was restored into a rollback sandbox.
- Post-restore preflight:
  - `canonicalProjectCount`: `3`
  - `legacyDeletionCandidateCount`: `3`
  - `readErrorCount`: `0`
- Post-restore invariant status: `ok`
- This proves rollback must restore the project-store backup in addition to
  previous code; code-only rollback would not recover the pre-release legacy
  records.

## Automated Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_release_rehearsal.py tests/test_project_orchestration_release_preflight.py
```

Result:

- `3 passed in 2.25s`

```bash
.venv/bin/python -m py_compile scripts/project_orchestration_release_rehearsal.py
```

Result:

- Passed.

```bash
git diff --check -- scripts/project_orchestration_release_rehearsal.py tests/test_project_orchestration_release_rehearsal.py
```

Result:

- Passed.

## Notes

- The rehearsal is intentionally non-destructive to the real status directory:
  all project mutation, service stop, and project-store restore steps run in
  temporary sandboxes.
- The real 10.2 backup remains available at
  `/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z`.
