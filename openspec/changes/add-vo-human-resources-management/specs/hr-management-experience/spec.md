## ADDED Requirements

### Requirement: First-level Human Resources module
The main VO application SHALL provide a first-level Human Resources entry modeled on Archive Room's independent navigation pattern rather than limiting Human Resources to Agent detail or HR chat.

#### Scenario: Human opens Human Resources
- **WHEN** the user activates the main Human Resources entry
- **THEN** the application SHALL open the Human Resources module with HR status and cross-Agent overview before requiring selection of one Agent

### Requirement: Human Resources overview
The overview SHALL present HR lifecycle state, Agent totals by availability, today's submitted, missing, pending-assessment, assessed, and failed counts, recent HR activity, the next configured daily-report collection time in the VO timezone, and a roster prioritized so unresolved or abnormal states remain discoverable.

#### Scenario: Daily collection is in progress
- **WHEN** the overview loads during an open collection window
- **THEN** it SHALL distinguish waiting, submitted, skipped, and failed Agents and SHALL NOT present the cycle as complete

#### Scenario: No Agent records exist
- **WHEN** HR has not yet established a directory
- **THEN** the module SHALL explain whether initialization is pending, paused, or failed and SHALL NOT display invented roster data

#### Scenario: Human inspects the next daily-report collection
- **WHEN** the Human Resources overview loads
- **THEN** it SHALL show the next collection wall-clock time and configured VO timezone
- **AND** it SHALL distinguish scheduled collection, an occurrence already due for catch-up, and a configured time whose automatic scheduler is disabled

#### Scenario: Human configures daily collection on the page
- **WHEN** the human edits the daily collection time or automatic enablement in Human Resources
- **THEN** the module SHALL validate and save the schedule through a management API
- **AND** the refreshed overview SHALL show the persisted time and next occurrence
- **AND** a new repository SHALL initially show an enabled `18:00` schedule

### Requirement: Agent Human Resources detail
The human-facing Agent detail SHALL show name, introduction, AI ID, availability, introduction provenance, report history, assessment history, workload history, blockers, improvement feedback, current workflow state, HR contact state, and access history authorized for the human.

#### Scenario: Human selects an Agent
- **WHEN** an Agent record is opened
- **THEN** current information and historical reports and assessments SHALL be clearly separated by date and status
- **AND** raw Agent claims SHALL be distinguishable from HR normalization and HR judgment

### Requirement: HR lifecycle controls and activity
The module SHALL expose HR status, auto-created state, profile or provider error, pause/resume controls, and recent lifecycle and workflow activity to the authenticated human.

The overview SHALL show one authoritative HR lifecycle status indicator rather than duplicating the same status in the modal header and overview card. It SHALL also provide an authenticated manual Agent-team synchronization action that force-refreshes roster discovery and reconciles newly discovered, changed, reactivated, and missing Agents into the HR directory before refreshing the view, plus a separate `补充信息` action for asynchronously filling missing introductions among currently available Agents.

#### Scenario: Human pauses HR
- **WHEN** the user confirms pause
- **THEN** the module SHALL show that new introductions, daily collection, and assessment are paused while existing data remains browsable

#### Scenario: Human actively synchronizes the Agent team
- **WHEN** the user confirms active synchronization
- **THEN** HR SHALL force-refresh the VO roster, reconcile Agent records for every registered Provider, and refresh the displayed Agent team
- **AND** one malformed or unsupported Agent SHALL NOT prevent valid newly discovered Agents from appearing

#### Scenario: Human completes missing Agent information
- **WHEN** the user confirms `补充信息`
- **THEN** the command SHALL be accepted without waiting for all Agent conversations
- **AND** the UI SHALL preserve existing readable data while HR asks and summarizes only missing introductions in the background
- **AND** a second completion command SHALL NOT start while one is already running

### Requirement: Degraded and partial-failure experience
The Human Resources module SHALL remain readable when HR, OpenClaw, scheduling, one Agent, normalization, or assessment fails and SHALL identify the affected scope and retry or recovery state without masking valid records.

#### Scenario: HR creation fails
- **WHEN** the HR lifecycle is in error
- **THEN** the module SHALL show the understandable failure state and retain access to any existing Human Resources data

#### Scenario: One Agent workflow fails
- **WHEN** introduction, report collection, or assessment fails for one Agent
- **THEN** the module SHALL show that Agent's failed state without presenting other Agents as failed

### Requirement: Observable background command execution
Every asynchronous Human Resources management command SHALL expose a durable command identity and distinguish accepted, processing, complete, and failed states through the management overview. The UI SHALL continue refreshing while a command is active and SHALL present its current action and state instead of treating queue acceptance as completion.

#### Scenario: Accepted command starts background work
- **WHEN** the human submits Agent-team synchronization, information completion, manual daily synchronization, or a daily-cycle command
- **THEN** the command endpoint SHALL return without waiting for provider work and include a stable command ID
- **AND** the overview SHALL expose that command as accepted or processing until it reaches a terminal state

#### Scenario: Human refreshes while work is running
- **WHEN** the Human Resources module is reopened or refreshed during an active command
- **THEN** the UI SHALL recover the active state from the server, show which action is in progress, and continue polling until completion or failure

#### Scenario: Background work terminates
- **WHEN** an active command completes, partially fails, or fails
- **THEN** its active marker SHALL be removed and the same durable activity SHALL show the terminal result without leaving a stale processing state

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
