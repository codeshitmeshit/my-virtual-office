# Task 10.4 manual acceptance evidence

Date: 2026-07-27
Change: `add-project-task-orchestration`
Task: `10.4 Complete manual acceptance for create -> auto-save -> explicit start -> parallel stage -> automatic next stage -> final completion, plus failure, skip approval, pause/re-orchestration, restart recovery, schedule, permissions, and concurrent editing.`

## Service and browser acceptance

- Restarted the local VO service from the current checkout after discovering an earlier process on `7243/7244` was still serving older Python code with newer static assets.
- Verified HTTP readiness at `http://localhost:7243`; browser container access used `http://172.19.0.1:7243/?v=stage-pipeline-10-4`.
- Cleared the stale service worker/cache and reloaded the page.
- Verified orchestration assets loaded in the real page:
  - `project-orchestration.css`
  - `project-orchestration-api.js`
  - `project-orchestration.js`
- Verified runtime/API presence in the browser:
  - `window.ProjectOrchestrationRuntime`
  - `window.ProjectOrchestrationAPI`
  - runtime methods: `open`, `moveTaskToStage`, `addTask`, `pauseProject`, `resumeProject`, `requestSkip`, `decideSkip`
- Opened the orchestration modal for real project `project-9cf16b05-7593-40f0-ad99-a02e98404703`.
  - Modal class: `project-orchestration-modal is-draft`
  - Header count: `3 TASKS · 2 STEPS`
  - Stage count: `2`
  - Task count: `3`
  - Revision: `1`
  - Editable: `true`

Known browser noise: the console retained earlier `ERR_CONNECTION_REFUSED` entries from an accidental browser-container navigation to `127.0.0.1`, plus a pointer-lock warning from the shell page. After reloading through `172.19.0.1`, the orchestration assets returned 200 and the modal runtime rendered correctly.

## Real Agent direct-create and auto-save

Acceptance project:

- Project id: `project-9cf16b05-7593-40f0-ad99-a02e98404703`
- Title: `10.4 acceptance 20260727123907`
- Created through `POST /api/agent/project-authoring/projects`
- Project fields after creation:
  - `executionModel: stage_pipeline_v1`
  - `orchestration.state: draft`
  - `orchestration.revision: 0`
  - task `executionStage` assignments: `[1, 1, 2]`
  - no `projectExecutionStartMode`
  - no `executionPolicy`
  - no task `executionOrder`

Auto-save acceptance:

- Read current project detail, then saved via `PUT /api/projects/{id}/orchestration` using the project management token.
- Changed assignments from `[1, 1, 2]` to `[1, 2, 2]`.
- Result:
  - HTTP 200
  - revision advanced from `0` to `1`
  - persisted task stage assignments: `[1, 2, 2]`
  - no legacy progression authority fields reappeared

The current backend also rejects legacy direct-create payloads that still include `projectExecutionStartMode`; the live request returned `400 invalid_project_draft` with issue `legacy_project_execution_start_mode`.

## AI-facing direct-create template correction

Manual acceptance exposed a mismatch between the updated Agent authoring skill and backend confirmation text validation:

- `skills/vo-project-authoring/SKILL.md` correctly instructs Agents to submit `阶段编排：... executionStage ...` and never write `projectExecutionStartMode`, `executionPolicy`, or `executionOrder`.
- `app/services/project_direct_creation.py` still required the older `启动模式：...` marker in the confirmation summary.

Fixed during task 10.4:

- `app/services/project_direct_creation.py` accepts either the new `阶段编排：` marker or the old `启动模式：` marker for confirmation-summary compatibility.
- It accepts either the new task table with `阶段` or the older task table without it.
- Payload validation remains strict and still rejects legacy project/task authorities.
- `docs/VO_PROJECT_AUTHORING_OPERATIONS.md` now documents `executionModel: stage_pipeline_v1`, `orchestration.state=draft`, task `executionStage`, and no legacy progression authorities.
- Added regression coverage in `tests/test_project_authoring_direct_create.py`.
- Updated HTTP contract fixtures in `tests/test_project_authoring_http_contract.py` to use canonical stage-pipeline drafts.

## Scenario coverage

Create -> auto-save:

- Covered by the real Agent direct-create project and real orchestration auto-save above.
- Covered by `tests/test_project_authoring_direct_create.py`, `tests/test_project_authoring_http_contract.py`, `tests/test_project_authoring_validation.py`, `tests/test_project_orchestration_http.py`, and the frontend API/modal/page wiring scripts.

Explicit start -> parallel stage -> automatic next stage -> final completion:

- Covered by `tests/test_project_stage_dispatch.py` and `tests/test_project_stage_start_server.py`.
- These tests verify explicit stage-pipeline start, first-stage fan-out, stage advancement after all current-stage tasks complete, and completion when the final stage finishes.

Failure:

- Covered by the stage dispatch/server tests and orchestration HTTP tests, including invalid drafts, stale revisions, lock failures, queue/dispatch failure handling, and error-preserving transitions.

Skip approval:

- Covered by `tests/test_project_orchestration_skip.py`.
- Includes request/approve/reject behavior and persistence of skip metadata.

Pause and re-orchestration:

- Covered by `tests/test_project_orchestration_pause.py` and orchestration HTTP coverage.
- Includes pause/resume commands, paused edit constraints, and re-orchestration persistence.

Restart recovery:

- Covered by `tests/test_project_orchestration_recovery.py` and `tests/test_project_orchestration_concurrency.py`.
- Includes reconstruction from persisted orchestration/run state and revision-based conflict handling.

Schedule:

- Covered by `tests/test_project_schedule_service.py` and `tests/test_project_recurrence_execution.py`.
- Includes scheduled/recurring project behavior under the stage-pipeline model.

Permissions:

- Covered by `tests/test_project_authoring_http_contract.py`, `tests/test_project_orchestration_http.py`, and frontend API contract checks.
- Includes Agent-only authoring controls, browser-origin rejection for Agent direct-create, management-token checks, and action authorization.

Concurrent editing:

- Covered by `tests/test_project_orchestration_concurrency.py` and stale-revision HTTP coverage.
- Conflicting orchestration saves fail instead of overwriting a newer revision.

## Verification commands

```bash
.venv/bin/python -m pytest -q tests/test_project_authoring_direct_create.py tests/test_project_authoring_validation.py tests/test_project_authoring_http_contract.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_http.py tests/test_project_orchestration_concurrency.py tests/test_project_orchestration_recovery.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_pause.py tests/test_project_schedule_service.py tests/test_project_recurrence_execution.py tests/test_project_orchestration_release_preflight.py
```

Result: `131 passed in 3.31s`

```bash
node tests/check_project_orchestration_modal.mjs
node tests/check_project_orchestration_api_contract.mjs
node tests/check_project_orchestration_page_wiring.mjs
node tests/check_vo_project_authoring_skill.mjs
```

Results:

- `project orchestration modal runtime contract ok`
- `project orchestration API contract checks passed`
- `project orchestration page wiring checks passed`
- `VO project authoring skill contract passed`

## Acceptance notes

- Real provider-backed AI execution was not started during manual acceptance to avoid consuming external Agent runs. The execution path itself is covered by deterministic dispatcher/server tests.
- The earlier bad live project created by stale backend code was removed before acceptance continued. Its project record, workspace, grant metadata, idempotency entry, and outbox entry were cleaned, and the release preflight returned `canonicalProjectCount: 0` and `legacyDeletionCandidateCount: 0` before creating the final acceptance project.
