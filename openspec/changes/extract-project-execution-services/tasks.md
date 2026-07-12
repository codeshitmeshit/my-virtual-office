## 1. Baseline and writer inventory

- [x] 1.1 Inventory every project-store writer, including CRUD, execution, review/acceptance, Feishu, Meeting, Cron, archive/recovery, legacy `_wf_*`, and direct `PROJECT_STORE.save_all/delete_project` calls; record each writer's target project, owned fields, and planned `repo.update`, `repo.delete`, or safe merge migration.
- [x] 1.2 Add characterization tests for cross-writer state preservation, including same-project legacy/new updates, different-project barrier commits, execution completion racing with task/activity/comment changes, and direct-delete behavior.
- [x] 1.3 Add the reproducible performance harness and `performance-baseline.md` for start prepare, provider completion, review start/commit, acceptance, and Cron dispatch using the confirmed small/medium/large fixtures, call counters, three warmups, twenty measured runs, median, and p95.

## 2. Repository and project command foundation

- [x] 2.1 Implement `app/services/project_repository.py` with the ref-counted project lock registry, short global store commit lock, latest-data merge, acceptance repair, Cron-history compatibility, stable lock ordering, and explicit `update`/`delete` operations; add focused repository tests.
- [x] 2.2 Route all inventoried project-store writers through the shared commit coordinator without moving legacy `_wf_*` business orchestration; add static checks forbidding stale full-data saves and direct `PROJECT_STORE.save_all/delete_project` outside the repository adapter.
- [x] 2.3 Extract project and task CRUD commands into `app/services/project_commands.py`, preserve validation, Done/checklist/column policies, payload/status/storage compatibility, and add direct Service plus Handler adapter contract tests.
- [x] 2.4 Run repository, writer-race, project/task CRUD, old-Markdown compatibility, and performance-harness regression; record the first verified read/write reduction or explicitly keep the performance claim open.

## 3. Execution lifecycle

- [x] 3.1 Add lifecycle characterization tests for start, project start, status, cancel, transition matrix, dirty-worktree confirmation, retry, Meeting blocking, continuous execution, and every runner intermediate branch.
- [x] 3.2 Implement `app/services/execution_lifecycle.py` with explicit repository, clock, ID, launcher, workspace, Git snapshot, Provider, cancel-registry, notification, and scheduling dependencies; preserve persist-before-launch and attempt-ID compare-and-commit ordering.
- [x] 3.3 Change Git workspace snapshot failure/timeout to fail closed with HTTP 409 and `workspace_git_snapshot_failed`, preserve non-Git behavior, and add failing-before plus API compatibility tests proving Provider is not invoked.
- [x] 3.4 Migrate HTTP, Cron, Meeting, continuation, retry, and internal execution callers to lifecycle commands while retaining thin compatibility delegates only where references remain; run lifecycle and cross-writer concurrency tests.

## 4. Review, rework, and acceptance

- [x] 4.1 Add characterization tests for review start/normalization, malformed reviewer output, automatic rework limits, checklist/empty-checklist gates, HTTP and Feishu acceptance, repeated acceptance, and notification failure/crash windows.
- [x] 4.2 Implement `app/services/review_acceptance.py` with trusted entry context, review/attempt compare tokens, stable local notification intents, sanitized notification DTOs, and best-effort external delivery without business-state rollback.
- [x] 4.3 Migrate HTTP, Feishu card action, Meeting/rework, automatic review, and checklist-completion callers; add authorization-linkage, forged actor, cross-project, idempotency, redaction, and adapter compatibility tests.
- [x] 4.4 Run review, rework, acceptance, notification, legacy workflow compatibility, writer-race, and performance measurements; verify load/save/external-call counts do not regress.

## 5. Artifact service

- [x] 5.1 Add `tests/test_artifact_service.py` characterization for list/read/file/delete, directory allowlist deletion, associated-only access, traversal, symlink swap, non-regular files, limits, client interruption, and current status/payload semantics.
- [x] 5.2 Implement `app/services/artifacts.py` with realpath containment, allowlists, resource limits, `OpenedArtifact` context management, `fstat`, no-follow support/fallback, sanitized errors, and compatible recursive allowlist directory deletion.
- [x] 5.3 Migrate Artifact JSON and file-stream handlers while keeping management authorization, headers, streaming, BrokenPipe cleanup, and HTTP error mapping in `OfficeHandler`; run focused security and contract tests.

## 6. Schedule service

- [x] 6.1 Extend Cron phase characterization tests for Gateway run plus local dispatch, skipped/paused/archived cases, repeatable-task reopen, cross-project concurrency, binding/history limits, and Gateway-success/local-failure behavior.
- [x] 6.2 Implement `app/services/project_schedule.py` with the specified Gateway, Binding, and Execution ports, compatible payload/status/error results, lock-order rules, history limits, and diagnostic reconciliation state.
- [x] 6.3 Migrate all scheduled Cron handlers and dispatch callers, preserve Gateway job/binding/project-history ordering and 502/skipped semantics, then run phase 1-5, idempotency, writer-race, and performance tests.

## 7. Boundary, security, and performance verification

- [x] 7.1 Add static dependency checks proving new Service modules do not import `server.py`, `OfficeHandler`, or HTTP transport objects, and proving all project-store writes use the shared coordinator.
- [x] 7.2 Add trusted-entry and sensitive-data regression coverage for HTTP, Feishu, Meeting, Cron, workspace paths, Provider metadata, Review feedback, Artifact content, canary secrets, absolute paths, and sanitized logger/notifier DTOs.
- [x] 7.3 Produce `performance-result.md` from the fixed harness; verify no measured operation increases store/external call counts and at least one evidenced redundant store read/write path strictly improves before claiming the backend performance goal.
- [x] 7.4 Run the complete Python, JavaScript, static, persistence, Provider, SSE/WebSocket, notification, workflow, Artifact, Cron, and OpenSpec strict regression set; record commands, results, failures, and any remaining manual-only coverage.

## 8. Documentation, acceptance, and release readiness

- [x] 8.1 Update service-boundary and developer documentation with the final module ownership, trusted entry contexts, writer coordinator rule, lock ordering, performance methodology, confirmed bug fixes, compatibility guarantees, and legacy `_wf_*` non-goal.
- [x] 8.2 Start the application only through the repository startup script and complete manual acceptance for project/task operations, execution, Review/rework/acceptance, Artifact access, scheduling, Git snapshot failure, concurrent operations, and management-token behavior.
- [x] 8.3 Execute the staging medium-fixture release/active-work/drain/rollback rehearsal and create `rollout-rehearsal.md` containing version SHAs, commands, backup location, before/after state snapshots, thresholds, reconciliation results, and pass/fail evidence.
- [x] 8.4 Re-run `openspec validate extract-project-execution-services --strict`, verify every confirmed scenario maps to implementation and test evidence, and present the complete test/performance/rollback results for the test-result confirmation gate.
