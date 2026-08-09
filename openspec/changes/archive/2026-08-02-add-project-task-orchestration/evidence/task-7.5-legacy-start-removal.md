# Task 7.5 Evidence: marked-project legacy start removal

## Scope

Removed marked-project support for legacy project execution start controls and payloads:

- `mode`
- `startMode`
- `restartPipeline`
- task-level start
- manual next-task progression

Unmarked legacy projects retain their old workflow behavior until the remaining legacy flow is fully removed.

## Changed behavior

- `start_marked_project()` rejects any marked-project start body containing `mode`, `startMode`, or `restartPipeline` with `marked_project_legacy_start_payload_forbidden`.
- Direct server task-level Project Execution start still rejects marked projects with `marked_project_task_start_forbidden`.
- Split `server_services.projects` task-level start now also rejects marked projects.
- Split `server_services.projects` project-level start delegates marked projects to the focused stage dispatcher handler; if the stage dispatcher is unavailable, it fails closed instead of running legacy single-task start.
- Project frontend sends pure marked-project start payloads by passing `stagePipeline: true` to the API helper, which omits `mode` and `restartPipeline`.
- Project frontend blocks the old restart-pipeline action for marked projects.
- Marked task detail actions no longer expose ordinary task-level start/rerun controls.

## Files

- `app/services/project_stage_dispatch.py`
- `app/server_services/projects.py`
- `app/projects.js`
- `tests/test_project_stage_dispatch.py`
- `tests/test_project_stage_start_server.py`
- `tests/check_project_marked_legacy_start_removed.mjs`

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
# 37 passed

node tests/check_project_marked_legacy_start_removed.mjs
# marked project legacy start removal checks passed

node tests/check_project_marked_frontend_legacy_fields.mjs
# marked project frontend legacy-field checks passed

node tests/check_project_execution_start_payload.mjs
# project execution start payload check passed

node --check app/projects.js
# passed

.venv/bin/python -m py_compile app/services/project_stage_dispatch.py app/server.py app/server_services/projects.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
# passed
```

## OpenSpec

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
# Change 'add-project-task-orchestration' is valid
```
