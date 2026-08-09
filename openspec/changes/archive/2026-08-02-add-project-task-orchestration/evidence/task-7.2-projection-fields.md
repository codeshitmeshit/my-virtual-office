# Task 7.2 Evidence: Projection fields

Updated marked-project summary and dashboard projections to expose stage-orchestration state instead of singular active-task authority.

The projection path now:

- uses `project_orchestration.project_projection()` for marked project list summaries;
- returns marked project detail responses with `activeTaskIds`, `activeTaskCount`, `currentStage`, `orchestrationState`, and `pauseReason`;
- removes `activeTaskId`, `activeAgent`, `activeTaskTitle`, and `projectExecutionFlowActive` from marked project list summaries;
- removes `activeTaskId`, `activeAgent`, and `projectExecutionFlowActive` from marked project detail responses;
- shapes dashboard SSE project snapshots with `activeTaskIds`, `activeTaskCount`, `currentStage`, `orchestrationState`, and `pauseReason`;
- emits `dashboard.projects` diffs when marked active task IDs change.

Changed files:

- `app/server.py`
- `app/dashboard_realtime.py`
- `tests/test_project_execution_dashboard_status.py`
- `tests/test_dashboard_realtime.py`

Verification:

```text
.venv/bin/python -m pytest -q tests/test_project_execution_dashboard_status.py tests/test_dashboard_realtime.py
...............                                                          [100%]
15 passed in 1.75s

.venv/bin/python -m py_compile app/server.py app/dashboard_realtime.py tests/test_project_execution_dashboard_status.py tests/test_dashboard_realtime.py
passed

node tests/check_dashboard_realtime_static.mjs
dashboard realtime static checks passed

.venv/bin/python -m pytest -q tests/test_project_execution_dashboard_status.py tests/test_dashboard_realtime.py tests/test_project_orchestration.py tests/test_project_orchestration_http.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 1.54s

npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```
