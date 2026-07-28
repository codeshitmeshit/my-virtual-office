# Task 3.2 Evidence: Task create/delete structural edits

Date: 2026-07-27

## Scope

Updated task creation and deletion commands for marked stage-pipeline projects:

- `create_task` rejects ordinary task creation when the marked project's orchestration state is not editable.
- `create_task` keeps using canonical task materialization, so modal-created tasks default to `max(existing executionStage) + 1`.
- `create_task` increments `orchestration.revision` for marked projects because adding a task changes the editable orchestration shape.
- `delete_task` rejects ordinary task deletion when the marked project's orchestration state is not editable.
- `delete_task` rejects deleting completed-stage history while a paused project is being re-orchestrated.
- `delete_task` atomically removes the task, compacts remaining stages, updates task timestamps, and increments `orchestration.revision`.
- Added a pure `compact_stages_after_removal` helper in `project_orchestration.py`.

## Verification

Focused command/model regression:

```text
.venv/bin/pytest -q tests/test_project_commands.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py
48 passed in 0.61s
```

Wider project, materialization, and authoring regression:

```text
.venv/bin/pytest -q tests/test_project_commands.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_materialization.py tests/test_project_materialization_characterization.py tests/test_project_authoring_service.py tests/test_project_authoring_direct_create.py
117 passed in 2.74s
```

OpenSpec validation:

```text
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```

## Notes

- Existing creation-source characterization now treats `orchestration.revision` as a mutable concurrency token. Pure materialization sources still start at revision 0, while command-created tasks bump the revision because they are post-creation structural edits.
