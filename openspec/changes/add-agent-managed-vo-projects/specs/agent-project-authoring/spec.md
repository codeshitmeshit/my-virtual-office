## ADDED Requirements

### Requirement: Explicit project-authoring invocation
The VO project-authoring skill SHALL prepare a natural-language project proposal only after the user explicitly requests project creation, SHALL wait for the user to confirm that proposal in the conversation, and SHALL NOT infer or proactively create a project from an unrelated complex request.

#### Scenario: User explicitly requests a project
- **WHEN** a user asks the Agent to create a VO project
- **THEN** the skill SHALL collect or derive a complete natural-language project proposal
- **AND** the proposal SHALL describe the project type, tasks, responsible actors, executor actors, optional reviewer decisions, maintenance mode, and template or recurrence settings
- **AND** the skill SHALL wait for explicit user confirmation before calling the direct-create API

#### Scenario: User gives a complex goal without requesting a project
- **WHEN** a user describes multi-step work but does not request project creation
- **THEN** the skill SHALL NOT propose or create a VO project

### Requirement: Complete direct project creation
After conversational confirmation, an Agent direct-create request MUST contain the project identity and type, all initial tasks, one responsible actor and one executor actor for every task, the user-confirmed reviewer decisions, maintenance mode, and any template or recurrence configuration required to create the real project atomically.

#### Scenario: Confirmed proposal is submitted
- **WHEN** a registered VO Agent submits a syntactically and semantically valid complete create request with an idempotency key after explicit conversational confirmation
- **THEN** the backend SHALL atomically create one real project containing all initial tasks and role assignments
- **AND** it SHALL return the created project identifier and a scoped project grant
- **AND** it SHALL NOT persist a pending draft request
- **AND** it SHALL NOT start Project Execution

#### Scenario: Required role is unresolved
- **WHEN** any task lacks a valid responsible actor or executor actor
- **THEN** the backend SHALL reject the create request without partial project state
- **AND** the skill SHALL present the corrected candidate in natural language and obtain confirmation before retrying a semantically changed request

#### Scenario: Direct creation is retried
- **WHEN** the same requesting Agent retries the same create idempotency key
- **THEN** the backend SHALL return the original created project and grant status
- **AND** it SHALL NOT create a duplicate project, template, recurrence, task set, or workspace

### Requirement: Conversational confirmation and atomic creation
The skill MUST obtain explicit user confirmation of the natural-language proposal before calling the Agent direct-create API, and the backend MUST atomically create the confirmed project and all initial tasks without a separate persisted draft or management confirmation state.

#### Scenario: User confirms the proposal
- **WHEN** the user explicitly confirms the natural-language proposal
- **THEN** the Agent SHALL translate that confirmed proposal into one structured direct-create request
- **AND** the created project SHALL record the requesting Agent, confirmation assertion, source summary digest, creation time, and complete created configuration

#### Scenario: User changes the proposal before confirmation
- **WHEN** the user changes project, task, role, reviewer, maintenance, template, or recurrence intent before confirming
- **THEN** the Agent SHALL present the revised natural-language proposal
- **AND** the revised proposal SHALL require explicit confirmation before creation

#### Scenario: Direct creation fails
- **WHEN** workspace creation, actor validation, template creation, recurrence registration, or project persistence fails during direct creation
- **THEN** the system SHALL return a stable failure result
- **AND** it SHALL NOT leave a partially created project or task set
- **AND** a transport retry with the same idempotency key SHALL be safe

#### Scenario: Creation is retried
- **WHEN** direct creation for an already materialized confirmation is repeated
- **THEN** the backend SHALL return the same project identifier
- **AND** it SHALL NOT create a duplicate project or recurrence

#### Scenario: User does not confirm
- **WHEN** the user rejects, changes, or does not confirm the natural-language proposal
- **THEN** the Agent SHALL NOT call the direct-create API
- **AND** the backend SHALL store no draft or project for that proposal

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

#### Scenario: Actor is invalid at creation time
- **WHEN** a referenced Agent no longer exists or is excluded from ordinary project assignment
- **THEN** creation SHALL fail with the invalid role and candidate identified
- **AND** no partial project SHALL be created

### Requirement: Reviewer is optional and user-confirmed
Authored tasks SHALL have no reviewer by default. For a task classified as high-risk, cross-team, or critical-delivery, the Agent SHALL recommend a reviewer candidate and explain the trigger in the natural-language proposal, but the reviewer SHALL be assigned only when the user explicitly confirms that assignment.

#### Scenario: Ordinary task has no reviewer
- **WHEN** a task does not trigger a reviewer recommendation and the user does not add one
- **THEN** the task SHALL be created without a reviewer

#### Scenario: Reviewer rule is triggered
- **WHEN** the Agent classifies a task as high-risk, cross-team, or critical-delivery
- **THEN** the natural-language proposal SHALL contain the trigger, rationale, and recommended registered reviewer
- **AND** the direct-create request SHALL omit `reviewerActor` unless the user confirms the assignment

#### Scenario: User removes a recommendation
- **WHEN** the user confirms the proposal without the recommended reviewer
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
The system SHALL allow a conversation-confirmed direct-create request to create or reference a reusable project template whose versioned snapshot contains the confirmed task structure, role rules, reviewer policy, maintenance mode, and execution settings needed to instantiate future projects.

#### Scenario: User manually creates from a template
- **WHEN** the user or an authorized Agent workflow requests manual instantiation of a valid template version
- **THEN** the system SHALL create a new independent project from that immutable version
- **AND** it SHALL validate all referenced actors before committing the instance

#### Scenario: Template is edited
- **WHEN** a template receives a new confirmed version
- **THEN** only future instances SHALL use the new version
- **AND** existing project instances and their approved snapshots SHALL remain unchanged

### Requirement: Independent recurring project instances
A conversation-confirmed recurring project creation SHALL establish a definition that creates a new independently traceable project instance for each due occurrence rather than reopening tasks or starting execution in an existing project.

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
Agent project-authoring APIs MUST NOT require or expose the VO management token. They SHALL limit Agent-originated calls to idempotent direct project creation and maintenance actions permitted by the created project policy, while protected maintenance mutations remain management-authenticated.

#### Scenario: Agent creates without management credentials
- **WHEN** a local registered Agent submits a valid direct-create request through the Agent authoring endpoint after conversational confirmation
- **THEN** the endpoint SHALL atomically create the project without disclosing a management credential
- **AND** it SHALL return the project grant secret only on first creation

#### Scenario: Agent calls a protected maintenance endpoint
- **WHEN** a caller without a valid management token attempts to confirm protected maintenance, rotate or revoke another grant, or pause or resume recurrence
- **THEN** the backend SHALL return the existing management authorization failure
- **AND** no state SHALL change

#### Scenario: Request or mutation is observed
- **WHEN** a direct creation, maintenance change, or recurrence occurrence is processed
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
The VO skills index SHALL route natural-language project proposal confirmation, direct creation, template instantiation, recurrence authoring, and controlled maintenance to the new project-authoring skill, while execution, review, acceptance, cancellation, and artifact reading remain routed to `vo-project-workflow`.

#### Scenario: Agent needs to create a project
- **WHEN** the Agent follows the current VO skills index for an explicit project-creation request
- **THEN** it SHALL select the project-authoring skill
- **AND** it SHALL read current Agent and project data before recommending role candidates

#### Scenario: Agent needs to execute an existing task
- **WHEN** the Agent needs to start or advance Project Execution for an existing task
- **THEN** it SHALL continue to use `vo-project-workflow`
- **AND** the project-authoring skill SHALL NOT bypass execution safety gates
