# Project Task Orchestration Operations

This document is the developer and operator reference for the
`stage_pipeline_v1` project task orchestration contract introduced by
OpenSpec change `add-project-task-orchestration`.

## Ownership

The orchestration implementation is intentionally split by responsibility:

- `app/services/project_orchestration.py`
  - Owns the pure stage-pipeline model: execution marker, orchestration states,
    contiguous stage validation, completed-stage locks, accepted terminal
    evaluation, active-task projections, and skip-state helpers.
- `app/services/project_orchestration_commands.py`
  - Owns repository-backed orchestration edits, including full-assignment
    auto-save, optimistic revision validation, editable-state checks, and
    completed-stage immutability.
- `app/services/project_stage_dispatch.py`
  - Owns stage reservation, bounded task submission, reserved-attempt
    preparation, idempotent stage reconciliation, queue rejection handling, and
    paused-project resume.
- `app/services/project_orchestration_pause.py`
  - Owns two-phase pause and re-orchestration convergence.
- `app/services/project_orchestration_skip.py`
  - Owns task-owner skip requests and management-authorized skip decisions.
- `app/services/project_orchestration_recovery.py`
  - Owns startup recovery for marked projects in `starting`, `running`, and
    `pausing`.
- `app/services/project_orchestration_observability.py`
  - Owns bounded structured diagnostics and project audit event construction.
- `app/services/project_scheduling_orchestration.py`
  - Owns schedule and cron decisions that must respect stage eligibility.
- `app/project-orchestration.js`, `app/project-orchestration-api.js`, and
  `app/project-orchestration.css`
  - Own the modal runtime, API adapter, and Figma-scoped visual styling.

Legacy entry points such as `app/server.py`, `app/server_services/projects.py`,
and `app/projects.js` should stay thin: route registration, dependency wiring,
compatibility delegation, and refresh hooks only. New orchestration business
logic belongs in the focused modules above.

## Durable Storage Fields

Marked projects use the canonical Markdown project store. The required project
fields are:

- `executionModel: stage_pipeline_v1`
- `orchestration.schemaVersion`
- `orchestration.revision`
- `orchestration.state`
- `orchestration.currentStage`
- `orchestration.currentRunId`
- `orchestration.pauseReason`
- `orchestration.startedAt`
- `orchestration.completedAt`
- `orchestration.pauseSnapshot` while a pause is in progress or preserved for
  audit
- `orchestrationAudit`, a bounded recent audit list for durable orchestration
  diagnostics

The required task fields are:

- `executionStage`
- `stageRunId`
- `activeAttemptId`
- `attempts[*].stageRunId`
- `orchestrationSkip`
- `orchestrationSkipHistory`

Every editable marked project must have exactly one positive `executionStage`
per task, and occupied stage numbers must remain contiguous starting at `1`.
Completed tasks in completed stages are immutable during paused
re-orchestration. Attempt history and workspace snapshots must be preserved
across pause, resume, recovery, and completion.

## Removed Authorities

For marked projects, stage orchestration is the only task-eligibility authority.
Do not reintroduce these fields or treat them as hidden compatibility switches:

- `projectExecutionStartMode`
- `projectExecutionFlowActive`
- `projectExecutionFlowStopReason`
- `workflowActive`
- `workflowPhase`
- `activeTaskId`
- `activeAgent`
- `autoMode`
- `executionPolicy.maxActiveTasks`
- task `executionOrder`

Legacy request fields that select a free/single/manual progression mode are
rejected for marked projects, including `mode`, `startMode`, and
`restartPipeline`. Per-task manual start is also rejected for marked projects.

## API Contracts

Stable orchestration routes:

- `PUT /api/projects/{projectId}/orchestration`
  - Body: `{ revision, assignments: [{ taskId, executionStage }] }`
  - Persists one complete, normalized assignment in a single repository update.
  - Increments `orchestration.revision` on success.
  - Returns HTTP `409` with authoritative `currentRevision`, `orchestration`,
    and normalized `assignments` when the client revision is stale.
- `POST /api/projects/{projectId}/project-execution/start`
  - Starts a marked project by reserving the first/current eligible stage.
  - Rejects legacy progression payload fields.
  - Performs whole-stage preflight before any mutation.
- `POST /api/projects/{projectId}/project-execution/pause`
  - Requires explicit confirmation and management authority.
  - Enters `pausing` and snapshots active attempts.
- `POST /api/projects/{projectId}/project-execution/pause/complete`
  - Performs phase-two pause convergence after provider cancellation.
- `POST /api/projects/{projectId}/project-execution/resume`
  - Reserves and starts the first unfinished stage for a paused project.
- `POST /api/projects/{projectId}/tasks/{taskId}/orchestration-skip/request`
  - Records a responsible actor's skip request and reason.
- `POST /api/projects/{projectId}/tasks/{taskId}/orchestration-skip/decision`
  - Approves or rejects a pending skip request with management authority.

Projected response fields for marked projects include `activeTaskIds`,
`activeTaskCount`, `currentStage`, `orchestrationState`, and `pauseReason`.
Singular active-task fields are display fallbacks only and must not become
execution authority.

## Concurrency Limits

Logical parallelism is stage-based: every dispatchable task in the current
stage is submitted together, and no later-stage task can start before all
current-stage tasks reach accepted terminal outcomes.

Physical startup is bounded by `BoundedProjectExecutionDispatcher`:

- default workers: `8`
- default queue capacity: `100`

These are process safety controls, not user-editable project progression
settings. A full queue returns `dispatch_queue_full`, blocks the affected task,
sets the project to `blocked`, preserves already accepted submissions, and does
not start a later stage.

Stage reconciliation is idempotent on `(projectId, currentRunId)`. Duplicate or
stale terminal callbacks are suppressed and reported through diagnostics rather
than advancing a second time.

## Authorization Mapping

The current product does not introduce a new multi-user RBAC system for this
change. Browser owner/manager orchestration authority maps to the existing
management-token-authenticated management surface.

Authorization expectations:

- Auto-save, explicit start, pause, resume, and skip decisions require
  management/owner authority.
- Skip requests must come from the task's responsible actor, executor, or
  assignee as represented on the task.
- Schedule and recurrence dispatch may start marked projects only through the
  project-level orchestration path. Task-targeted cron cannot bypass stage
  eligibility.
- HTTP handlers must reject forged cross-project task links and stale revision
  writes without mutating durable state.

## Diagnostics

Orchestration services return structured `diagnostics` objects with:

- `operation`
- `status`
- `counters`
- `timings`
- `audit`

The audit context includes the available `projectId`, `taskId`, `stage`,
`runId`, `attemptId`, and `revision`. Operation names currently include:

- `reservation`
- `submission`
- `duplicateSuppression`
- `stageAdvancement`
- `pause`
- `skipDecision`
- `recovery`
- `autoSave`
- `autoSaveConflict`
- `stuckState`

Durable `orchestrationAudit` entries are appended for state-changing operations
such as reservations, auto-save, stage advancement/completion, pause, and skip
decisions. The list is bounded to the most recent `100` events.

## Recovery

Startup recovery scans marked projects in `starting`, `running`, and
`pausing`:

- `pausing` projects repeat pause convergence.
- Live active attempts are preserved and their active pointers repaired.
- Reserved tasks without attempts are prepared and resubmitted with the same
  `currentRunId`.
- Non-resumable active attempts block the stage with
  `stage_attempt_not_resumable_after_restart` and emit `stuckState`
  diagnostics.

Recovery must never create duplicate attempts for the same
`(projectId, taskId, currentRunId)`.

## No JSONL Decision

The confirmed storage contract is the canonical Markdown project store. The
orchestration marker and state are stored in project frontmatter and task
records. Do not add a JSONL shadow log or JSONL marker for orchestration state.

Rationale:

- A JSONL mirror would create a second state authority.
- Legacy callers could accidentally treat the mirror as writable truth.
- Restart recovery depends on canonical project/task state, not append-only
  event replay.
- The current audit need is bounded, credential-safe operational diagnostics,
  which is covered by `orchestrationAudit` and response `diagnostics`.

## Release Gates

Before production release, operators must review:

- `openspec/changes/add-project-task-orchestration/evidence/task-9.4-complete-regression.md`
  for broad regression gates.
- Backup and cleanup evidence from task `10.2`.
- Rollback rehearsal evidence from task `10.3`.
- Manual/live acceptance evidence from tasks `10.4` and `10.5`.
- Final strict validation evidence from task `10.6`.

