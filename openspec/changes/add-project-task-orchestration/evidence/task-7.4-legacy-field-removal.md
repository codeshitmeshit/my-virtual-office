# Task 7.4 Evidence: marked-project legacy field removal

## Scope

Removed migrated legacy progression-field usage from marked project frontend state and Agent workspace/project-card projections while preserving the legacy workflow path for unmarked projects that have not been deleted yet.

## Changed behavior

- Project board state hydration now goes through `syncWorkflowFromProject()`.
- Marked `stage_pipeline_v1` projects hydrate workflow UI from `projectExecutionPhase`, `orchestrationState`, `activeTaskIds`, and `pauseReason` instead of `workflowActive`, `workflowPhase`, `activeTaskId`, `projectExecutionStartMode`, or `projectExecutionFlowStopReason`.
- Marked project boards no longer synthesize task execution badges from `executionOrder`; task cards render `executionStage` badges.
- Marked project boards do not render legacy project start-mode radio controls or the restart-pipeline action.
- Project workflow chat polling passes an explicit task scope when the selected task is one of multiple active marked-project tasks.
- Marked project cancel-active selection uses `activeTaskIds` plus the selected task, not project-level `activeTaskId`.
- Agent workspace project-card projections omit `projectExecutionFlowActive` and `projectExecutionFlowStopReason` for marked projects and expose `executionModel`, `orchestrationState`, `currentStage`, `pauseReason`, and `activeTaskIds`.
- Agent workspace UI only renders old flow badges for unmarked legacy cards.

## Files

- `app/projects.js`
- `app/agent-workspace-panel.js`
- `app/game.js`
- `app/server.py`
- `app/server_services/agents.py`
- `tests/check_project_marked_frontend_legacy_fields.mjs`
- `tests/test_agent_workspace_project_context.py`

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_agent_workspace_project_context.py
# 2 passed

node tests/check_project_marked_frontend_legacy_fields.mjs
# marked project frontend legacy-field checks passed

node tests/check_agent_workspace_project_context_readonly.mjs
# agent workspace project context read-only UI checks passed

node tests/check_project_execution_start_payload.mjs
# project execution start payload check passed

.venv/bin/python -m py_compile app/server.py app/server_services/agents.py tests/test_agent_workspace_project_context.py
# passed

node --check app/projects.js && node --check app/agent-workspace-panel.js && node --check app/game.js
# passed

.venv/bin/python -m pytest -q tests/test_project_execution_dashboard_status.py tests/test_dashboard_realtime.py tests/test_project_workflow_chat.py
# 25 passed
```

Legacy-field grep sanity:

```bash
rg -n "state\\.workflow\\.active = !!state\\.currentProject\\.workflowActive|state\\.workflow\\.currentTaskId = state\\.currentProject\\.activeTaskId|p\\.projectExecutionFlowStopReason \\|\\| null|api\\.workflowChat\\(p\\.id\\)" app/projects.js
# no matches
```

Remaining legacy field references in `app/projects.js`, `app/agent-workspace-panel.js`, `app/game.js`, and legacy backend services are intentionally guarded or retained for unmarked legacy projects until tasks 7.5/7.6 remove the remaining reachable legacy behaviors.

## OpenSpec

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
# Change 'add-project-task-orchestration' is valid
```
