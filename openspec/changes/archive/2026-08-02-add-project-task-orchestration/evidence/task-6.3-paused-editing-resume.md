# Task 6.3 Evidence: Paused Editing and Resume

## Scope

- Updated `autosave_orchestration(...)` so paused-project edits preserve completed history and normalize unfinished tasks after the last completed stage.
- Added `resume_paused_project(...)` to `app/services/project_stage_dispatch.py` as the explicit resume command boundary before HTTP delegates are introduced.
- Resume only accepts projects in `orchestration.state = "paused"`.
- Resume chooses `next_unfinished_stage(project)` regardless of any client-supplied stage and then reuses the existing stage reservation, attempt preparation, and bounded dispatch path.

## Paused Editing Rules

- Completed tasks in completed stages remain locked to their original `executionStage`.
- Unfinished task assignments are normalized independently and offset by `last_completed_stage(project)`, so they form a contiguous sequence after completed history.
- A client cannot move unfinished tasks back into completed stages by submitting low stage numbers.
- Existing task create/delete command coverage remains aligned: paused projects are editable, non-editable states reject structural edits, and completed-stage task deletion is blocked.

## Explicit Resume Rules

- Resume rejects non-paused projects with `orchestration_not_resumable`.
- Resume rejects fully completed paused projects with `no_unfinished_stage`.
- Resume starts the first unfinished stage using a new stage run ID.
- Resumed unfinished tasks receive fresh attempts and are dispatched through the bounded dispatcher.
- Prior cancelled attempts remain in task attempt history; completed tasks keep their original completed outcome and run history.

## Verification

Commands run:

```bash
.venv/bin/pytest -q tests/test_project_orchestration_commands.py tests/test_project_stage_dispatch.py
.venv/bin/pytest -q tests/test_project_commands.py tests/test_project_orchestration_commands.py tests/test_project_stage_dispatch.py
.venv/bin/python -m py_compile app/services/project_orchestration_commands.py app/services/project_stage_dispatch.py app/services/project_commands.py
.venv/bin/pytest -q tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_pause.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py tests/test_project_commands.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py
```

Results:

- Focused orchestration command/stage dispatch suite: 39 passed.
- Project command + orchestration command + stage dispatch suite: 57 passed.
- Adjacent lifecycle/review/HTTP regression suite: 124 passed.
- `py_compile`: passed.

## Added Coverage

- Paused auto-save keeps completed tasks at stages 1..N and moves unfinished tasks to N+1...
- Paused auto-save rejects attempts to reassign completed-stage history.
- Resume starts the first unfinished stage even when the request body includes a later stage.
- Resume appends fresh attempts while preserving previous cancelled attempt history.
- Resume rejects running projects and paused projects with no unfinished work.
