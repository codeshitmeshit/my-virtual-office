## 1. Baseline and Contract Inventory

- [x] 1.1 Add focused characterization fixtures that capture the complete persisted Project and Task base-field projections for manual creation, browser template creation, Agent direct creation, versioned template instantiation, and recurring occurrence creation.
- [x] 1.2 Add a static creation-writer inventory test that identifies every Project/Task materialization entry point, including local `office.py --proj create`/`add-task` and confirmed Agent maintenance `create_task`, distinguishes readers/blueprints/persistence sinks, and initially allows the known builders while defining the final single-materializer boundary.
- [x] 1.3 Add focused local CLI characterization fixtures for empty and built-in-template `office.py --proj create` plus `add-task`, capturing arguments, printed results, persistence location, column/order behavior, and complete persisted Project/Task base-field projections.

## 2. Canonical Materialization Foundation

- [x] 2.1 Create `app/services/project_materialization.py` with pure canonical column and Project base materializers, injected ID/time/default inputs, deep-copy guarantees, four-column fallback, and focused unit tests.
- [x] 2.2 Add the canonical Task and checklist materializers with complete runtime/meeting/source collection defaults, stable checklist normalization, Backlog fallback, and focused unit tests for explicit and omitted values.
- [x] 2.3 Add pure manual, authoring, template, and recurrence overlay helpers plus canonical workspace projection/cleanup metadata handling, with tests proving overlays cannot omit or mutate canonical base fields.

## 3. Manual and Browser Creation Migration

- [x] 3.1 Migrate `project_commands.create_project` to the canonical Project/column materializers while preserving validation, archive default policy, workspace preparation, activity, repository response, IDs, and compatibility tests.
- [x] 3.2 Migrate `project_commands.create_task` to the canonical Task/checklist materializer while preserving assignment validation, column ordering, repository atomic update, task-file post-commit metadata, and compatibility tests.
- [x] 3.3 Migrate `_handle_project_from_template` to canonical materialization and the existing repository create boundary, preserving template column remapping, actor validation, version/source overlay, workspace behavior, HTTP payload/status, and browser-template compatibility tests.
- [x] 3.4 Migrate local `office.py --proj create` and `add-task` Project/Task construction to canonical materialization while preserving CLI arguments, built-in template selection, column/order behavior, printed output, storage adapter behavior, and CLI compatibility tests.

## 4. Agent Execution Intent and Confirmation Contract

- [x] 4.1 Extend Agent project validation to default missing execution intent to enabled, validate execution/default Agent and policy fields, require executable Task Agents and workspace preparation when enabled, allow explicit tracking-only projects, and add failure/no-downgrade tests.
- [x] 4.2 Update `vo-project-authoring` confirmation text, structured payload guidance, digest markers, and static/direct-create contract tests to show execution state, executor, reviewer, start behavior, and to translate confirmed acceptance criteria into Task checklists without promoting meeting context.
- [x] 4.3 Replace the authoring-specific `{path, kind, status, managed, created}` workspace mapping with the canonical prepared-workspace projection, preserve cleanup-on-failed-commit behavior, and add system-managed/user-managed/tracking-only workspace tests.

## 5. Agent and Template Materialization Migration

- [x] 5.1 Migrate conversation-confirmed direct creation to canonical Project/Task/column/checklist materialization plus the authoring overlay, preserving grant, idempotency, template/recurrence/outbox atomicity, activity, and one-time secret behavior.
- [x] 5.2 Persist explicit execution intent in new immutable template snapshots, safely retain stored disabled behavior for existing schema-version-1 templates, and add compatibility tests for new enabled, explicit tracking-only, and historical templates.
- [x] 5.3 Migrate versioned template instantiation to canonical materialization and template overlays while preserving actor revalidation, immutable version pinning, overrides, workspace cleanup, idempotency, and public management behavior.
- [x] 5.4 Migrate confirmed Agent maintenance `create_task` to the canonical Task materializer while preserving grant and confirmation authorization, actor validation, caller-supplied ID conflict handling, root-transaction atomicity, audit behavior, and maintenance tests.

## 6. Recurring Instance and Automatic Execution

- [x] 6.1 Add and validate the confirmed recurrence execution mode (`create_only` or `create_and_execute`), include it in semantic digests and durable recurrence definitions, default existing definitions to create-only, and add validation/idempotency tests.
- [x] 6.2 Migrate recurring occurrence Project/Task creation to canonical materialization while preserving deterministic IDs, claims, version/source traceability, workspace cleanup, intervention recording, and duplicate/concurrent callback tests.
- [x] 6.3 Persist a bounded per-occurrence automatic-execution intent atomically with `create_and_execute` Project creation, and add state/history tests for pending, started, retryable failure, and intervention outcomes.
- [x] 6.4 Inject project-level execution start after occurrence commit, reconcile pending/retryable intents without duplicate active attempts, expose sanitized/rate-limited observability, and test post-commit crash recovery, repeated/concurrent callbacks, start failure, and already-active projects.

## 7. Duplicate Removal and Boundary Enforcement

- [x] 7.1 Remove superseded `_build_project`, `_build_template_instance_project`, compact-column/checklist repair logic, and obsolete workspace field adapters after all callers migrate; tighten the static writer boundary test to forbid new independent builders.
- [x] 7.2 Run cross-entry-point base-field projection tests and document every permitted manual/authoring/template/recurrence overlay difference, fixing any unapproved parity drift without changing public route contracts.

## 8. Verification, Documentation, and Rollout Evidence

- [x] 8.1 Update user and operator documentation for enabled-but-unstarted Agent projects, tracking-only creation, execution prerequisite failures, recurring create-only versus auto-execute confirmation, and rollback behavior.
- [x] 8.2 Run and record focused materialization, project command, direct authoring, HTTP/security, template, recurrence, Project Execution, persistence, static-boundary, and legacy compatibility suites, plus strict OpenSpec validation.
  - Evidence (2026-07-23): `.venv/bin/python -m pytest -q tests/test_project_materialization*.py tests/test_project_commands.py tests/test_project_cli_materialization_characterization.py tests/test_project_writer_characterization.py tests/test_project_authoring*.py tests/test_project_template*.py tests/test_project_recurrence*.py tests/test_project_execution*.py tests/test_project_repository.py tests/test_project_store_authoring_metadata.py` — 323 passed in 13.29s.
  - Evidence (2026-07-23): `node tests/check_vo_project_authoring_skill.mjs` and `node tests/check_vo_project_authoring_docs.mjs` — both contract checks passed.
  - Evidence (2026-07-23): `openspec validate unify-project-materialization --strict` — change is valid.
- [ ] 8.3 Record a flag-off rollout rehearsal followed by Agent direct creation, create-only recurrence, confirmed auto-execute recurrence, failure/intervention observation, feature disablement, and code/data rollback checks with unresolved limitations explicitly listed.
