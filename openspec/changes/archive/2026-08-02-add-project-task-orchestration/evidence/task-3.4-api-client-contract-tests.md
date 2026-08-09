# Task 3.4 Evidence: API and client contract tests

Date: 2026-07-27

## Scope

Added API and client-contract coverage for orchestration auto-save behavior.

The client contract now proves:

- a completed orchestration drag calls one `PUT /api/projects/{projectId}/orchestration` request;
- the request body is one full-assignment write containing `revision` plus all task stage assignments;
- stale-revision HTTP 409 responses expose the authoritative `currentRevision`, `orchestration`, and `assignments`;
- validation failures and transport failures always return `saved: false` to prevent rejected writes from appearing saved.

The HTTP contract now proves:

- successful orchestration PUTs perform exactly one repository save;
- authorization failures, validation failures, stale revision conflicts, and persistence failures do not persist project state.

## Files

- `app/project-orchestration-api.js`
- `tests/check_project_orchestration_api_contract.mjs`
- `tests/test_project_orchestration_http.py`

## Verification

Client contract:

```text
node tests/check_project_orchestration_api_contract.mjs
project orchestration API contract checks passed
```

Focused API and command regression:

```text
.venv/bin/pytest -q tests/test_project_orchestration_http.py tests/test_project_orchestration_commands.py
12 passed in 0.84s
```

## Notes

- The new frontend API module is intentionally isolated from `projects.js`; task 8.4 will wire the orchestration modal drag/drop UI to this contract.
- The route remains a thin transport delegate, while atomic save semantics continue to live in `project_orchestration_commands.py`.
