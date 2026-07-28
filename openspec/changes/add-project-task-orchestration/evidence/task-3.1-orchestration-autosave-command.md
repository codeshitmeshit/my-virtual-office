# Task 3.1 Evidence: Orchestration auto-save command

Date: 2026-07-27

## Scope

Added `app/services/project_orchestration_commands.py` as the repository-backed command boundary for one full-assignment orchestration auto-save.

The command now:

- requires the project to be marked with `executionModel: stage_pipeline_v1`;
- accepts only complete full-project assignments, one per task;
- rejects duplicate, unknown, missing, and invalid task-stage assignments;
- checks optimistic `orchestration.revision` and returns HTTP-style 409 payloads with authoritative revision and assignments on stale writes;
- allows edits only while orchestration state is `draft` or `paused`;
- rejects reassignment of completed-stage task history;
- normalizes sparse positive stages into contiguous stages beginning at 1;
- persists all task `executionStage` updates and increments `orchestration.revision` in one repository update.

## Verification

Focused command/model/storage regression:

```text
.venv/bin/pytest -q tests/test_project_orchestration_commands.py tests/test_project_orchestration.py tests/test_project_orchestration_store.py
32 passed in 0.49s
```

Wider project command/materialization regression:

```text
.venv/bin/pytest -q tests/test_project_orchestration_commands.py tests/test_project_orchestration.py tests/test_project_orchestration_store.py tests/test_project_commands.py tests/test_project_materialization.py tests/test_project_materialization_characterization.py
72 passed in 2.56s
```

OpenSpec validation:

```text
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```

## Notes

- The command returns `ServiceResult` payloads through an `OrchestrationCommandOutcome`, matching existing transport-independent command style while keeping this orchestration boundary out of `project_commands.py`.
- Persistence exceptions are not swallowed in this task; the repository write remains atomic and the future route delegate in task 3.3 owns HTTP persistence-failure mapping.
