# Task 7.3 Evidence: workflow chat explicit task scope

## Scope

Updated Project Workflow Chat scope resolution for marked `stage_pipeline_v1` projects so multi-active stages no longer infer an execution scope from the most-recent task.

## Changed behavior

- `ProjectWorkflowChatService.read()` and `resolve_scope()` accept optional `task_scope`.
- Marked projects with more than one active task return a compatible empty chat envelope unless a valid explicit task scope is supplied.
- The no-scope multi-active envelope includes `activeTaskIds`, `activeTaskCount`, `requiresTaskScope`, and `displayTaskId`; `displayTaskId` is only the most-recent active task for presentation and does not trigger message/session reads.
- Explicit task scope must match a currently active marked-project task. Invalid scopes return HTTP-compatible 409 payloads and do not read Provider/session history.
- Marked projects with exactly one active task preserve automatic scope resolution.
- Workflow chat HTTP route handling accepts `taskId` or `taskScope` query parameters and passes the value into the focused service.
- The split `server_services.workflow` compatibility handler delegates to `ProjectWorkflowChatService` so route-split and direct server paths share the same scope contract.

## Files

- `app/services/project_workflow_chat.py`
- `app/server.py`
- `app/server_routes/workflow.py`
- `app/server_services/workflow.py`
- `tests/test_project_workflow_chat.py`
- `tests/test_server_routes_module_split.py`

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_workflow_chat.py
# 10 passed

.venv/bin/python -m pytest -q tests/test_project_workflow_chat.py tests/test_server_routes_module_split.py::test_workflow_chat_route_passes_explicit_task_scope tests/test_server_routes_module_split.py::test_workflow_route_uses_workflow_service_compatibility
# 12 passed

.venv/bin/python -m pytest -q tests/test_project_execution.py -k workflow_chat
# 4 passed, 104 deselected

.venv/bin/python -m py_compile app/services/project_workflow_chat.py app/server_routes/workflow.py app/server_services/workflow.py app/server.py tests/test_project_workflow_chat.py tests/test_server_routes_module_split.py
# passed
```

`tests/test_server_routes_module_split.py` as a whole currently has unrelated pre-existing failures where several monkeypatched server compatibility handlers are absent (`_handle_agents_list`, `_handle_health`, `_handle_browser_status`). The new workflow-chat route test and adjacent workflow status route test pass when run directly.

## OpenSpec

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
# Change 'add-project-task-orchestration' is valid
```
