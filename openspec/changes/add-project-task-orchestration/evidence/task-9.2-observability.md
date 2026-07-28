# Task 9.2 Observability Evidence

## Scope

Added structured orchestration diagnostics for:

- reservations
- dispatcher submissions
- queue rejection
- duplicate terminal callback suppression
- stage advancement and final completion
- phase-one and phase-two pause
- skip decisions
- startup recovery
- auto-save revision conflicts
- stuck-state detection

Each diagnostic payload carries bounded `counters`, `timings`, and `audit` fields with project, task, stage, run, attempt, and revision context where available.

## Verification

- `.venv/bin/python -m py_compile app/services/project_orchestration_observability.py app/services/project_stage_dispatch.py app/services/project_orchestration_commands.py app/services/project_orchestration_pause.py app/services/project_orchestration_skip.py app/services/project_orchestration_recovery.py`
  - Result: passed.
- `.venv/bin/python -m pytest -q tests/test_project_orchestration_observability.py`
  - Result: `4 passed in 0.11s`.
- `.venv/bin/python -m pytest -q tests/test_project_orchestration_observability.py tests/test_project_orchestration_concurrency.py tests/test_project_stage_dispatch.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_pause.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_recovery.py`
  - Result: `69 passed in 0.77s`.

## OpenSpec CLI Check

- `openspec status --change add-project-task-orchestration --json`
  - Result: blocked by local environment, `openspec: command not found`.
- `openspec instructions apply --change add-project-task-orchestration --json`
  - Result: blocked by local environment, `openspec: command not found`.
- `npx --yes @openspec/cli validate add-project-task-orchestration --strict`
  - Result: npm 404, package not found.
- `npx --yes openspec validate add-project-task-orchestration --strict`
  - Result: npm could not determine executable to run.

OpenSpec artifacts were still updated directly in this change directory after reading the local task list.

