# Project Execution Service Boundaries Specification

## Purpose

Define the service ownership, compatibility, safety, concurrency, and measured backend-performance requirements for project execution workflows.
## Requirements
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
Extracted project and task operations MUST preserve validation, project linkage, identifiers, timestamps, and field semantics that remain part of the marked-new-project contract. They SHALL intentionally replace legacy free-execution and single-task progression semantics with execution-stage orchestration, and they SHALL NOT be required to keep unmarked legacy project records runnable after the pre-release cleanup.

#### Scenario: A marked project or task operation is delegated
- **WHEN** a client invokes a migrated project or task operation for a marked new project
- **THEN** the service SHALL preserve the orchestration marker, task-stage membership, contiguous-stage invariants, and current-stage lifecycle
- **AND** the persisted project record SHALL remain readable across restarts within the new contract

#### Scenario: Invalid project or task input is submitted
- **WHEN** an operation would leave a marked project with an unassigned task, a non-positive stage, a duplicate task identity, or a non-contiguous occupied stage sequence
- **THEN** the extracted service SHALL reject or normalize the operation according to the orchestration specification
- **AND** it SHALL NOT persist a partial invalid state

#### Scenario: An unmarked legacy project is encountered before release
- **WHEN** pre-release data inspection finds a project that lacks the orchestration marker
- **THEN** that project MAY be removed instead of migrated
- **AND** this change SHALL NOT require legacy execution compatibility for that record

### Requirement: Execution lifecycle invariants
The extracted execution lifecycle SHALL enforce stage eligibility, parallel current-stage dispatch, active-task and active-attempt ownership, execution-state transitions, concurrency controls, workspace safety gates, retry behavior, provider invocation ordering, exception pauses, and automatic transition to the next contiguous stage.

#### Scenario: Eligible stage execution starts
- **WHEN** an authorized user starts or resumes a valid marked project and every task in the current stage passes its execution and workspace gates
- **THEN** the service SHALL establish active attempts for every dispatchable task in that stage before their provider work begins
- **AND** no later-stage task SHALL become active

#### Scenario: One task fails its execution gate
- **WHEN** a current-stage task is ineligible, another incompatible execution owns that task, or workspace validation fails
- **THEN** provider execution SHALL not start for that task
- **AND** the stage SHALL pause without dispatching a later stage
- **AND** already valid parallel tasks in the same stage SHALL retain their truthful execution states

#### Scenario: Git workspace snapshot fails
- **WHEN** a validated Git workspace cannot produce its dirty-state snapshot because the Git command fails or times out
- **THEN** provider execution SHALL not start for the affected task
- **AND** the API SHALL return HTTP 409 with a stable workspace-snapshot failure code
- **AND** the stage SHALL not advance

#### Scenario: Workspace is not a Git repository
- **WHEN** the validated workspace is not a Git repository
- **THEN** the absence of a Git snapshot SHALL not by itself block execution

#### Scenario: Provider execution fails
- **WHEN** provider startup or execution raises an error for a current-stage task
- **THEN** the service SHALL preserve failure recording, cleanup, retry eligibility, and active-attempt semantics
- **AND** automatic advancement SHALL pause until the task completes or receives an approved skip

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
Extracted scheduling operations SHALL preserve repeat configuration, due-time evaluation, duplicate-run prevention, restart recovery, blocked-task behavior, and linkage between scheduled runs, projects, tasks, and attempts while enforcing marked-project stage eligibility.

#### Scenario: A scheduled marked project becomes due
- **WHEN** a configured project occurrence becomes due and its creation and execution policy permits automatic start
- **THEN** exactly one marked project instance SHALL be materialized for that occurrence
- **AND** its valid stage 1 tasks SHALL be dispatched under the orchestration contract

#### Scenario: Scheduler evaluates a later-stage task
- **WHEN** a scheduled or recovered task does not belong to the marked project's current stage
- **THEN** the scheduler SHALL not create an execution attempt for that task
- **AND** it SHALL preserve the current stage and existing scheduling metadata

#### Scenario: Application restarts with an active marked project
- **WHEN** the application loads a marked project with persisted current-stage and attempt state
- **THEN** recovery SHALL reconcile those attempts without duplicating execution
- **AND** it SHALL resume or pause advancement from the persisted orchestration state

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
The change MUST preserve route stability, authorization, project/task identity, atomic mutation safety, SSE and WebSocket delivery contracts, provider protocols, and notification integrity except where the confirmed orchestration specification explicitly replaces request fields, response fields, client workflow state, persisted project properties, and transitions used only for free execution or single-task/manual progression.

#### Scenario: A retained project execution contract is exercised
- **WHEN** a marked-project request uses a route or field that remains part of the orchestration contract
- **THEN** its validation, authorization, response, event, and durable side-effect semantics SHALL remain compatible unless another requirement in this change explicitly modifies them

#### Scenario: A removed progression contract is exercised
- **WHEN** a client submits a legacy mode selection or manual progression field that this change removes
- **THEN** the system SHALL NOT re-enable free or single-task progression for a marked project
- **AND** the response SHALL use a stable rejection or omission contract defined by the confirmed design

#### Scenario: Project state is persisted
- **WHEN** a marked project is created or its orchestration state changes
- **THEN** its canonical Markdown project representation SHALL preserve the orchestration marker, valid task stages, current execution stage, pause state, and durable attempt history required for restart recovery
- **AND** it SHALL omit obsolete properties whose only purpose was selecting or maintaining free or single-task progression

### Requirement: Verified defect correction during migration
The change SHALL permit correction of a defect discovered in a migrated slice only when the behavior is reproducible, the expected behavior follows an existing product or safety invariant, and a regression test distinguishes the correction from migration-caused drift.

#### Scenario: Confirmed bug is found in the active slice
- **WHEN** migration work exposes a reproducible defect within the active slice
- **THEN** the defect MAY be fixed in that slice
- **AND** the change SHALL include a failing-before regression scenario and document the intentional behavior difference

#### Scenario: Untrusted management mutation reaches the HTTP boundary
- **WHEN** a POST, PUT, or DELETE request targets a browser management mutation endpoint without a valid management token
- **THEN** the handler SHALL reject it before parsing or mutating project state
- **AND** the trusted project client SHALL attach the management token through the existing management-fetch flow

#### Scenario: Execution agent requests a meeting blocker
- **WHEN** the execution prompt posts to the dedicated task meeting-request endpoint without a browser management token
- **THEN** the existing agent bridge SHALL remain reachable
- **AND** the handler SHALL validate project/task linkage and the request body through the meeting-request command

#### Scenario: Managed-workspace deletion is requested
- **WHEN** project deletion requests removal of a system-managed workspace
- **THEN** deletion SHALL proceed only for a non-symlink descendant of the configured auto-workspace root
- **AND** the root itself and every path outside it SHALL be preserved

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

### Requirement: Obsolete execution-mode authorities are removed
The system MUST remove duplicate or obsolete state authorities that allow a marked new project to select free execution, single-task execution, or manual project advancement. Removal SHALL cover persisted properties, materialization defaults, service decisions, HTTP payload handling, realtime projections, frontend workflow state, and tests that would otherwise keep the old behavior reachable.

#### Scenario: A marked project is materialized
- **WHEN** any supported creation path creates a marked new project
- **THEN** no free-versus-continuous or single-task progression selector SHALL be persisted
- **AND** stage orchestration SHALL be the sole authority for project task eligibility

#### Scenario: A retained caller references an obsolete property
- **WHEN** implementation inventory finds a caller that reads or writes an obsolete execution-mode property
- **THEN** that caller SHALL be migrated to the stage-orchestration authority or removed
- **AND** the obsolete property SHALL not remain as a hidden compatibility switch

#### Scenario: Removal is verified
- **WHEN** implementation verification searches storage serializers, materializers, commands, lifecycle services, HTTP handlers, realtime projections, frontend state, and tests
- **THEN** no reachable marked-project path SHALL depend on the removed execution-mode authorities

