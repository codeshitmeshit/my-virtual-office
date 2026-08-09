## ADDED Requirements

### Requirement: Canonical project materialization
Every future manual, Agent-authored, template-instantiated, and recurring project creation path SHALL materialize its persisted Project from one canonical base contract before applying creation-source-specific metadata.

The canonical contract SHALL provide the same defaults for status, priority, timestamps, archive maintenance, high-priority meeting approval, Project Execution state and stop reason, scheduling pause state, execution dirty confirmations, columns, tasks, activity container, workspace fields, and template state whenever those values are not explicitly supplied by an applicable confirmed intent.

#### Scenario: Equivalent projects are created through different entry points
- **WHEN** manual, Agent-authored, and template creation receive semantically equivalent project configuration
- **THEN** their persisted canonical Project fields SHALL be equivalent
- **AND** differences SHALL be limited to explicitly confirmed configuration and source-specific overlays

#### Scenario: A project field is omitted
- **WHEN** a creation path omits a field owned by the canonical Project contract
- **THEN** the field SHALL receive the canonical default
- **AND** the creation path SHALL NOT substitute an independently maintained default

### Requirement: Canonical task materialization
Every initial or separately created Task SHALL be materialized from one canonical Task contract that supplies execution, attempt, evidence, blocking, error, source, comment, attachment, meeting, checklist, assignment-branch, timestamp, completion, column, and order fields.

#### Scenario: Equivalent tasks are created through different entry points
- **WHEN** manual task creation, Agent-authored project creation, and template instantiation receive semantically equivalent task configuration
- **THEN** their persisted canonical Task fields SHALL be equivalent
- **AND** omitted collection and state fields SHALL use the same empty or initial values

#### Scenario: Template or draft omits optional task state
- **WHEN** a task blueprint or confirmed Agent proposal omits evidence, comments, attachments, meeting data, source, blocked reason, last error, attempts, or assignment branch
- **THEN** the materialized Task SHALL contain the canonical defaults for those fields

### Requirement: Canonical columns and acceptance checklists
Project creation SHALL produce a usable canonical board and Task acceptance checklist without relying on source-specific repair after materialization.

#### Scenario: No custom columns are confirmed
- **WHEN** a project creation request supplies no meaningful custom column configuration
- **THEN** the project SHALL contain the canonical Backlog, In Progress, Review, and Done columns in that order
- **AND** each Task without an explicit valid column SHALL be assigned to Backlog

#### Scenario: Acceptance criteria are confirmed for an Agent-authored task
- **WHEN** the confirmed natural-language proposal contains deliverable acceptance criteria for a Task
- **THEN** those criteria SHALL materialize as that Task's initial checklist
- **AND** meeting actions, discussion points, and risks SHALL NOT be treated as acceptance criteria unless the user explicitly confirms them as such

#### Scenario: An explicit checklist is supplied
- **WHEN** a supported creation path supplies an explicit valid checklist
- **THEN** the materialized Task SHALL preserve its confirmed items
- **AND** each item SHALL use the canonical checklist representation

### Requirement: Agent-created execution intent
Every future project initiated by an Agent SHALL be Project Execution-enabled by default, SHALL have a valid executable Agent and executable workspace, and SHALL remain unstarted after ordinary creation. This rule SHALL cover direct creation, Agent-initiated template instances, and recurring instances unless the user explicitly confirms tracking-only behavior.

Before creation, the user-facing proposal MUST show whether Project Execution is enabled, the executor, the reviewer or absence of one, and whether creation will start execution.

#### Scenario: Agent creates an ordinary executable project
- **WHEN** the user confirms an Agent-authored project without requesting tracking-only behavior or automatic start
- **THEN** the materialized project SHALL set `projectExecutionEnabled` to true
- **AND** it SHALL set `projectExecutionFlowActive` and legacy `workflowActive` to false
- **AND** creation SHALL NOT start Project Execution

#### Scenario: User explicitly requests a tracking-only project
- **WHEN** the user confirms that an Agent-authored project is for tracking only
- **THEN** the materialized project SHALL set `projectExecutionEnabled` to false
- **AND** creation SHALL NOT require an executable Agent or executable workspace

#### Scenario: Agent instantiates a template without execution intent
- **WHEN** an Agent initiates an instance from a template that has no explicit execution setting
- **THEN** the instance SHALL default to Project Execution-enabled and unstarted

#### Scenario: Template explicitly defines tracking-only behavior
- **WHEN** an Agent instantiates a template whose confirmed execution setting explicitly disables Project Execution
- **THEN** the instance SHALL remain tracking-only
- **AND** the Agent initiation default SHALL NOT override the explicit template setting

### Requirement: Execution prerequisites fail closed
Execution-capable Agent creation MUST validate its executable Agent and workspace prerequisites before committing the project, and MUST NOT silently materialize a legacy or tracking-only project when those prerequisites fail.

#### Scenario: Executor is unavailable
- **WHEN** an execution-capable Agent creation references no valid executable Agent or references an Agent that is no longer assignable
- **THEN** creation SHALL fail without a partial project
- **AND** the user SHALL receive a correction requirement rather than a successfully downgraded project

#### Scenario: Workspace preparation fails
- **WHEN** the executable workspace cannot be prepared or validated for an execution-capable Agent creation
- **THEN** creation SHALL fail without a partial project
- **AND** any newly prepared but uncommitted managed workspace SHALL be eligible for cleanup under the existing creation guarantees

### Requirement: Explicit project and recurrence execution authorization
An ordinary Agent-created project SHALL begin continuous project execution only after the user explicitly requests execution. Recurring authoring MUST separately confirm whether each occurrence only creates an instance or also starts that instance automatically.

#### Scenario: User starts an existing Agent-created project
- **WHEN** the user explicitly requests execution of an execution-capable Agent-created project
- **THEN** the system SHALL start project-level execution under the existing execution policy
- **AND** subsequent tasks SHALL progress continuously until an existing review, acceptance, blocker, cancellation, failure, or completion gate stops the flow

#### Scenario: Recurrence is confirmed as create-only
- **WHEN** the user confirms a recurrence that only creates project instances
- **THEN** each occurrence SHALL materialize one execution-capable project instance
- **AND** the instance SHALL remain unstarted until the user explicitly requests execution

#### Scenario: Recurrence is confirmed for automatic execution
- **WHEN** the user explicitly confirms that each recurring occurrence shall be created and automatically executed
- **THEN** each successfully materialized occurrence SHALL start Project Execution under its confirmed execution policy
- **AND** creation or execution retries SHALL preserve the existing occurrence and execution idempotency guarantees

### Requirement: Canonical workspace projection
All execution-capable creation paths SHALL persist workspace path, kind, status, manager, and creation time with the same field meanings. A creation source SHALL NOT reinterpret workspace ownership merely to identify itself as the authoring source.

#### Scenario: System prepares a managed workspace
- **WHEN** a creation path receives a workspace prepared and managed by the system
- **THEN** the persisted workspace fields SHALL identify system management using the canonical workspace ownership semantics
- **AND** authoring provenance SHALL be recorded separately from workspace ownership

#### Scenario: User supplies an existing workspace
- **WHEN** a supported creation path uses a valid user-managed workspace
- **THEN** the persisted workspace fields SHALL retain user-managed ownership semantics
- **AND** the project SHALL remain compatible with existing workspace safety checks

### Requirement: Source overlays and compatibility
Manual, Agent-authored, template, and recurring creation SHALL retain their existing authorization, persistence transaction, idempotency, grant, source, template/version, recurrence, and audit semantics as explicit overlays around canonical materialization.

Projects created before this change MUST remain readable and MUST NOT be automatically migrated, enabled, or started by this change.

#### Scenario: Manual project is created
- **WHEN** the browser management surface creates a project
- **THEN** it SHALL retain the manual `project_created` activity and existing public API behavior
- **AND** its explicit Project Execution selection SHALL be preserved

#### Scenario: Agent project is created
- **WHEN** confirmed Agent direct creation succeeds
- **THEN** it SHALL retain authoring source, confirmation, grant, audit, and idempotency metadata
- **AND** those overlays SHALL NOT replace or omit canonical Project or Task fields

#### Scenario: Template instance is created
- **WHEN** a supported path instantiates a template version
- **THEN** it SHALL retain template identity, version, and instantiation provenance
- **AND** its Project and Tasks SHALL still conform to the canonical materialization contracts

#### Scenario: Existing project is loaded after deployment
- **WHEN** the system loads a project created before this change
- **THEN** its stored execution setting and behavior SHALL remain unchanged
- **AND** the system SHALL NOT automatically rewrite or start it
