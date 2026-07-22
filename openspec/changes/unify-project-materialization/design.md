## Context

Project creation currently has five object-building authorities:

- `project_commands.create_project` and `create_task` build the manual Project and Task contracts.
- `ProjectAuthoringService._build_project` builds conversation-confirmed Agent projects, while `_apply_maintenance_mutation(create_task)` independently builds Tasks added through confirmed Agent maintenance.
- `ProjectAuthoringService._build_template_instance_project` builds versioned template and recurrence instances.
- `server._handle_project_from_template` independently clones browser templates and builds another Project/Task shape.
- `office.proj_cmd --proj create` and `--proj add-task` are separate local CLI writers that directly append smaller Project/Task shapes through `_save_proj`.

The paths share storage but not materialization. Manual creation supplies archive, execution, workspace, scheduling, dirty-confirmation, template, meeting, evidence, source, comment, and attachment defaults that the authoring builders may omit. Agent validation also leaves Project Execution fields optional, while workspace preparation interprets an omitted `projectExecutionEnabled` as false. Template schema version 1 synthesizes false when execution intent is absent, and authoring workspace preparation converts the canonical persisted field names into a second `{path, kind, status, managed, created}` vocabulary.

Direct authoring and recurring occurrence creation already have important atomicity and idempotency boundaries that must remain intact. Workspace preparation occurs before commit and is cleaned up on failed commit. Direct creation atomically commits the Project, grant, template, recurrence, outbox, and idempotency record. Recurrence uses expiring occurrence claims and creates one deterministic project per occurrence. Materialization must be shared without merging those transaction boundaries.

## Goals / Non-Goals

**Goals:**

- Make one focused module the sole writer of canonical new Project, Task, column, checklist, and persisted workspace fields.
- Preserve manual, Agent, template, and recurrence authorization, validation, idempotency, transaction, source, and audit behavior as orchestration and overlays.
- Resolve Agent execution intent before side effects: default enabled and unstarted, explicit tracking-only disabled, and fail closed when enabled prerequisites are invalid.
- Preserve template version pinning and occurrence idempotency while allowing separately confirmed recurring automatic execution.
- Keep legacy project records readable without a backfill or destructive migration.

**Non-Goals:**

- Do not route Agent creation through the browser HTTP API.
- Do not combine ProjectRepository and ProjectAuthoringRootStore transaction models.
- Do not redesign Project Execution, review, acceptance, grant, or scheduling state machines.
- Do not change existing projects or infer that historical disabled projects should be enabled.
- Do not introduce a new external dependency, datastore, worker pool, or public route.

## Decisions

### 1. Add a pure project materialization module

Create `app/services/project_materialization.py`. It MUST NOT import `app.server`, access repositories, prepare workspaces, emit HTTP responses, or launch execution. Its dependencies are explicit values or injected ID/clock/default-policy callables.

The module owns these cohesive operations:

- `materialize_columns(...)`: normalize explicit columns or produce the canonical Backlog, In Progress, Review, and Done board; return the normalized columns and source-to-materialized column mapping.
- `materialize_task_base(...)`: produce every canonical Task field, normalize checklist items, deep-copy mutable input, and accept already validated actor projections.
- `materialize_project_base(...)`: produce every canonical Project field from resolved project configuration, prepared workspace projection, materialized columns/tasks, timestamp, IDs, and archive/execution defaults.
- `apply_authoring_overlay(...)`: add authoring provenance and initial `project_authored` activity without rebuilding base fields.
- `apply_template_overlay(...)`: add template/version or recurrence provenance and the appropriate initial activity without rebuilding base fields.

Materializers return new dictionaries and never mutate caller-owned drafts or template snapshots. Project/task identifiers and timestamps remain caller-supplied or generated through injected factories so existing random and deterministic ID contracts can be preserved.

Alternative considered: make `project_commands.create_project` the shared builder. Rejected because commands also own validation, workspace orchestration, repository mutation, result mapping, and post-commit behavior; importing them into authoring would couple root compare-and-set creation to the manual repository transaction.

Alternative considered: call `/api/projects` from Agent authoring. Rejected because it would cross trust boundaries, split the atomic grant/template/recurrence commit, and make local transport availability part of domain creation.

### 2. Separate canonical base fields from explicit source overlays

The base contract is authoritative for all fields that describe a valid persisted Project or Task. It includes the currently manual-only compatibility defaults such as archive maintenance state, high-priority meeting approval, Project Execution flow state/stop reason, schedule pause, execution dirty confirmations, template state, Task attempt/evidence/block/error/source/comment/attachment/meeting fields, and timestamps.

Callers resolve validation and policy before materialization. Overlays may add or replace only documented source-owned fields:

| Source | Overlay ownership |
| --- | --- |
| Manual | `project_created` activity and manual creator identity |
| Browser template | template reference/source and manual template activity |
| Agent direct | `project_authored`, confirmation/source, maintenance/grant linkage, idempotency-visible provenance |
| Versioned template | immutable template ID/version and instantiation provenance |
| Recurrence | recurrence/occurrence ID and recurrence provenance |

An overlay cannot delete canonical fields. Contract tests compare base-field projections across entry points and separately assert allowed overlay differences.

### 3. Normalize columns and checklists during materialization

No meaningful columns means the four canonical columns. Explicit custom columns retain their title/color/order but are copied and assigned IDs according to the caller's ID policy. Template cloning requests fresh column IDs and uses the returned mapping to remap Task columns; Agent drafts may retain valid project-scoped column IDs. A missing or invalid Task column after validated mapping falls back to Backlog.

Checklist normalization accepts a bounded list of item mappings or text values and produces the execution-compatible `{id, text, done}` representation, preserving valid supplied IDs and optional evidence. Stable IDs are derived from normalized text when absent, with a collision suffix within one Task. Initial `done` defaults to false.

The `vo-project-authoring` skill remains responsible for translating each confirmed “验收标准” cell into structured `tasks[].checklist`. The backend validates that structured data and the materializer normalizes it. Meeting actions, risks, and discussion points remain separate inputs and are not promoted to checklist items implicitly.

Alternative considered: parse the confirmed Markdown summary in the backend. Rejected because the summary is an audit assertion rather than a second product model, and parsing it would duplicate the already confirmed structured payload.

### 4. Resolve Agent execution intent in validation before workspace preparation

Extend Agent draft validation with an explicit normalized execution intent:

- Missing `projectExecutionEnabled` on future Agent creation resolves to true.
- Explicit false resolves to tracking-only.
- Enabled creation requires every automatically executable Task to resolve to an assignable Agent executor. Human-only Tasks are valid only for explicit tracking-only creation.
- `defaultExecutorAgentId`, `defaultReviewerAgentId`, `projectExecutionStartMode`, and `executionPolicy` are normalized and validated when supplied. Task-level executors remain authoritative when no project default is supplied.
- Ordinary creation always materializes `projectExecutionFlowActive=false` and `workflowActive=false`.

The confirmation template and its digest markers change together. It shows execution enabled/disabled, executor assignment, reviewer assignment/absence, and creation start behavior. Direct-create payload digesting occurs after normalization, so omitted enabled and explicit enabled have one semantic idempotency representation; explicit tracking-only remains distinct.

For templates created after this change, execution intent is saved explicitly in the immutable snapshot. Existing schema-version-1 snapshots already containing `projectExecutionEnabled=false` are treated as explicit disabled configuration for safety and compatibility; they are not rewritten or reinterpreted as enabled. Agent initiation defaults to enabled only when the resolved template configuration truly lacks an execution setting. This avoids automatically enabling historical automation while making all new Agent template authoring explicit.

### 5. Use one canonical prepared-workspace projection

Workspace creation and validation remain outside the materializer. `_project_prepare_workspace` continues to own filesystem effects and returns canonical storage semantics:

- `projectExecutionEnabled`
- `workspacePath`
- `workspaceKind`
- `workspaceStatus`
- `workspaceManagedBy` (`system`, `user`, or null)
- `workspaceCreatedAt`

Authoring adapters stop translating these fields into `path/kind/status/managed/created`. Non-persisted cleanup information is represented by a small internal prepared-workspace value or derived only from canonical ownership plus a created-in-this-attempt marker; it is never copied into the Project. `workspaceManagedBy` identifies ownership, while `authoringSource` identifies provenance.

Tracking-only Agent creation skips executable-workspace preparation. Enabled creation calls the same preparation policy used by manual Project Execution projects and fails before commit on error. Existing cleanup callbacks remain outside locks.

### 6. Migrate each caller without changing its transaction boundary

Migration order follows dependency risk:

1. Add pure materializers and exhaustive unit contract fixtures.
2. Delegate manual `create_project` and `create_task` object construction while retaining command validation, repository calls, activity logging, and task-file post-commit behavior.
3. Delegate browser `_handle_project_from_template`, replace its direct full-store append with the existing repository create boundary, and retain its route/status/payload contract.
4. Delegate the local `office.py --proj create` and `--proj add-task` paths, retaining CLI arguments, built-in template selection, printed output, and their current storage adapter while replacing their independent Project/Task dictionaries.
5. Normalize Agent execution/checklist/column intent, then delegate direct authoring `_build_project`; once callers use the materializer, remove the duplicate private builder.
6. Delegate versioned template and recurrence instance creation; remove `_build_template_instance_project` after both callers migrate.
7. Delegate confirmed Agent maintenance `create_task` to the canonical Task materializer while retaining grant, confirmation, actor validation, conflict, and root-transaction semantics.
8. Remove standalone compact-column/checklist repair helpers once their behavior is covered by canonical materialization.

During migration, thin compatibility delegates may remain only while a referenced caller still exists. There will be no import from the new module back into `server.py` or another legacy entry point.

### 7. Persist recurring automatic-execution intent and launch only after commit

Add a normalized recurrence execution mode with two values: `create_only` and `create_and_execute`. It is displayed in the confirmation summary, included in the semantic/idempotency digest, stored in the recurrence definition, and copied into each occurrence record.

For `create_only`, occurrence materialization behaves as today: it commits one enabled but inactive Project.

For `create_and_execute`, the occurrence commit atomically writes both the Project and a bounded execution intent in the occurrence record with state `pending`. The root-store lock is released before calling an injected Project Execution `start_project` port. The result is then recorded as `started`, `failed_retryable`, or `intervention_required` with bounded timestamps/code/history.

Repeated callbacks reconcile the durable intent:

- If the Project is already active, completed, or has an active attempt attributable to the occurrence, mark the intent started without launching again.
- If the intent is pending or retryable and the Project remains eligible, call the existing project-level start command outside the root lock.
- Project Execution's project-scoped atomic gates prevent two callbacks from establishing conflicting active attempts.
- A failure to start does not roll back or duplicate the already committed Project. Retry uses the same occurrence and Project ID.

The Agent recurrence HTTP handler supplies the injected start port; `ProjectAuthoringService` does not import `server.py`. Existing recurrence and authoring feature flags gate creation and dispatch. Disabling recurrence prevents new occurrence materialization/reconciliation; already started execution follows existing Project Execution controls.

Alternative considered: call Project Execution inside the occurrence root transaction. Rejected because workspace/provider/launcher work can block and can write through a different repository boundary, creating lock-order and partial-commit hazards.

Alternative considered: start without a durable intent after returning creation success. Rejected because a crash between commit and launch would permanently lose the user's separately confirmed automatic-execution request.

### 8. Preserve public compatibility and add focused observability

No public route is added. Existing JSON fields remain accepted; Agent omission of `projectExecutionEnabled` intentionally changes from disabled to enabled. New recurrence execution mode is optional and defaults to `create_only` for existing definitions.

Existing authoring observability records direct-create and occurrence request outcomes. Add bounded operation/status counters and occurrence history for automatic start requested, started, retryable failure, and intervention. Logs use existing sanitization/rate limiting and do not include workspace credentials, grant secrets, confirmation text, or provider output.

Materialization itself is O(columns + tasks + checklist items), which matches existing builders and introduces no external calls or additional persistence. Column and checklist inputs remain bounded by existing request/task limits; tests add explicit large-valid-fixture coverage rather than introducing a new worker or queue.

## Risks / Trade-offs

- **[Compatibility] Canonical defaults expose accidental differences that HTTP clients or local CLI automation may rely on.** → Characterize every current entry point first, compare allowed overlays explicitly, and retain public response, CLI output/arguments, and storage readability.
- **[Safety] Historical template false may have been synthesized rather than user-selected.** → Treat stored false as disabled; do not guess or auto-enable historical automation. New snapshots persist explicit intent.
- **[Consistency] Automatic occurrence start can crash after Project commit.** → Persist the execution intent in the same occurrence commit and reconcile it on repeated callbacks.
- **[Concurrency] Two recurrence callbacks may race to start the same Project.** → Reuse the existing occurrence claim plus Project Execution project-scoped start gates; never launch while holding the root-store lock.
- **[Rollback] Old code ignores new automatic-start intent fields.** → Fields are additive; disabling recurrence stops new dispatch, and code rollback leaves created Projects readable but may leave pending intents inert until the new code is restored or the user starts them manually.
- **[Security] Default-enabled Agent creation can allocate workspaces unexpectedly.** → Require explicit user confirmation displaying execution behavior, validate the registered executor, retain bounded body/task limits, and fail closed before commit.
- **[Observability] Materialization parity failures may be silent.** → Add cross-entry-point contract tests and source-specific failure counters; retain sanitized operation logs.

## Migration Plan

1. Land pure materializer tests and implementation with no callers.
2. Migrate manual commands, browser template creation, local `office.py --proj create`/`add-task` writers, and confirmed Agent maintenance Task creation; run project command, CLI, maintenance, template compatibility, persistence, and Project Execution regressions.
3. Update Agent validation, confirmation template/docs, and direct creation; deploy with `VO_AGENT_PROJECT_AUTHORING_ENABLED` off, then verify enabled and tracking-only creation in an isolated workspace.
4. Migrate versioned template and recurrence creation with `VO_PROJECT_INSTANCE_RECURRENCE_ENABLED` off.
5. Enable create-only recurrence first. Verify occurrence idempotency, workspace cleanup, and bounded history.
6. Enable separately confirmed create-and-execute recurrence; verify pending-intent recovery, duplicate callbacks, start failures, and intervention visibility.
7. Remove duplicate builders and repair helpers only after static caller checks and the full focused regression pass.

Rollback disables Agent authoring and recurrence dispatch before reverting code. No data backfill is required. Projects created by the new code remain readable by the old code; additive recurrence execution-intent fields may remain inert. Any occurrence Project already started is stopped or completed through existing Project Execution controls rather than deleted.

## Open Questions

None. Product execution defaults, tracking-only behavior, project-level start scope, recurring start choice, and historical-project non-migration were explicitly confirmed before this design.
