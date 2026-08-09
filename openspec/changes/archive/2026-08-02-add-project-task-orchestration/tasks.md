## 1. Baseline, overlap, and removal inventory

- [x] 1.1 Record an evidence-backed inventory of every reader and writer of `projectExecutionStartMode`, `projectExecutionFlowActive`, `projectExecutionFlowStopReason`, `workflowActive`, `workflowPhase`, `activeTaskId`, `activeAgent`, `autoMode`, `executionPolicy.maxActiveTasks`, and task `executionOrder`, including storage, materializers, commands, lifecycle, review, schedules, realtime, chat, frontend, and tests.
- [x] 1.2 Re-read `unify-project-materialization`, `add-agent-managed-vo-projects`, and `add-project-workflow-chat-realtime-stream`; document overlapping contracts and the implementation order required to preserve their confirmed behavior.
- [x] 1.3 Add failing-before characterization tests for single/continuous project start, unique execution order, singular active-task projection, task-level manual start, completion-triggered next-task start, restart recovery, and scheduled execution.
- [x] 1.4 Add a read-only release preflight command that inventories canonical projects lacking `executionModel: stage_pipeline_v1`, emits exact backup/deletion candidates, and never deletes project data.

## 2. Canonical orchestration model and storage

- [x] 2.1 Implement `app/services/project_orchestration.py` with the execution-model marker, orchestration states, positive contiguous-stage validation, stage compaction, completed-stage locks, accepted-terminal evaluation, and derived active-task projections; add pure table-driven tests.
- [x] 2.2 Extend `MarkdownProjectStore` round-trip support for `executionModel`, `orchestration`, task `executionStage`, `stageRunId`, and `orchestrationSkip`, including malformed-frontmatter rejection or repair tests.
- [x] 2.3 Update canonical project/task materialization so every new project receives `stage_pipeline_v1`, draft orchestration state, and every initial task receives a valid stage without writing old progression-mode authorities.
- [x] 2.4 Update manual browser, Agent direct-create, versioned-template, legacy-template adaptation, and recurrence materialization paths to produce the same marked orchestration contract; add parity tests across all creation sources.
- [x] 2.5 Update project-authoring validation and template snapshots to accept `executionStage`, reject incomplete/non-contiguous assignments, and stop emitting `projectExecutionStartMode`, `executionPolicy.maxActiveTasks`, or `executionOrder`.

## 3. Auto-save orchestration commands and API

- [x] 3.1 Implement `app/services/project_orchestration_commands.py` with full-assignment auto-save, optimistic revision checking, project-state editability, completed-task locks, contiguous normalization, and atomic repository updates; add command tests.
- [x] 3.2 Extend task creation and deletion commands so modal-created tasks default to `max(executionStage) + 1`, deleting an empty stage compacts later unfinished stages, and locked projects reject ordinary structural edits.
- [x] 3.3 Add the management-token-protected `PUT /api/projects/{projectId}/orchestration` transport delegate with stable success, validation, stale-revision, authorization, and persistence-failure responses.
- [x] 3.4 Add API and client-contract tests proving one completed drag produces one atomic full-assignment write, stale revisions return HTTP 409 with authoritative state, and rejected writes are not presented as saved.

## 4. Stage reservation and bounded parallel dispatch

- [x] 4.1 Implement a reusable bounded project-execution dispatcher with 8 workers, a queue bounded by the authored-task limit, deterministic shutdown/test hooks, queue-depth diagnostics, and rejection tests.
- [x] 4.2 Implement `app/services/project_stage_dispatch.py` stage preflight and atomic reservation using `currentRunId`, including whole-stage workspace, dirty-state, executor, reviewer, active-attempt, marker, revision, and authorization checks.
- [x] 4.3 Refactor task-start preparation so internally reserved tasks in the same current stage can create task-level attempts concurrently and idempotently without consulting a singular project active-task authority.
- [x] 4.4 Replace project-start mode selection with explicit marked-project start that reserves and submits stage 1, aggregates all preflight blockers before mutation, and rejects task-level manual start for marked projects.
- [x] 4.5 Add bounded-queue and partial-submission handling that preserves already submitted task truth, blocks the stage with `dispatch_queue_full`, and never starts a later stage.

## 5. Terminal reconciliation, exception handling, and completion

- [x] 5.1 Implement idempotent stage reconciliation keyed by `(projectId, currentRunId)` so concurrent terminal callbacks advance exactly once only after every current-stage task has an accepted terminal outcome.
- [x] 5.2 Migrate execution completion, review, rework, checklist completion, acceptance, meeting resolution, and retry callbacks to reconcile the stage instead of toggling flow flags or starting one next task.
- [x] 5.3 Implement task-owner skip requests and management-authorized approve/reject decisions with separate orchestration-skip state, reasons, timestamps, audit history, and no reuse of review-skipped semantics.
- [x] 5.4 Add skip request/decision API delegates and tests for requester linkage, management-token authorization, approval idempotency, rejection, cross-project forgery, and races with task completion.
- [x] 5.5 Implement automatic final-project completion after the final stage reaches accepted outcomes, while requiring human acceptance to be represented as a normal pipeline task; add notification and idempotency tests.

## 6. Pause, re-orchestration, resume, and recovery

- [x] 6.1 Implement the phase-one pause command that atomically enters `pausing`, blocks dispatch/advancement, snapshots active attempt IDs, increments revision, and requires explicit confirmation.
- [x] 6.2 Implement lock-free provider cancellation followed by phase-two atomic convergence that records cancelled attempts, returns unfinished tasks to pending, preserves workspace/attempt history, and enters `paused`.
- [x] 6.3 Implement paused-project editing and explicit resume so completed stages remain immutable, unfinished stages normalize after the last completed stage, and resumed tasks execute from the beginning under a new run ID.
- [x] 6.4 Add pause/resume transport delegates and tests for partial cancellation, cancellation failure, pause-versus-completion races, repeated requests, and forbidden edit/start transitions.
- [x] 6.5 Replace startup recovery with run-aware reconciliation for `starting`, `running`, and `pausing` projects, including idempotent reserved-task resubmission, live-attempt preservation, non-resumable blocking, and no duplicate attempts.

## 7. Scheduling, projections, chat, and legacy authority removal

- [x] 7.1 Update project recurrence and project-level cron dispatch to start marked pipelines, reject later-stage task cron bypass, and derive already-active/completed decisions from orchestration plus task attempts.
- [x] 7.2 Replace singular dashboard and project response fields with `activeTaskIds`, `activeTaskCount`, `currentStage`, `orchestrationState`, and `pauseReason`; update SSE/WebSocket diff tests.
- [x] 7.3 Update project workflow chat to accept explicit task scope when multiple stage tasks are active and use most-recent active task only as a display fallback, never as execution authority.
- [x] 7.4 Remove old progression fields from project/task serializers, materializers, commands, handlers, templates, notifications, frontend state, localization, and tests after their callers have migrated.
- [x] 7.5 Remove marked-project support for `mode`, `startMode`, `restartPipeline`, task-level start, and manual next-task progression; add static checks proving no reachable caller can restore legacy behavior.
- [x] 7.6 Add full storage and route contract tests proving marked projects persist only the new authority and survive reload without reintroducing deleted fields.

## 8. Figma-aligned orchestration frontend

- [x] 8.1 Capture reference screenshots and computed specifications for Figma frame `147:2` and modal `148:3`, recording the approved deletion of the save action as the only intentional visual delta.
- [x] 8.2 Create `app/project-orchestration.css` with scoped Figma-derived typography, dimensions, spacing, colors, borders, radii, shadows, modal geometry, task cards, parallel groups, arrows, footer layout, and responsive containment.
- [x] 8.3 Create `app/project-orchestration.js` with isolated modal rendering, task/stage view models, lifecycle cleanup, close/reopen behavior, and fit-canvas controls using the existing `Press Start 2P` font.
- [x] 8.4 Implement drag/drop and add-task interactions with positive contiguous stages, default maximum-stage-plus-one placement, one auto-save call per completed edit, visible saving/error/conflict states, and authoritative reload on HTTP 409.
- [x] 8.5 Implement frontend locked, running, blocked, pausing, paused, skip-request, skip-decision, resume, and completed states without exposing free-mode or per-task start controls.
- [x] 8.6 Wire the project page to the focused frontend module through thin entry and refresh hooks, remove the legacy execution-order editor and start-mode radio controls, and update localized copy.
- [x] 8.7 Add DOM/runtime tests for modal rendering, drag/drop, auto-save success/failure/conflict, add-task default stage, fit canvas, close/reopen persistence, locking, pause/re-orchestration, skip approval, and removal of the save button.
- [x] 8.8 Add deterministic screenshot tests at the 1512×742 reference viewport and compare the complete overlay, 1220×560 modal, 1184×350 canvas, typography, card states, parallel grouping, and footer against Figma evidence.

## 9. Concurrency, observability, and regression verification

- [x] 9.1 Add deterministic concurrency tests for duplicate start, duplicate terminal callback, simultaneous parallel completions, completion-versus-pause, skip-versus-completion, stale auto-save, and recovery-versus-live execution.
- [x] 9.2 Add structured counters, timings, and audit fields for reservations, submissions, queue rejection, duplicate suppression, stage advancement, pauses, skip decisions, recovery, auto-save conflicts, project/task/stage/run/attempt/revision, and stuck-state detection.
- [x] 9.3 Run focused storage, materialization, command, lifecycle, review, schedule, realtime, chat, frontend, security, and visual tests; record commands, results, failures, and unverified scenarios in change evidence.
- [x] 9.4 Run the complete Python, JavaScript, static dependency, persistence, provider, SSE/WebSocket, notification, workflow, schedule, and OpenSpec strict regression suites; fix or explicitly gate every regression.

## 10. Release preparation, rollback, and acceptance

- [x] 10.1 Update developer and operational documentation with module ownership, new storage fields, removed authorities, API contracts, concurrency limits, authorization mapping, diagnostics, and the no-JSONL decision.
- [x] 10.2 Back up the exact status directory, run the read-only legacy-project preflight, obtain separate explicit approval for destructive cleanup, remove only confirmed legacy project records, and record recoverability evidence.
- [x] 10.3 Rehearse the maintenance-window deployment and rollback: invariant check, coordinated backend/frontend activation, new-project smoke flow, service stop, previous-code restore, project-store restore, and post-restore validation.
- [x] 10.4 Complete manual acceptance for create → auto-save → explicit start → parallel stage → automatic next stage → final completion, plus failure, skip approval, pause/re-orchestration, restart recovery, schedule, permissions, and concurrent editing.
- [x] 10.5 Complete final Figma visual acceptance and attach reference/candidate screenshots, measured geometry, intentional-difference record, and any environment-dependent font notes.
- [x] 10.6 Run final `openspec validate --strict`, attach test and release evidence, and verify every confirmed requirement and scenario is traceable to completed tasks before requesting test-result confirmation.

## 11. Task final-result artifacts and stage handoffs

- [x] 11.1 Add a focused final-result module that renders `TASK_FINAL_RESULT.md`, builds task `finalResult` indexes, and creates compact prior-stage prompt blocks.
- [x] 11.2 Persist task `finalResult` metadata in canonical Markdown task frontmatter and regenerate `TASK_FINAL_RESULT.md` during store rewrites.
- [x] 11.3 Record or fallback-generate a task final result when a task reaches accepted terminal state, including skipped-task handling.
- [x] 11.4 Build `orchestration.stageHandoffs` from completed stage task results during reconciliation.
- [x] 11.5 Inject prior-stage result indexes into later-stage execution prompts without inlining full result bodies by default.
- [x] 11.6 Add focused storage, lifecycle, stage-reconciliation, prompt, and real-project smoke tests for final-result handoff behavior.
