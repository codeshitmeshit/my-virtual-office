## Context

The current implementation has introduced an `executionOrder` task field and UI badges. Recent product clarification changed the intended meaning: users need an execution batch number, not a globally unique linear ID. Same-number tasks form one batch and are eligible to run concurrently as one project-flow step.

Existing project data, templates, authoring, recurrence, and execution tests already reference `executionOrder`, so the design must avoid a breaking rename while changing the product semantics and state-machine behavior.

## Design Decisions

### 1. Keep `executionOrder` as the compatibility storage field for this change

Use `executionOrder` as the persisted compatibility field, but treat and label it as `executionBatch` in product surfaces and helper APIs. Introduce a focused project execution-batch helper module that owns:

- effective batch calculation for legacy records with missing values;
- validation of positive integer batch values;
- batch grouping and lowest-unfinished-batch selection;
- batch edit eligibility checks;
- compatibility aliases between UI/API wording and persisted `executionOrder`.

This avoids a destructive migration and prevents another round of template/recurrence/backward-compatibility churn. A later migration may introduce a new persisted `executionBatch` field after compatibility behavior is proven.

### 2. Allow duplicate batch numbers and remove uniqueness as a validation rule

The previous uniqueness validation must be removed or relaxed. Validity is:

- the batch value is a positive integer;
- duplicate values are allowed;
- duplicate values mean same concurrent batch;
- effective legacy values may collide only if the project has intentionally grouped those tasks or if read-repair/backfill normalizes them.

The editor should validate only positivity and edit-boundary constraints, not uniqueness.

### 3. Batch editing is project-wide and state-aware

The existing order editor should become a project batch editor:

- list every task exactly once;
- show title plus column/state;
- allow duplicate positive batch numbers;
- prevent started or historical tasks from changing batch;
- prevent unstarted tasks from moving into batches that have already started or completed;
- write all changed task batch values through existing task update paths so audit/timestamps remain compatible.

State-aware edit protection must be enforced server-side. UI disabled inputs are only convenience.

### 4. Project-level execution selects a batch, not a single task

Replace single-task project start selection with batch selection:

1. Compute the lowest unfinished effective batch.
2. If any task in that batch is active, reviewing, blocked, awaiting acceptance, or otherwise not terminal, project flow remains on that batch.
3. Starting the project attempts to start every startable task in the selected batch.
4. If any task in the selected batch cannot start because of a prerequisite failure, later batches are not considered and the response surfaces that batch-level correction requirement.
5. The project flow advances only when every task in the selected batch has passed execution/review/acceptance completion semantics.

Direct task start remains supported only when the task is in the current lowest unfinished batch. Starting a later batch task directly remains rejected.

### 5. Concurrency model uses existing per-task attempts

Do not introduce a separate batch attempt object in the first implementation. Batch execution is an orchestration layer over existing task attempts:

- each task keeps its own attempt, review, evidence, acceptance, cancellation, retry, and notification state;
- project-level state records the active batch number for summary and blocking;
- existing task-level cancellation/retry remains available;
- batch completion is derived from task states.

This limits the blast radius while enabling parallel task attempts in one batch. If batch-level audit or retry UX becomes insufficient, a later change can add a first-class batch attempt record.

### 6. Authoring, templates, and recurrence preserve batches

All creation paths should assign or preserve execution batches:

- manual project/task creation defaults to the next future batch unless specified;
- Agent authoring proposal and structured payload include batch values;
- template snapshots persist task batch values;
- recurrence materialization copies template batch values;
- legacy templates without values receive compatible defaults.

### 7. Rollout and compatibility

The change should be backward-readable and deployable with existing flags:

- legacy projects without `executionOrder` continue to display and execute via effective batch fallback;
- projects with previously unique order values behave like one task per batch;
- duplicate batch values become valid only after the complete batch execution and edit-boundary rules are in place;
- no automatic project execution should start as a side effect of read-repair/backfill.

## State Model

Task states are interpreted for batch orchestration:

- `not_started`: no active attempt and execution state is empty/backlog/blocked only when manually resolved to startable.
- `active`: validating, executing, retrying, reviewing, reworking, awaiting meeting resolution, awaiting user acceptance, or execution complete pending acceptance.
- `complete`: done/completed, completedAt set, or Project Execution acceptance/review gates have finished according to existing task completion helpers.
- `blocked`: blocked or failed states that require user intervention.

The batch state is derived:

- `pending`: every task in the batch is not started.
- `active`: at least one task active and none blocked.
- `blocked`: at least one task blocked/failed or a selected-batch task cannot start.
- `complete`: every task in the batch is complete.

## Technical Review

### 评审结论

带条件通过。The requirement is clear enough to proceed to a task plan, but implementation must first remove the uniqueness assumption and define server-side batch edit guards. The design must not rely only on UI validation.

### 阻塞问题

1. Existing code currently treats `executionOrder` as unique in update validation and editor validation.
   - Recommendation: remove uniqueness checks before allowing duplicate batches, and replace them with positive-integer and state-boundary checks.

2. Project Execution currently delegates to a single selected next task.
   - Recommendation: add batch-selection and batch-start orchestration before claiming the feature complete. Do not claim batch execution support while only one task starts.

3. Started-task edit boundaries require a server-side definition of historical states.
   - Recommendation: centralize batch edit eligibility in a service helper and cover each state with tests.

### 主要风险

- Stability: starting multiple task attempts at once can expose existing active-task blockers that assume one active task per project.
- Data consistency: two simultaneous batch edits or direct task starts can race unless validation happens inside the project-scoped update boundary.
- Compatibility: existing projects using unique values must continue as one-task-per-batch flows.
- Rollback: duplicate persisted `executionOrder` values may confuse older code that assumed uniqueness.
- Observability: project-level status needs enough detail to show which batch is active and which task blocked it.

### 关键追问

Q: Why keep `executionOrder` instead of immediately renaming storage?
A: It preserves compatibility with existing project, template, recurrence, and test data. Product copy and helper APIs can use "batch" while storage remains compatible.

Q: Why not add a first-class batch attempt record now?
A: Existing task attempts already own provider execution, review, acceptance, cancellation, and evidence. A derived batch state reduces blast radius for the first version.

Q: What happens if one task in a batch cannot start?
A: Later batches must not start. The batch becomes blocked with a correction requirement.

Q: What happens if all tasks in a batch are already complete?
A: The project flow skips that complete batch and selects the next lowest unfinished batch.

### 测试与上线建议

- Add command tests for duplicate positive batch values, invalid values, started-task edit rejection, and future-batch-only movement.
- Add materialization tests for manual create, Agent create, template instantiate, recurrence occurrence, and legacy fallback.
- Add execution lifecycle tests for starting all tasks in one batch, blocking on one failed task, no advancement until all complete, and direct later-batch start rejection.
- Add UI/browser verification that the editor lists all tasks and accepts duplicate batch numbers.
- Roll out as a compatibility change where existing unique orders behave as single-task batches.
