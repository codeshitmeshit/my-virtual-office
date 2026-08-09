# Task 1.1 Legacy Execution Authority Inventory

## Scope

Inventory every current reader and writer of the legacy project-execution authorities targeted for removal or migration by `add-project-task-orchestration`:

- `projectExecutionStartMode`
- `projectExecutionFlowActive`
- `projectExecutionFlowStopReason`
- `workflowActive`
- `workflowPhase`
- `activeTaskId`
- `activeAgent`
- `autoMode`
- `executionPolicy.maxActiveTasks`
- task `executionOrder`

This is a read-only implementation inventory. It records current authority usage so later tasks can remove or migrate callers without leaving hidden single/free/manual project progression paths.

## Evidence Commands

```bash
npx --yes @fission-ai/openspec@latest status --change add-project-task-orchestration --json
npx --yes @fission-ai/openspec@latest instructions apply --change add-project-task-orchestration --json
rg -n "projectExecutionStartMode|projectExecutionFlowActive|projectExecutionFlowStopReason|workflowActive|workflowPhase|activeTaskId|activeAgent|autoMode|executionPolicy|maxActiveTasks|executionOrder" app tests openspec/changes/unify-project-materialization openspec/changes/add-agent-managed-vo-projects openspec/changes/add-project-workflow-chat-realtime-stream --glob '!**/*.png' --glob '!**/*.jpg' --glob '!**/*.json'
rg -l "projectExecutionStartMode|projectExecutionFlowActive|projectExecutionFlowStopReason|workflowActive|workflowPhase|activeTaskId|activeAgent|autoMode|executionPolicy|maxActiveTasks|executionOrder" app tests openspec/changes/unify-project-materialization openspec/changes/add-agent-managed-vo-projects openspec/changes/add-project-workflow-chat-realtime-stream --glob '!**/*.png' --glob '!**/*.jpg' --glob '!**/*.json'
```

## Field Hit Counts

These counts are raw text matches across `app`, `tests`, and the three overlapping OpenSpec changes listed in the design. They intentionally include tests and compatibility docs because those are part of the migration surface.

| Field | Hits |
|---|---:|
| `projectExecutionStartMode` | 71 |
| `projectExecutionFlowActive` | 102 |
| `projectExecutionFlowStopReason` | 90 |
| `workflowActive` | 123 |
| `workflowPhase` | 145 |
| `activeTaskId` | 156 |
| `activeAgent` | 113 |
| `autoMode` | 56 |
| `executionPolicy` | 33 |
| `maxActiveTasks` | 23 |
| `executionOrder` | 58 |

## Hotspot Files

| Hits | File | Inventory role |
|---:|---|---|
| 149 | `app/server_services/projects.py` | legacy project execution, schedule/cron continuation, meeting continuation, project start, task start, review/acceptance fallback |
| 138 | `app/server.py` | legacy mirrored HTTP entry-point behavior that must stay thin or be removed after service migration |
| 54 | `tests/test_project_execution.py` | contract tests for current single/continuous execution behavior |
| 52 | `app/services/execution_lifecycle.py` | extracted lifecycle service with singular active-task authority and mode selection |
| 41 | `app/projects.js` | project-page controls, start-mode UI, flow status, execution-order editing |
| 32 | `app/server_services/workflow.py` | non-Project-Execution workflow state using `autoMode` and singular active task fields |
| 30 | `app/services/review_acceptance.py` | review, rework, acceptance, and continuation callbacks |
| 22 | `app/services/project_materialization.py` | canonical project materialization defaults and template adaptation |
| 21 | `tests/test_project_materialization.py` | materialization expectations for old fields and `executionOrder` |
| 21 | `app/project_store.py` | Markdown frontmatter serialization/deserialization authority |
| 20 | `app/game.js` | frontend dashboard/project status presentation |
| 18 | `tests/test_project_repository.py` | repository persistence/concurrency fixtures using old workflow fields |
| 17 | `tests/test_project_materialization_characterization.py` | characterization snapshots for old materialization shape |
| 15 | `app/services/project_authoring_validation.py` | Agent/browser authoring validation for start mode, execution policy, and execution order |
| 14 | `tests/test_project_execution_dashboard_status.py` | dashboard projection expectations for singular active task/agent |
| 14 | `tests/test_project_commands.py` | command tests for `executionOrder` and project flow fields |

## Storage and Materialization

| Area | Evidence | Current behavior | Required migration direction |
|---|---|---|---|
| Markdown project frontmatter | `app/project_store.py` writes `projectExecutionStartMode`, `projectExecutionFlowActive`, `projectExecutionFlowStopReason`, `executionPolicy_json`, `workflowActive`, `workflowPhase`, `activeTaskId`, and `activeAgent`; task files write `executionOrder`. | The canonical store persists old progression and singular-active-task authorities. | Replace with `executionModel`, nested `orchestration`, task `executionStage`, `stageRunId`, and `orchestrationSkip`; remove old marked-project persisted authorities. |
| Canonical materialization | `app/services/project_materialization.py`, `app/services/browser_project_creation.py`, `app/services/project_direct_materialization.py`, `app/services/project_template_materialization.py`, `app/services/project_templates.py`. | New project creation and template paths still default `projectExecutionStartMode`, `executionPolicy.maxActiveTasks`, `workflowActive=false`, `projectExecutionFlowActive=false`, and task `executionOrder`. | Every creation source must emit `stage_pipeline_v1`, draft orchestration, and contiguous task `executionStage` without old progression selectors. |
| Project authoring validation | `app/services/project_authoring_validation.py`. | Validates `projectExecutionStartMode`, `executionPolicy.maxActiveTasks`, and populates `executionOrder`. | Accept and validate stage assignments; reject incomplete/non-contiguous stages; stop authoring old selectors for marked projects. |
| Templates/snapshots | `tests/test_project_materialization.py`, `tests/test_project_materialization_characterization.py`, `tests/test_project_templates.py`, `tests/test_project_writer_characterization.py`. | Tests lock old field persistence and execution-order defaults. | Convert tests to new marker/orchestration/stage storage once implementation lands. |

## Commands, Lifecycle, Review, and Scheduling

| Area | Evidence | Current behavior | Required migration direction |
|---|---|---|---|
| Project/task commands | `app/services/project_commands.py`, `app/server_services/projects.py`. | Allow old project execution fields in update payloads; allow task `executionOrder`; checklist completion toggles flow flags. | Route structural edits through orchestration commands; remove old fields from marked-project update surface. |
| Execution lifecycle | `app/services/execution_lifecycle.py`, `app/server_services/projects.py`. | Start mode is selected from `mode`, `startMode`, or `projectExecutionStartMode`; active ownership is singular `activeTaskId`; continuation calls start one next task. | Reserve a stage run with `currentRunId`; dispatch all current-stage tasks; reject task-level/manual starts for marked projects. |
| Review and acceptance | `app/services/review_acceptance.py`, `app/server_services/projects.py`. | Review, acceptance, rework, meeting callbacks toggle `workflowActive`, `workflowPhase`, `activeTaskId`, `activeAgent`, and `projectExecutionFlowActive`. | Terminal callbacks must reconcile the current stage instead of restarting legacy flow. |
| Scheduling and recurrence | `app/services/project_schedule.py`, `app/services/project_recurrence_execution_dispatch.py`, `app/server_services/projects.py`. | Cron can skip because another singular task is active or start legacy project execution using `projectExecutionStartMode`. | Project-level schedules may start a marked pipeline; task-targeted schedules must respect current-stage eligibility. |
| Ordering authority | `app/services/project_execution_ordering.py`, `app/services/project_commands.py`. | `executionOrder` is normalized as unique positive project-wide order and rejects invalid/duplicate semantics through commands/tests. | Replace execution eligibility with `executionStage`; keep visual board `order` separate. |

## Realtime, Chat, Frontend, and AI-Facing Interfaces

| Area | Evidence | Current behavior | Required migration direction |
|---|---|---|---|
| Realtime/dashboard projections | `app/dashboard_realtime.py`, `app/game.js`, `tests/test_project_execution_dashboard_status.py`. | Projections expose `activeTaskId`, `activeAgent`, and `projectExecutionFlowActive`. | Derive `activeTaskIds`, `activeTaskCount`, `currentStage`, `orchestrationState`, and `pauseReason`. |
| Workflow chat | `app/services/project_workflow_chat.py`, `app/server_services/workflow.py`, `tests/test_project_workflow_chat.py`. | Chat scope defaults from singular active project task/agent when project execution is active. | Require explicit task scope when multiple current-stage tasks are active; use most-recent active task only as display fallback. |
| Browser frontend | `app/projects.js`, `app/game.js`, `app/agent-workspace-panel.js`. | UI contains start-mode/project-flow state and execution-order affordances; workspace panels read singular active task IDs. | Add isolated orchestration modal and remove free/single/manual progression controls for marked projects. |
| Agent/AI project authoring | `app/services/project_authoring_validation.py`, `app/services/browser_project_creation.py`, `tests/check_vo_project_authoring_skill.mjs`, `tests/check_agent_workspace_project_context_readonly.mjs`, `tests/test_project_authoring_*`. | AI-facing creation/validation still understands old execution mode, policy, and order fields. | Review and migrate AI-facing inputs/outputs so agents produce stage assignments and cannot re-enable old progression selectors. |

## Overlapping OpenSpec Contracts

| Change | Evidence | Conflict to preserve during migration |
|---|---|---|
| `unify-project-materialization` | `openspec/changes/unify-project-materialization/design.md`, `openspec/changes/unify-project-materialization/specs/project-materialization/spec.md`. | Currently requires normalized `projectExecutionStartMode`, `executionPolicy`, and inactive old flow defaults. This must be superseded or coordinated by the orchestration marker contract. |
| `add-agent-managed-vo-projects` | `openspec/changes/add-agent-managed-vo-projects/design.md`, `verification-evidence.md`. | Confirms Agent-created projects do not auto-start and currently persist `workflowActive=false` and `projectExecutionFlowActive=false`. New contract must preserve "does not auto-start" while changing storage fields. |
| `add-project-workflow-chat-realtime-stream` | No field hits in current `rg` inventory. | Still listed by design as overlapping workflow-chat/realtime work; re-read before tasks touching chat or realtime projections. |

## Migration Checklist Derived From Inventory

- Storage removal cannot happen before materializers, commands, lifecycle, projections, frontend, and tests stop reading old fields.
- `app/server.py` and `app/server_services/projects.py` contain mirrored legacy behavior; later implementation tasks should keep them as thin delegates and avoid adding new orchestration logic there.
- `autoMode` appears in the separate workflow service and tests; later removal must distinguish general workflow automation from marked-project orchestration authorities.
- `activeAgent` has unrelated object-service/frontend uses in `app/game.js`; later static checks must scope removals to project execution authorities, not unrelated queue fields.
- Tests currently assert the old contract heavily; characterization tests in task 1.3 should freeze legacy behavior before task 2+ changes remove it.
