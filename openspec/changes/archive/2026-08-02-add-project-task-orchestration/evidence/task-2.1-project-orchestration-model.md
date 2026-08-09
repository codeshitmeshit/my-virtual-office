# Task 2.1 Project Orchestration Model

## Scope

Implemented the pure stage-pipeline orchestration model helpers.

Code:

- `app/services/project_orchestration.py`

Tests:

- `tests/test_project_orchestration.py`

## Implemented Helpers

- Execution model marker: `stage_pipeline_v1`
- Orchestration states: `draft`, `starting`, `running`, `pausing`, `paused`, `blocked`, `completed`
- Default orchestration and skip-state constructors
- Positive execution-stage parsing and validation
- Full-assignment stage compaction
- Marked-project and orchestration-state validation
- Completed-stage lock detection
- Accepted terminal evaluation using task completion or approved orchestration skip
- Explicit separation from `reviewResult.status == skipped`
- Failed/blocked/unresolved-skip detection
- Active task projection from task states and active attempts
- Current-stage task grouping
- Project projection fields: `activeTaskIds`, `activeTaskCount`, `currentStage`, `orchestrationState`, `pauseReason`

## Boundary

`project_orchestration.py` is a pure domain module. It has no repository, HTTP, workspace, provider, subprocess, or notification dependencies.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration.py
```

Result:

```text
22 passed in 0.12s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration.py tests/test_project_orchestration_release_preflight.py tests/test_project_execution_legacy_characterization.py tests/test_execution_lifecycle.py tests/test_project_execution_ordering.py
```

Result:

```text
41 passed in 55.90s
```

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result:

```text
Change 'add-project-task-orchestration' is valid
```

```bash
npx --yes @fission-ai/openspec@latest instructions apply --change add-project-task-orchestration --json
```

Result:

```text
5 / 52 tasks complete
```
