# Project Store Writer Inventory

## Scope and method

Baseline: `origin/main` at the start of change implementation.

Production writers were discovered with:

```bash
rg -n '_save_projects\(|PROJECT_STORE\.(save_all|delete_project)\(' app --glob '*.py'
```

The inventory covers every production call site in `app/server.py`. Calls from `tests/` and fixture seed scripts are setup helpers rather than runtime writers; they remain compatibility consumers of `_save_projects` until their fixtures are migrated.

Migration strategies:

- `repo.update`: acquire the shared project lock, mutate one project from the latest snapshot, and commit through the shared store coordinator.
- `repo.create`: commit a new project through the coordinator without accepting a caller-owned full snapshot.
- `repo.delete`: delete a project through the coordinator and the shared store commit lock.
- `repo.update_root`: update root-level collections such as templates through the coordinator.
- `owned merge`: merge an explicitly enumerated field set into the latest project under project lock and store commit lock.

No runtime writer may retain a caller-modified full-data snapshot and pass it to `_save_projects` after Task 2.2.

## Runtime writer inventory

| Area | Writer symbol | Current write ownership | Target strategy | Notes / required compatibility |
| --- | --- | --- | --- | --- |
| Meeting | `_meeting_request_log_auto_confirm_activity` | project `activity`, `updatedAt` | `repo.update` | Preserve meeting/task linkage and activity ordering. |
| Meeting | `_meeting_confirm_action_item_on_source_task` | task `meetingActionItems`, task/project timestamps, project activity | `repo.update` | Preserve action-item idempotency and source snapshot. |
| Cron | `_project_cron_append_history` | `scheduledCronHistory`, project activity, `updatedAt` | `repo.update` | Preserve history limit, alert activity, result/status fields. |
| Cron dispatch | `_handle_project_scheduled_cron_dispatch` | reopened task state, checklist, comments/history, project timestamp | `repo.update` | Prepare reopen atomically before execution start; do not hold project lock across Gateway or execution calls. |
| Project CRUD | `_handle_project_create` | append a complete project | `repo.create` | Preserve generated workspace, defaults, activity, identifiers and ordering. |
| Task CRUD | `_handle_task_create` | append task, project activity/timestamp | `repo.update` | Preserve column/order defaults and execution-role validation. |
| Task CRUD | `_handle_task_comment` | task comments, timestamps, project activity | `repo.update` | Preserve comment ordering and limits. |
| Project templates | `_handle_project_from_template` | append project and generated task/column state | `repo.create` | Preserve template expansion and generated workspace behavior. |
| Project templates | `_handle_save_as_template` | root `templates` collection | `repo.update_root` | Root collection update must share the store commit coordinator. |
| Project CRUD | `_handle_project_update` | mutable project fields, workspace settings, activity/timestamp | `repo.update` | Field allowlist and workspace validation remain unchanged. |
| Task CRUD | `_handle_task_update` | task fields/checklist/column/completion state, project activity/timestamp | `repo.update` | Preserve Project Execution Done/acceptance gates and continuation triggers; launch follow-up work after commit. |
| Project columns | `_handle_columns_update` | project `columns`, task column normalization, activity/timestamp | `repo.update` | Preserve task membership and column ordering. |
| Task ordering | `_handle_tasks_reorder` | task `columnId`/`order`/completion fields, activity/timestamps | `repo.update` | Preserve Done gate and post-commit continuation behavior. |
| Project CRUD | `_handle_project_delete` | entire project removal via direct `PROJECT_STORE.delete_project` | `repo.delete` | Workspace deletion remains outside commit lock and follows existing authorization/safety checks. |
| Task CRUD | `_handle_task_delete` | remove task, active-task metadata, project activity/timestamp | `repo.update` | Preserve active task cleanup and response shape. |
| Project reset | `_handle_project_reset` | task execution/review/attempt/checklist state and project workflow fields | `repo.update` | Preserve reset mode, activity/history and post-commit side effects. |
| Execution retry | `_project_execution_schedule_transient_retry` | attempt retry/evidence/status, task/project execution fields | `repo.update` | Commit retry state before launching delayed work; compare active attempt. |
| Execution checklist | `_project_execution_continue_for_incomplete_checklist` | attempt evidence, checklist, task state/comments/history, project workflow fields | `repo.update` | Three current save branches become explicit atomic outcomes. |
| Meeting blocker | `_project_execution_block_for_meeting_request` | task blocker/history/state and project workflow fields | `repo.update` | Preserve request linkage and transition order. |
| Meeting blocker | `_project_execution_update_meeting_blocker` | task blocker/history/timestamps | `repo.update` | Compare request id before mutation. |
| Meeting result | `_project_execution_apply_meeting_result` | meeting records/actions/checklist, task state, project activity/workflow | `repo.update` | All current success/failure save branches commit by meeting/request token; slow follow-up stays outside lock. |
| Archive maintenance | `_handle_archive_project_maintenance_update` | archive maintenance settings and project timestamp/activity | `repo.update` | Preserve archive-manager validation and response fields. |
| Review runner | `_project_execution_run_review` | review result/status, task transition, project workflow and notification markers | `repo.update` | Both malformed/failure and normalized-result branches compare review/attempt ids. |
| Execution runner | `_project_execution_run_attempt` | attempt evidence/status/retry, task state, project workflow and notification markers | `repo.update` | Every intermediate branch must compare active attempt; Provider/notification work stays outside lock. |
| Execution start | `_handle_project_execution_start` | dirty confirmation, attempt creation, task/project active state | `repo.update` | Current validation-failure and success saves become atomic command outcomes; launch only after commit. |
| Project execution | `_handle_project_execution_project_start` | flow-active/stop metadata and selected task state | `repo.update` | Current no-task/confirmation/success branches preserve statuses. |
| Continuous execution | `_project_execution_schedule_continue` | flow stop reason and project workflow fields | `repo.update` | Delay/thread creation occurs after commit. |
| Execution status | `_handle_project_execution_status` | repaired stale execution state | `repo.update` | Only write when repair changes state; preserve read response contract. |
| Execution cancel | `_handle_project_execution_cancel` | attempt/task cancellation and project workflow fields | `repo.update` | In-memory cancel flag update is coordinated outside durable commit. |
| Review start | `_handle_project_execution_review_start` | review creation, task/project reviewing state | `repo.update` | Launch reviewer after commit and compare review/attempt ids. |
| Acceptance | `_handle_project_execution_acceptance` | acceptance/rework/block state, attempts, history, checklist, workflow and notification intent | `repo.update` | All current branches use one command boundary; launch rework/notify after commit. |
| Meeting override | `_handle_project_execution_meeting_blocker_action` | blocker/history, task/project transition and restart-failure state | `repo.update` | Each branch commits before external restart; failed restart is a second compare-and-commit. |
| Legacy workflow | `_wf_move_task` | task column/order/completion, project activity/timestamp | `repo.update` | Business orchestration stays legacy; write coordination migrates. |
| Legacy workflow | `_wf_update_task_field` | one task field and timestamps | `owned merge` | Explicit task id + field; reject execution-owned fields unless routed to lifecycle command. |
| Legacy workflow | `_wf_sync_project_workflow_meta` | `workflowActive`, `workflowPhase`, `activeTaskId`, `activeAgent`, timestamp | `owned merge` | Field ownership is explicit; use shared project lock. |
| Legacy workflow | `_wf_write_task_file` | task `reviewCheck`, comments and timestamps | `repo.update` | Canonical Markdown task update remains legacy logic but uses coordinator. |
| Legacy workflow | `_handle_workflow_start` | workflow/active-task/agent/auto-mode fields | `repo.update` | Thread launch happens after durable commit. |
| Legacy workflow | `_handle_workflow_stop` | workflow/active-task/agent fields | `repo.update` | Session abort remains outside project lock. |
| Legacy workflow | `_handle_workflow_auto_mode` | project `autoMode`, timestamp | `owned merge` | In-memory workflow state update follows durable commit. |
| Legacy review | `_handle_review_check_update` | task `reviewCheck`, activity/comments/timestamps | `repo.update` | Preserve rejection for Project Execution-enabled projects; avoid a second stale save in `_wf_write_task_file`. |
| Project templates | `_handle_template_delete` | root `templates` collection | `repo.update_root` | Preserve 404 behavior and template ordering. |

## Storage adapter call sites

| Symbol | Current behavior | Task 2.2 requirement |
| --- | --- | --- |
| `_load_projects` | `PROJECT_STORE.load_all()` plus acceptance-state repair | Become the repository compatibility read delegate; callers must not pair it with stale full-data save. |
| `_save_projects` | reloads for Cron-history compatibility, then calls `PROJECT_STORE.save_all(data)` | Become internal-only compatibility adapter or be removed; static check forbids production callers after migration. |
| `_handle_project_delete` | calls `PROJECT_STORE.delete_project(project_id)` directly | Route through `repo.delete`; static check forbids direct runtime deletion outside repository. |

## Test and fixture consumers

The following are not production writers but depend on `_save_projects` for fixture setup and must continue to work until migrated to repository test helpers:

- `tests/test_project_execution.py`
- `tests/test_meeting_request_blocks_task.py`
- `tests/test_project_scheduled_cron_phase1.py`
- `tests/test_project_scheduled_cron_phase2_3.py`
- `tests/test_project_scheduled_cron_phase4.py`
- `tests/test_project_scheduled_cron_phase5.py`
- `tests/test_project_cron_idempotent_defect.py`
- `tests/test_archive_room_phase_1_3.py`
- `tests/seed_archive_room_phase7_fixture.py`
- `tests/seed_archive_room_phase8_fixture.py`
- `tests/seed_meeting_action_items_fixture.py`

## Task 2.2 enforcement targets

1. A static test must fail if `app/server.py` directly calls `PROJECT_STORE.save_all` or `PROJECT_STORE.delete_project` outside the repository adapter wiring.
2. A static test must prove `_save_projects` delegates to `ProjectRepository.commit_snapshot` and contains no direct store write; each later service slice removes its corresponding compatibility calls.
3. Barrier tests must cover same-project legacy/new writes and different-project commits.
4. Slow Provider, notification, Gateway, Git, filesystem, thread launch, and session-abort work must remain outside project/store locks.
