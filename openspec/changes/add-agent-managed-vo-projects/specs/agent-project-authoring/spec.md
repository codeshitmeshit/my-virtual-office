## ADDED Requirements

### Requirement: Explicit project-authoring invocation
The VO project-authoring skill SHALL create a project draft only after the user explicitly requests project creation, and SHALL NOT infer or proactively start project creation from an unrelated complex request.

#### Scenario: User explicitly requests a project
- **WHEN** a user asks the Agent to create a VO project
- **THEN** the skill SHALL collect or derive a complete project draft
- **AND** the skill SHALL submit the draft for user review without creating a project

#### Scenario: User gives a complex goal without requesting a project
- **WHEN** a user describes multi-step work but does not request project creation
- **THEN** the skill SHALL NOT create or submit a VO project draft

### Requirement: Complete pending project draft
An Agent-submitted project draft MUST contain the project identity and type, all initial tasks, one responsible actor and one executor actor for every task, reviewer recommendations, maintenance mode, and any template or recurrence configuration required for confirmation.

#### Scenario: Complete draft is submitted
- **WHEN** a registered VO Agent submits a syntactically and semantically valid complete draft with an idempotency key
- **THEN** the backend SHALL persist one pending draft request
- **AND** no project, task, template, recurrence, or workspace SHALL be created before confirmation

#### Scenario: Required role is unresolved
- **WHEN** any task lacks a valid responsible actor or executor actor
- **THEN** the backend SHALL reject the draft as incomplete
- **AND** the skill SHALL ask the user to confirm an Agent-recommended candidate before resubmission

#### Scenario: Draft submission is retried
- **WHEN** the same requesting Agent retries the same draft idempotency key
- **THEN** the backend SHALL return the original draft request
- **AND** it SHALL NOT create a duplicate pending request

### Requirement: Trusted user review and atomic materialization
The system MUST require a management-authenticated user action to edit, confirm, or reject a pending project draft, and confirmation MUST atomically materialize the approved project and all initial tasks.

#### Scenario: User confirms an unchanged draft
- **WHEN** an authorized user confirms a valid pending draft
- **THEN** the backend SHALL create exactly one project containing all approved tasks and role assignments
- **AND** the draft SHALL record the confirming user, confirmation time, immutable approved snapshot, and created project identifier

#### Scenario: User edits before confirmation
- **WHEN** an authorized user edits project, task, role, reviewer, maintenance, template, or recurrence fields and then confirms
- **THEN** the edited snapshot SHALL be validated and become the materialized source of truth
- **AND** the original Agent proposal SHALL remain available in audit history

#### Scenario: Materialization fails
- **WHEN** workspace creation, actor validation, template creation, recurrence registration, or project persistence fails during confirmation
- **THEN** the system SHALL return a stable failure result
- **AND** it SHALL NOT leave a partially created project or task set
- **AND** the pending draft SHALL remain recoverable for correction or retry

#### Scenario: Confirmation is retried
- **WHEN** confirmation for an already materialized draft is repeated
- **THEN** the backend SHALL return the same project identifier
- **AND** it SHALL NOT create a duplicate project or recurrence

#### Scenario: User rejects a draft
- **WHEN** an authorized user rejects a pending draft with a reason
- **THEN** the draft SHALL become rejected and remain auditable
- **AND** no project SHALL be created from it

### Requirement: Responsible and executor actor semantics
Every authored task SHALL have exactly one responsible actor accountable for the result and exactly one executor actor responsible for performing the work; the same supported actor MAY hold both roles.

#### Scenario: One actor holds both roles
- **WHEN** a confirmed task names the same valid actor as responsible actor and executor actor
- **THEN** the task SHALL be created with both role relationships preserved

#### Scenario: Automated Agent execution is selected
- **WHEN** the executor actor is a registered executable Agent
- **THEN** the backend SHALL project that actor into the existing Project Execution executor fields
- **AND** existing execution, review, and acceptance gates SHALL remain applicable

#### Scenario: Human execution is selected
- **WHEN** the executor actor is the supported VO user actor
- **THEN** the task SHALL remain trackable as human-executed work
- **AND** automated Project Execution SHALL reject starting that task until a valid executable Agent is assigned

#### Scenario: Actor is invalid at confirmation time
- **WHEN** a referenced Agent no longer exists or is excluded from ordinary project assignment
- **THEN** confirmation SHALL fail with the invalid role and candidate identified
- **AND** no partial project SHALL be created

### Requirement: Reviewer is optional and user-confirmed
Authored tasks SHALL have no reviewer by default. For a task classified as high-risk, cross-team, or critical-delivery, the Agent SHALL recommend a reviewer candidate and explain the trigger, but the reviewer SHALL be assigned only from the user-confirmed snapshot.

#### Scenario: Ordinary task has no reviewer
- **WHEN** a task does not trigger a reviewer recommendation and the user does not add one
- **THEN** the task SHALL be created without a reviewer

#### Scenario: Reviewer rule is triggered
- **WHEN** the Agent classifies a task as high-risk, cross-team, or critical-delivery
- **THEN** the draft SHALL contain the trigger, rationale, and recommended registered reviewer
- **AND** the backend SHALL NOT treat the recommendation as an assignment before user confirmation

#### Scenario: User removes a recommendation
- **WHEN** the user confirms the draft after removing a recommended reviewer
- **THEN** the task SHALL remain reviewerless
- **AND** any later execution attempt SHALL continue to use the existing reviewer-skip confirmation gate

### Requirement: Controlled Agent maintenance
Each authored project SHALL persist either `strict_confirmation` or `autonomous` maintenance mode, and Agent-originated maintenance MUST remain within the mode's approved mutation boundary.

#### Scenario: Strict project receives a structural change
- **WHEN** an Agent requests any task creation or deletion, role or reviewer change, recurrence change, project archival, or other project-structure mutation in `strict_confirmation` mode
- **THEN** the backend SHALL create a pending maintenance request
- **AND** the mutation SHALL require management-authenticated user confirmation

#### Scenario: Autonomous project receives an allowed routine update
- **WHEN** an assigned Agent updates task state, description, checklist, evidence, or due date in `autonomous` mode
- **THEN** the backend MAY apply the validated update without a new user confirmation
- **AND** it SHALL record the actor, changed fields, timestamp, and source

#### Scenario: Autonomous project receives a protected update
- **WHEN** an Agent requests task deletion, role or reviewer reassignment, recurrence changes, project archival, workspace changes, or maintenance-mode changes in `autonomous` mode
- **THEN** the backend SHALL require a pending maintenance request and user confirmation

#### Scenario: Unassigned Agent requests maintenance
- **WHEN** an Agent that is not an approved project or task actor requests an Agent-originated mutation
- **THEN** the backend SHALL reject the request
- **AND** no project state SHALL change

### Requirement: Reusable versioned project templates
The system SHALL allow a confirmed project draft to create or reference a reusable project template whose versioned snapshot contains the confirmed task structure, role rules, reviewer policy, maintenance mode, and execution settings needed to instantiate future projects.

#### Scenario: User manually creates from a template
- **WHEN** the user or an authorized Agent workflow requests manual instantiation of a valid template version
- **THEN** the system SHALL create a new independent project from that immutable version
- **AND** it SHALL validate all referenced actors before committing the instance

#### Scenario: Template is edited
- **WHEN** a template receives a new confirmed version
- **THEN** only future instances SHALL use the new version
- **AND** existing project instances and their approved snapshots SHALL remain unchanged

### Requirement: Independent recurring project instances
A confirmed recurring project definition SHALL create a new independently traceable project instance for each due occurrence rather than reopening tasks or starting execution in an existing project.

#### Scenario: Recurrence becomes due
- **WHEN** a confirmed recurrence reaches a due occurrence
- **THEN** the backend SHALL instantiate exactly one new project from the recurrence's selected template version
- **AND** the project SHALL record recurrence identifier, occurrence identifier, template identifier, and template version

#### Scenario: Same occurrence is delivered repeatedly
- **WHEN** scheduler callbacks or retries repeat the same recurrence occurrence
- **THEN** the backend SHALL return or retain the original project instance
- **AND** it SHALL NOT create another project for that occurrence

#### Scenario: Future actor is no longer valid
- **WHEN** a due recurrence references an actor that is no longer assignable
- **THEN** the occurrence SHALL fail without a partial project
- **AND** the recurrence SHALL record an intervention alert and retry-safe failure state

#### Scenario: Recurrence is paused
- **WHEN** an authorized user pauses a recurrence
- **THEN** future due callbacks SHALL not create project instances until the recurrence is resumed

### Requirement: Agent-safe API and audit boundary
Agent project-authoring APIs MUST NOT require or expose the VO management token. They SHALL limit unauthenticated or Agent-originated calls to draft submission, request status, and maintenance actions permitted by the confirmed project policy, while user confirm/edit/reject and protected mutations remain management-authenticated.

#### Scenario: Agent submits a draft without management credentials
- **WHEN** a local registered Agent submits a valid project draft through the Agent authoring endpoint
- **THEN** the endpoint SHALL accept the non-materializing request without disclosing a management credential

#### Scenario: Agent calls a protected confirmation endpoint
- **WHEN** a caller without a valid management token attempts to confirm, edit, reject, or directly materialize a draft
- **THEN** the backend SHALL return the existing management authorization failure
- **AND** no state SHALL change

#### Scenario: Request or mutation is observed
- **WHEN** a draft, confirmation, rejection, materialization, maintenance change, or recurrence occurrence is processed
- **THEN** the system SHALL retain a sanitized audit record containing request identity, actor, action, source, timestamp, result, and linked object identifiers
- **AND** secrets or management credentials SHALL NOT be persisted in that record

### Requirement: Existing project behavior remains compatible
The change MUST preserve existing browser project CRUD, stored project readability, Project Execution, review, acceptance, template, and scheduled-execution behavior for projects not using the new authoring capability.

#### Scenario: Legacy project is loaded
- **WHEN** a project created before this change lacks actor-reference, maintenance-mode, or authoring-source fields
- **THEN** the backend SHALL apply backward-compatible read defaults
- **AND** existing project APIs and execution behavior SHALL remain valid

#### Scenario: Existing scheduled execution runs
- **WHEN** an existing project workflow or project-task cron binding becomes due
- **THEN** it SHALL continue to run or skip under its current rules
- **AND** it SHALL NOT be converted into recurring project instantiation

### Requirement: Project-authoring skill routing and safety
The VO skills index SHALL route project creation, draft confirmation status, template instantiation, recurrence authoring, and controlled maintenance to the new project-authoring skill, while execution, review, acceptance, cancellation, and artifact reading remain routed to `vo-project-workflow`.

#### Scenario: Agent needs to create a project
- **WHEN** the Agent follows the current VO skills index for an explicit project-creation request
- **THEN** it SHALL select the project-authoring skill
- **AND** it SHALL read current Agent and project data before recommending role candidates

#### Scenario: Agent needs to execute an existing task
- **WHEN** the Agent needs to start or advance Project Execution for an existing task
- **THEN** it SHALL continue to use `vo-project-workflow`
- **AND** the project-authoring skill SHALL NOT bypass execution safety gates
