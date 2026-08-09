## ADDED Requirements

### Requirement: Project tasks have execution batches
Every project task SHALL have a positive execution-batch number that represents the task's position in the project's batch flow. Multiple tasks in the same project MAY share the same execution-batch number, and tasks with the same number belong to the same concurrent execution batch.

#### Scenario: Project is created with tasks
- **WHEN** a project is created through manual UI, Agent authoring, template instantiation, or recurrence materialization
- **THEN** every created task SHALL have an execution-batch number
- **AND** tasks without an explicitly confirmed batch SHALL receive a compatible positive default based on their confirmed task order

#### Scenario: Several tasks share a batch
- **WHEN** two or more tasks in one project have the same execution-batch number
- **THEN** the system SHALL treat those tasks as peers in one concurrent batch
- **AND** it SHALL NOT reject the project or task update solely because the batch number is shared

#### Scenario: Legacy task lacks a persisted batch
- **WHEN** an existing project task lacks a persisted execution-batch value
- **THEN** the system SHALL compute a positive effective batch from legacy task ordering for display and execution compatibility
- **AND** the project SHALL remain readable without requiring a destructive migration

### Requirement: Batch editor covers the full project
The project execution-batch editor SHALL cover all tasks in the project, not only Backlog tasks, and SHALL make each task's current project column or state visible while editing.

#### Scenario: User opens the batch editor
- **WHEN** a user opens the project batch editor
- **THEN** the editor SHALL list every task in the project exactly once
- **AND** each row SHALL show the task title, current batch number, and current column or state

#### Scenario: User edits batch numbers
- **WHEN** a user changes batch numbers in the editor and saves
- **THEN** positive whole-number batch values SHALL be accepted
- **AND** duplicate batch values SHALL be accepted as valid concurrent batch assignments
- **AND** invalid non-positive or non-numeric values SHALL be rejected before the project state changes

### Requirement: Batch editing protects execution history
The system SHALL prevent batch edits that would rewrite already-started execution history or insert unstarted tasks into already-started or completed batches.

#### Scenario: Started task is edited
- **WHEN** a task is in an active, reviewing, blocked, awaiting-acceptance, completed, or otherwise historical execution state
- **THEN** the user SHALL NOT be allowed to move that task to another execution batch
- **AND** the task's existing batch SHALL remain unchanged

#### Scenario: Unstarted task is moved
- **WHEN** an unstarted task is assigned to another batch
- **THEN** the new batch SHALL be a future batch that has not started and has not completed
- **AND** the system SHALL reject attempts to move the task into a started or completed batch

### Requirement: Project Execution starts and advances by batch
Project-level execution SHALL select the lowest unfinished execution batch and start all eligible tasks in that batch together. It SHALL NOT advance to a later batch until every task in the current batch is complete.

#### Scenario: Project execution starts
- **WHEN** a user starts Project Execution for a project with multiple unfinished batches
- **THEN** the system SHALL select the lowest unfinished batch
- **AND** it SHALL start every eligible task in that batch without starting tasks from later batches

#### Scenario: Current batch completes
- **WHEN** every task in the active batch has passed required execution, review, and acceptance gates
- **THEN** the project flow MAY advance to the next lowest unfinished batch
- **AND** tasks in the completed batch SHALL remain historical and SHALL NOT be restarted unless an explicit supported restart action is used

#### Scenario: Current batch has an ineligible task
- **WHEN** any task in the selected batch cannot start because of missing executor, workspace failure, reviewer gate, or another start prerequisite
- **THEN** the project SHALL NOT advance to a later batch
- **AND** the batch SHALL surface a clear correction requirement to the user

#### Scenario: Current batch blocks or fails
- **WHEN** any task in the active batch enters a blocked or failed state
- **THEN** the batch SHALL be considered blocked as a whole
- **AND** Project Execution SHALL wait for user intervention before later batches can start

### Requirement: Agent and template authoring preserves batches
Agent project authoring, project templates, and recurring project instances SHALL preserve confirmed execution-batch assignments for every task.

#### Scenario: Agent proposes a project
- **WHEN** an Agent proposes a project with multiple tasks
- **THEN** the natural-language proposal SHALL show the execution batch for each task
- **AND** the Agent SHALL obtain user confirmation before creating or updating those batch assignments

#### Scenario: Template is saved and instantiated
- **WHEN** a project template is saved or instantiated
- **THEN** the template snapshot and new project instance SHALL preserve each task's execution-batch assignment

#### Scenario: Recurring project occurrence is created
- **WHEN** a recurring project occurrence materializes a project from a template
- **THEN** the occurrence project SHALL contain the same confirmed execution-batch assignments as the selected template version
