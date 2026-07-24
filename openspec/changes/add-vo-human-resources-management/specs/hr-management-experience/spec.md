## ADDED Requirements

### Requirement: Unified Agent management module
The main VO application SHALL provide one `Agent 管理` surface with peer `代理配置` and `人事运营` tabs. Both tabs SHALL use one Agent roster, preserve the current Agent selection and relevant view context across tab switches, and adapt visible data and actions to the authenticated human or ordinary-Agent audience without treating client-side hiding as authorization.

#### Scenario: Human opens Agent management
- **WHEN** an authenticated human opens Agent Management
- **THEN** the application SHALL expose both configuration and Human Resources tabs
- **AND** the Human Resources tab SHALL show HR status and cross-Agent overview without requiring a second independent Human Resources modal

#### Scenario: Agent opens the shared surface
- **WHEN** an ordinary Agent opens Agent Management
- **THEN** the same navigation structure SHALL default to that Agent's own record
- **AND** restricted human-management information and Human Resources commands SHALL be absent

#### Scenario: User switches management tabs
- **WHEN** the user selects an Agent and switches between configuration and Human Resources
- **THEN** the selected stable AI ID SHALL remain current
- **AND** switching tabs SHALL NOT reset the roster, open an unrelated Agent, or discard relevant scroll and loading state

### Requirement: Audience-safe automatic Agent configuration
The shared Agent Management surface SHALL allow an ordinary Agent to modify only its own low-risk name, introduction, responsibility/specialty, and appearance fields. Those changes SHALL apply immediately, provide visible automatic-save feedback, and offer a bounded undo action. Provider, branch, workspace, assignment, and Provider-Agent binding changes SHALL remain authenticated-human-only and SHALL require an explicit impact confirmation before applying.

Responsibility/specialty values SHALL support display, filtering, and task-candidate recommendation but SHALL NOT act as a hard permission or assignment prohibition.

#### Scenario: Agent changes a low-risk field
- **WHEN** an ordinary Agent changes its own name, introduction, responsibility/specialty, or appearance
- **THEN** the change SHALL apply without a global save button
- **AND** the UI SHALL show whether automatic saving succeeded or failed
- **AND** a recent successful change SHALL be undoable within the documented undo window

#### Scenario: Human changes a high-risk binding
- **WHEN** an authenticated human changes Provider, branch, workspace, assignment, or Provider-Agent binding
- **THEN** the UI SHALL identify the Agent and affected relationship
- **AND** the change SHALL require explicit confirmation before applying

#### Scenario: Agent attempts a restricted configuration change
- **WHEN** an ordinary Agent opens its own or another Agent's configuration
- **THEN** high-risk binding controls SHALL NOT be available
- **AND** a direct restricted mutation attempt SHALL be rejected without changing configuration

#### Scenario: Responsibility does not become a hard gate
- **WHEN** an Agent's responsibility/specialty does not match a task category
- **THEN** the value MAY affect filtering or recommendation
- **AND** it SHALL NOT by itself prevent an otherwise authorized assignment

### Requirement: Compact visual configuration selectors
Categorical appearance fields SHALL render a compact current-value selector instead of permanently displaying every option. Opening a selector SHALL present a keyboard-accessible visual option grid, choosing an option SHALL update the Agent preview and automatic-save state immediately, and the selector SHALL close after selection. Color fields SHALL retain a visible swatch or palette affordance rather than becoming opaque text-only dropdowns.

#### Scenario: User opens an appearance selector
- **WHEN** the user activates a categorical appearance field such as hair, clothing, accessory, glasses, or item
- **THEN** the UI SHALL show the current value and an expanded visual option grid
- **AND** the currently selected option SHALL be distinguishable

#### Scenario: User chooses an appearance option
- **WHEN** the user chooses an allowed option from the expanded selector
- **THEN** the selector SHALL close
- **AND** the Agent preview SHALL reflect the new option
- **AND** automatic-save feedback and undo SHALL follow the same low-risk configuration behavior

### Requirement: Human Resources overview
The Human Resources tab overview SHALL present HR lifecycle state, Agent totals by availability, today's submitted, missing, pending-assessment, assessed, and failed counts, recent HR activity, the next configured daily-report collection time in the VO timezone, and a roster prioritized so unresolved or abnormal states remain discoverable.

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
The Human Resources tab SHALL expose HR status, auto-created state, profile or provider error, pause/resume controls, and recent lifecycle and workflow activity to the authenticated human.

The overview SHALL show one authoritative HR lifecycle status indicator rather than duplicating the same status in the header and overview card. It SHALL keep frequent Agent-team synchronization, information completion, and manual daily-report correction actions directly discoverable. Lower-frequency or higher-risk pause/resume, cycle close, export, and diagnostic actions SHALL be grouped under an explicit advanced area and SHALL preserve their existing confirmation requirements.

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

#### Scenario: Human opens advanced Human Resources actions
- **WHEN** the authenticated human needs pause/resume, cycle close, export, or diagnostics
- **THEN** those actions SHALL be available from an explicit advanced area rather than occupying the primary action row
- **AND** destructive or workflow-stopping actions SHALL still require confirmation and explain their affected scope

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
Agent-facing Human Resources experiences MAY reuse the Agent Management shell and navigation structure, but they SHALL load only governed public and self views. Restricted data and actions SHALL be absent from the Agent UI, and server-side disclosure and mutation enforcement SHALL remain authoritative rather than relying on client-side hiding.

#### Scenario: Ordinary Agent queries a colleague
- **WHEN** an Agent selects another Agent in the shared roster or asks for that Agent's work information
- **THEN** only the server-authorized public view SHALL be returned and the access SHALL be auditable under the governance specification

#### Scenario: Agent views its own record
- **WHEN** an ordinary Agent opens its own record
- **THEN** it SHALL receive its permitted self view, including its own applicable report and access-history information
- **AND** it SHALL NOT receive human-only assessment evidence, unrelated access history, or Human Resources commands

### Requirement: Localized and accessible workflow states
Human Resources navigation, statuses, actions, errors, report states, assessment states, workload labels, and access-history labels SHALL be available through the application's supported localization and interaction patterns.

#### Scenario: User changes application language
- **WHEN** Human Resources is rendered in a supported locale
- **THEN** visible workflow text SHALL use that locale without changing persisted semantic state values

### Requirement: Development-machine end-to-end regression gate
The change MUST NOT pass the test-result confirmation gate until an approved development machine with real OpenClaw and VO processes has produced end-to-end regression evidence for the merged Agent Management and Human Resources experience. The regression MUST begin with browser-visible user actions and traverse management authentication or governed Agent identity, real HTTP/application boundaries, asynchronous command processing, real Provider or Agent communication where applicable, durable persistence, restart or recovery behavior, and the final refreshed UI projection. Unit, static, API-only, fake-provider, and smoke tests SHALL remain supporting evidence but SHALL NOT substitute for this end-to-end gate.

#### Scenario: Human completes a real Human Resources workflow
- **WHEN** an authenticated human uses the merged Agent Management UI on the approved development machine to synchronize the Agent team, complete missing information, correct a daily report, or run the controlled daily cycle
- **THEN** the evidence SHALL trace the browser action through the accepted and processing command states to the real persisted terminal result
- **AND** the refreshed UI SHALL display the resulting directory, report, normalization, assessment, activity, or failure state without manual data fabrication

#### Scenario: Real Agent disclosure boundaries are regressed
- **WHEN** a registered ordinary Agent uses the development-machine Agent Management or governed Human Resources entry for self and cross-Agent reads
- **THEN** the end-to-end result SHALL expose only the permitted self or public projection
- **AND** restricted human data and commands SHALL remain unavailable
- **AND** successful cross-Agent disclosure and denial paths SHALL produce the specified audit or diagnostic result

#### Scenario: Restart and rollback are exercised end to end
- **WHEN** the development-machine regression restarts VO or OpenClaw during or after a controlled HR workflow and then disables the automatic schedule and HR in the approved rollback order
- **THEN** the same persisted Agent and Human Resources state SHALL recover or settle according to specification
- **AND** the UI SHALL show the recovered, paused, failed, or completed state
- **AND** Archive Room and existing VO workflows SHALL remain operational

#### Scenario: End-to-end evidence is reviewed
- **WHEN** the test-result confirmation package is prepared
- **THEN** it SHALL identify the approved machine, VO and OpenClaw versions, configuration and feature-switch sequence, browser actions, relevant command or log correlation, persisted outcomes, screenshots or recordings, failures, retries, and rollback result
- **AND** any uncovered end-to-end scenario SHALL remain explicitly unverified rather than being inferred from lower-level tests
