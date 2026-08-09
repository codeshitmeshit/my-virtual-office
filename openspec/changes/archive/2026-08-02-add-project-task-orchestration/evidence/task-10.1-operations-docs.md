# Task 10.1 Operations Documentation Evidence

## Updated Documents

- `docs/PROJECT_TASK_ORCHESTRATION_OPERATIONS.md`
  - Added the developer/operator contract for `stage_pipeline_v1`.
  - Covers module ownership, durable storage fields, removed legacy authorities,
    API contracts, concurrency limits, authorization mapping, structured
    diagnostics, recovery behavior, release gates, and the no-JSONL decision.
- `README.md`
  - Added the operations document to the documentation index.

## Verification

- `.venv/bin/python - <<'PY' ...`
  - Checked that the operations document contains the required 10.1 coverage
    markers:
    - `Ownership`
    - `Durable Storage Fields`
    - `Removed Authorities`
    - `API Contracts`
    - `Concurrency Limits`
    - `Authorization Mapping`
    - `Diagnostics`
    - `No JSONL Decision`
    - key storage/API/diagnostics terms such as
      `executionModel: stage_pipeline_v1`, `orchestration.revision`,
      `executionStage`, `PUT /api/projects/{projectId}/orchestration`,
      `BoundedProjectExecutionDispatcher`, `management-token`, and
      `orchestrationAudit`
  - Result: `project task orchestration operations doc coverage ok`.
- `rg -n "PROJECT_TASK_ORCHESTRATION_OPERATIONS|Project Task Orchestration" README.md docs/PROJECT_TASK_ORCHESTRATION_OPERATIONS.md`
  - Result: README index and new document title found.
- `git diff --check -- README.md docs/PROJECT_TASK_ORCHESTRATION_OPERATIONS.md openspec/changes/add-project-task-orchestration`
  - Result: passed.

