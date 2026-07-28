## MODIFIED Requirements

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

## ADDED Requirements

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
