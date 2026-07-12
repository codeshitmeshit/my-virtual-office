## ADDED Requirements

### Requirement: Incremental project-domain extraction
The system SHALL migrate project execution behavior from the HTTP handler into cohesive project-domain services in independently testable slices, and each migrated slice SHALL remain deployable without requiring later slices.

#### Scenario: One service slice is migrated
- **WHEN** a project-domain operation has been migrated and its compatibility tests pass
- **THEN** the HTTP handler SHALL delegate that operation to the extracted service
- **AND** project operations outside that slice SHALL continue to use their existing implementation

#### Scenario: A slice has not passed compatibility tests
- **WHEN** a proposed service slice has an unresolved behavior difference
- **THEN** the existing handler orchestration SHALL remain in place for that slice

### Requirement: Explicit project service dependencies
Project-domain services MUST accept validated application inputs and explicit persistence, workspace, provider, clock, notification, and scheduling dependencies as needed, without reading HTTP handler state or writing HTTP responses.

#### Scenario: Service is tested without an HTTP server
- **WHEN** a test invokes an extracted project service with test dependencies
- **THEN** the operation SHALL complete without constructing an HTTP handler or network server
- **AND** its result and state changes SHALL be assertable as application data

### Requirement: Project and task behavior compatibility
Extracted project and task operations MUST preserve existing validation, project linkage, field semantics, ordering, identifiers, timestamps, persistence formats, and externally observable API behavior.

#### Scenario: Existing project or task operation is delegated
- **WHEN** a client invokes a migrated project or task endpoint with a previously supported request
- **THEN** the response status and payload SHALL remain compatible
- **AND** the persisted project record SHALL remain readable by code and data created before the extraction

#### Scenario: Invalid project or task input is submitted
- **WHEN** existing validation rejects a project or task operation
- **THEN** the extracted service SHALL preserve the rejection without a partial state mutation

### Requirement: Execution lifecycle invariants
The extracted execution lifecycle SHALL preserve task eligibility, active-task and active-attempt ownership, execution-state transitions, concurrency controls, workspace safety gates, retry behavior, and provider invocation ordering.

#### Scenario: Eligible task execution starts
- **WHEN** an eligible task passes all existing execution and workspace gates
- **THEN** the service SHALL establish the same active task, attempt, and execution state before provider work begins

#### Scenario: Execution gate rejects a task
- **WHEN** the task is ineligible, another incompatible execution is active, or workspace validation fails
- **THEN** provider execution SHALL not start
- **AND** the existing failure state and client-visible result SHALL be preserved

#### Scenario: Git workspace snapshot fails
- **WHEN** a validated Git workspace cannot produce its dirty-state snapshot because the Git command fails or times out
- **THEN** provider execution SHALL not start
- **AND** the API SHALL return HTTP 409 with a stable workspace-snapshot failure code

#### Scenario: Workspace is not a Git repository
- **WHEN** the validated workspace is not a Git repository
- **THEN** the absence of a Git snapshot SHALL not by itself block execution

#### Scenario: Provider execution fails
- **WHEN** provider startup or execution raises an error
- **THEN** the service SHALL preserve existing failure recording, cleanup, retry eligibility, and active-attempt semantics

### Requirement: Review, rework, and acceptance gates
The extracted review workflow MUST preserve reviewer assignment, review eligibility, human confirmation, rework transitions, acceptance transitions, idempotency, and the rule that a task is not completed before all required gates succeed.

#### Scenario: Work enters review
- **WHEN** an execution attempt completes and review is required
- **THEN** the same reviewer selection and reviewing state SHALL be established
- **AND** acceptance SHALL remain unavailable until the existing review conditions are satisfied

#### Scenario: Reviewer requests rework
- **WHEN** an authorized review action requests rework
- **THEN** the service SHALL preserve the existing feedback, attempt linkage, execution transition, and notification behavior

#### Scenario: Acceptance action is repeated
- **WHEN** the same valid acceptance action is delivered more than once
- **THEN** the resulting project and task state SHALL be equivalent to applying it once
- **AND** the system SHALL persist one stable local side-effect intent for that accepted transition
- **AND** external delivery SHALL use the existing best-effort semantics without claiming exactly-once delivery

### Requirement: Artifact access and workspace safety
Extracted artifact operations MUST preserve project and attempt authorization, path normalization, workspace containment, file existence and type checks, content limits, and existing response semantics.

#### Scenario: Valid artifact is requested
- **WHEN** an authorized request references an artifact inside the validated project workspace
- **THEN** the service SHALL return the same artifact metadata or content as before extraction

#### Scenario: Artifact path escapes the workspace
- **WHEN** a requested artifact resolves outside the validated project workspace
- **THEN** access SHALL be rejected
- **AND** no out-of-workspace file metadata or content SHALL be disclosed

### Requirement: Scheduling and recovery compatibility
Extracted scheduling operations SHALL preserve repeat configuration, due-time evaluation, duplicate-run prevention, restart recovery, blocked-task behavior, and linkage between scheduled runs, projects, tasks, and attempts.

#### Scenario: Scheduled task becomes due
- **WHEN** a configured project task becomes due and all existing eligibility conditions pass
- **THEN** exactly one compatible execution attempt SHALL be scheduled for that due occurrence

#### Scenario: Scheduler evaluates an ineligible task
- **WHEN** a task is blocked, already active, completed, or otherwise ineligible
- **THEN** the scheduler SHALL not create a conflicting attempt
- **AND** the existing scheduling metadata and next-run behavior SHALL be preserved

#### Scenario: Application restarts with persisted scheduling state
- **WHEN** the application loads project data written before or during the extraction
- **THEN** scheduling and recovery SHALL continue without a data migration or duplicate execution

### Requirement: Project-scoped atomic state updates
Migrated project execution commands MUST apply their state validation and durable mutation through a project-scoped atomic update boundary so concurrent commands for the same project cannot overwrite committed state or create duplicate active attempts.

#### Scenario: Two commands update the same project concurrently
- **WHEN** concurrent migrated commands target the same project
- **THEN** their state validation and durable mutations SHALL be serialized for that project
- **AND** each command SHALL observe the state committed by the command that completed before it

#### Scenario: Commands target different projects
- **WHEN** migrated commands update different projects concurrently
- **THEN** their validation and slow external work SHALL not be serialized by another project's lock
- **AND** their short durable commits MAY be serialized by the shared full-project store

#### Scenario: Command invokes a slow external dependency
- **WHEN** a command needs provider, notification, filesystem, gateway, or other network work
- **THEN** the project update lock SHALL not be held during that slow external operation
- **AND** the command SHALL re-enter an atomic update boundary before committing a result that depends on current project state

### Requirement: API, event, and storage compatibility
The change MUST NOT intentionally alter public route paths, accepted request fields, response JSON fields, status semantics, persisted project records, SSE events, WebSocket behavior, frontend calls, provider protocols, or notification payloads.

#### Scenario: Compatibility regression suite runs
- **WHEN** service, HTTP contract, persistence, SSE, notification, and scheduling regression tests are run for migrated slices
- **THEN** all previously supported scenarios SHALL remain valid unless a separately confirmed specification explicitly changes them

### Requirement: Verified defect correction during migration
The change SHALL permit correction of a defect discovered in a migrated slice only when the behavior is reproducible, the expected behavior follows an existing product or safety invariant, and a regression test distinguishes the correction from migration-caused drift.

#### Scenario: Confirmed bug is found in the active slice
- **WHEN** migration work exposes a reproducible defect within the active slice
- **THEN** the defect MAY be fixed in that slice
- **AND** the change SHALL include a failing-before regression scenario and document the intentional behavior difference

#### Scenario: Suspected issue lacks evidence or expected behavior
- **WHEN** an observation cannot be reproduced or its correct product behavior is ambiguous
- **THEN** it SHALL not be changed as an incidental bug fix
- **AND** implementation SHALL pause for specification clarification if resolving it is required to continue the slice

#### Scenario: Defect is outside the active slice
- **WHEN** migration work discovers a defect outside the currently authorized service slice
- **THEN** the defect SHALL be recorded for a separately scoped task or specification update
- **AND** unrelated code SHALL not be changed under the migration task

### Requirement: Measured backend performance improvement
The change MUST improve evidenced backend bottlenecks in migrated project execution paths by reducing redundant persistence operations or repeated scans while preserving state, API, event, and storage compatibility; each optimization SHALL be supported by a reproducible pre-change baseline and post-change measurement.

#### Scenario: Migrated operation persists state
- **WHEN** a migrated operation follows a previously supported success or failure path
- **THEN** it SHALL not perform more durable writes, project-store reads, or provider invocations than the equivalent pre-extraction path

#### Scenario: Redundant persistence or scan is optimized
- **WHEN** a migrated path has a reproducible redundant read, write, or repeated scan
- **THEN** the optimization SHALL record the baseline operation count or elapsed-time fixture and the post-change result
- **AND** compatibility and concurrency regression tests SHALL pass

#### Scenario: Performance result cannot be measured reliably
- **WHEN** an optimization lacks a stable baseline or its expected benefit cannot be distinguished from measurement noise
- **THEN** it SHALL not be claimed as a performance improvement
- **AND** the behavior-preserving extraction SHALL proceed without that speculative optimization

### Requirement: Backend-only experience scope
This change SHALL limit experience improvements to backend latency, throughput, reliability, and error correctness in project execution paths, and MUST NOT introduce project-page interaction or visual redesign.

#### Scenario: Frontend change is proposed during migration
- **WHEN** a proposed adjustment changes project-page layout, interaction, styling, or client workflow
- **THEN** it SHALL be excluded from this change unless a separate specification is confirmed
