# Task 5.4 Evidence: Skip API Delegates

## Scope

- Added agent-facing skip request route:
  - `POST /api/agent/projects/{projectId}/tasks/{taskId}/orchestration/skip-request`
  - Requires loopback, no browser `Origin`, `X-VO-Agent-Action: project-execution`, and `X-VO-Agent-Id`.
  - The route overwrites any submitted actor with the trusted agent header identity.
- Added management-facing skip decision route:
  - `POST /api/projects/{projectId}/tasks/{taskId}/orchestration/skip-decision`
  - Requires `X-VO-Management-Token`.
  - The route overwrites any submitted actor with trusted management identity.
- Both routes delegate to `project_orchestration_skip` and use URL project/task identity instead of body-supplied ids.

## Tests Added

- `test_agent_skip_request_uses_header_actor_and_url_task_not_forged_body`
- `test_agent_skip_request_rejects_cross_task_owner_forgery`
- `test_skip_decision_requires_management_token_before_mutation`
- `test_management_skip_approval_overrides_forged_actor_and_reconciles_completion_race`
- `test_management_skip_rejection_is_idempotent_and_does_not_reconcile`
- `test_management_skip_approval_is_idempotent_at_api_boundary`

## Verification

```bash
.venv/bin/pytest -q tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py
```

Result: `16 passed in 2.32s`

```bash
.venv/bin/pytest -q tests/test_project_orchestration_skip.py tests/test_project_orchestration_http.py tests/test_project_execution_service_boundary.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
```

Result: `70 passed in 1.16s`

```bash
.venv/bin/python -m py_compile app/server.py app/services/project_orchestration_skip.py
```

Result: passed with no output.
