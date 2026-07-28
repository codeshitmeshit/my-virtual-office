# Task 3.3 Evidence: Orchestration PUT route

Date: 2026-07-27

## Scope

Added the management-token-protected `PUT /api/projects/{projectId}/orchestration` route.

The route now:

- uses the existing `/api/projects/*` management-token gate before body parsing;
- uses bounded object JSON parsing through the existing management body reader;
- delegates to `project_orchestration_commands.autosave_orchestration`;
- returns stable success payloads with updated `orchestration`, normalized `assignments`, and project state;
- preserves command validation statuses such as HTTP-style 400 and stale-revision 409;
- maps persistence exceptions to a stable 500 payload with `code: orchestration_persistence_failed`.

## Verification

Focused route and command regression:

```text
.venv/bin/pytest -q tests/test_project_orchestration_http.py tests/test_project_orchestration_commands.py
12 passed in 1.85s
```

Wider project HTTP, command, and materialization regression:

```text
.venv/bin/pytest -q tests/test_project_orchestration_http.py tests/test_project_orchestration_commands.py tests/test_project_execution_service_boundary.py tests/test_project_authoring_http_management.py tests/test_project_commands.py tests/test_project_materialization.py tests/test_project_materialization_characterization.py
84 passed in 2.27s
```

OpenSpec validation:

```text
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```

## Notes

- Authorization is covered by the route-level management gate shared by all `/api/projects/*` mutations.
- The route remains a thin transport delegate; validation and mutation rules remain in `project_orchestration_commands.py`.
