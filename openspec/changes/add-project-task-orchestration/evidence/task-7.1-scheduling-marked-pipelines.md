# Task 7.1 Evidence: Scheduling marked pipelines

Updated scheduled execution paths to consume marked project orchestration state.

The scheduling path now:

- starts marked project-level cron dispatch through the project pipeline start path without sending legacy `mode`;
- skips task-targeted cron for marked projects before it can call task-level execution;
- records later-stage marked task cron triggers as `marked_task_not_current_stage`;
- derives marked project active/completed scheduling decisions from orchestration state and task attempts;
- keeps existing legacy task-targeted cron tests explicit by using unmarked fixtures.

The recurrence automatic-execution path now:

- treats marked `starting`, `running`, and `pausing` projects or active attempts as already active;
- treats marked completed orchestration or accepted-terminal tasks as already completed;
- launches marked occurrence projects without legacy `mode`;
- keeps the automatic execution intent idempotent for already-active marked occurrences.

Changed files:

- `app/services/project_scheduling_orchestration.py`
- `app/services/project_schedule.py`
- `app/services/project_recurrence_execution_dispatch.py`
- `app/server.py`
- `tests/test_project_scheduled_cron_phase2_3.py`
- `tests/test_project_scheduled_cron_phase4.py`
- `tests/test_project_recurrence_occurrences.py`

Verification:

```text
.venv/bin/python -m pytest -q tests/test_project_scheduled_cron_phase2_3.py tests/test_project_recurrence_occurrences.py
...................................                                      [100%]
35 passed in 2.44s

.venv/bin/python -m py_compile tests/test_project_scheduled_cron_phase2_3.py tests/test_project_recurrence_occurrences.py app/services/project_scheduling_orchestration.py app/services/project_schedule.py app/services/project_recurrence_execution_dispatch.py app/server.py
passed

.venv/bin/python -m pytest -q tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_project_scheduled_cron_phase4.py tests/test_project_recurrence_occurrences.py tests/test_project_recurrence_reconciler.py tests/test_project_authoring_service.py
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 3.29s

npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```
