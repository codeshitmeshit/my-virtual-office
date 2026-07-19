## ADDED Requirements

### Requirement: First-level Human Resources module
The main VO application SHALL provide a first-level Human Resources entry modeled on Archive Room's independent navigation pattern rather than limiting Human Resources to Agent detail or HR chat.

#### Scenario: Human opens Human Resources
- **WHEN** the user activates the main Human Resources entry
- **THEN** the application SHALL open the Human Resources module with HR status and cross-Agent overview before requiring selection of one Agent

### Requirement: Human Resources overview
The overview SHALL present HR lifecycle state, Agent totals by availability, today's submitted, missing, pending-assessment, assessed, and failed counts, recent HR activity, and a roster prioritized so unresolved or abnormal states remain discoverable.

#### Scenario: Daily collection is in progress
- **WHEN** the overview loads during an open collection window
- **THEN** it SHALL distinguish waiting, submitted, skipped, and failed Agents and SHALL NOT present the cycle as complete

#### Scenario: No Agent records exist
- **WHEN** HR has not yet established a directory
- **THEN** the module SHALL explain whether initialization is pending, paused, or failed and SHALL NOT display invented roster data

### Requirement: Agent Human Resources detail
The human-facing Agent detail SHALL show name, introduction, AI ID, availability, introduction provenance, report history, assessment history, workload history, blockers, improvement feedback, current workflow state, HR contact state, and access history authorized for the human.

#### Scenario: Human selects an Agent
- **WHEN** an Agent record is opened
- **THEN** current information and historical reports and assessments SHALL be clearly separated by date and status
- **AND** raw Agent claims SHALL be distinguishable from HR normalization and HR judgment

### Requirement: HR lifecycle controls and activity
The module SHALL expose HR status, auto-created state, profile or provider error, pause/resume controls, and recent lifecycle and workflow activity to the authenticated human.

#### Scenario: Human pauses HR
- **WHEN** the user confirms pause
- **THEN** the module SHALL show that new introductions, daily collection, and assessment are paused while existing data remains browsable

### Requirement: Degraded and partial-failure experience
The Human Resources module SHALL remain readable when HR, OpenClaw, scheduling, one Agent, normalization, or assessment fails and SHALL identify the affected scope and retry or recovery state without masking valid records.

#### Scenario: HR creation fails
- **WHEN** the HR lifecycle is in error
- **THEN** the module SHALL show the understandable failure state and retain access to any existing Human Resources data

#### Scenario: One Agent workflow fails
- **WHEN** introduction, report collection, or assessment fails for one Agent
- **THEN** the module SHALL show that Agent's failed state without presenting other Agents as failed

### Requirement: Disclosure-safe Agent experience
Agent-facing Human Resources queries SHALL use the governed public and self views rather than rendering the human management surface or relying on client-side hiding of restricted data.

#### Scenario: Ordinary Agent queries a colleague
- **WHEN** an Agent asks for another Agent's work information
- **THEN** only the server-authorized public view SHALL be returned and the access SHALL be auditable under the governance specification

### Requirement: Localized and accessible workflow states
Human Resources navigation, statuses, actions, errors, report states, assessment states, workload labels, and access-history labels SHALL be available through the application's supported localization and interaction patterns.

#### Scenario: User changes application language
- **WHEN** Human Resources is rendered in a supported locale
- **THEN** visible workflow text SHALL use that locale without changing persisted semantic state values
