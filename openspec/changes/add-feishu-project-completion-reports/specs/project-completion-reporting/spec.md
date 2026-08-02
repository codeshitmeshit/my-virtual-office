## ADDED Requirements

### Requirement: Projects expose an independent Feishu reporting preference
Every newly created project SHALL have a project-scoped Feishu completion-report preference that defaults to enabled. An authorized project owner MUST be able to change that preference until the project first reaches successful completion. The preference SHALL become immutable at that transition and SHALL remain the effective choice for later reruns of the same project.

#### Scenario: A project is created without an explicit reporting choice
- **WHEN** any supported project-creation path creates a project without an explicit Feishu reporting value
- **THEN** the project SHALL persist its Feishu completion-report preference as enabled

#### Scenario: The owner changes the preference before first successful completion
- **WHEN** the project owner changes the Feishu reporting preference before the project's first successful completion
- **THEN** the project SHALL persist the new project-scoped value
- **AND** the completion flow SHALL use that value for the first successful execution and later reruns

#### Scenario: A reporting preference change is requested after successful completion
- **WHEN** a user requests a change to the Feishu reporting preference after the project first completed successfully
- **THEN** the request SHALL be rejected
- **AND** the persisted project-scoped value SHALL remain unchanged

#### Scenario: A user has preferences from another project
- **WHEN** a new project is created after the same user enabled or disabled reporting on another project
- **THEN** the new project SHALL still default to enabled
- **AND** no personal reporting default SHALL override the project-scoped choice

### Requirement: Only enabled successful completion occurrences trigger reports
The system SHALL create one completion-report delivery intent for each distinct successful project completion occurrence whose effective reporting preference is enabled. Disabled projects and unsuccessful terminal outcomes MUST NOT create a Feishu completion report.

#### Scenario: An enabled project completes successfully
- **WHEN** an enabled project reaches successful completion
- **THEN** the system SHALL create a completion-report delivery intent for that completion occurrence
- **AND** report processing SHALL remain independent of the completed project state

#### Scenario: Reporting is disabled at successful completion
- **WHEN** a project reaches successful completion while its effective reporting preference is disabled
- **THEN** the system SHALL NOT create a Feishu completion-report delivery intent

#### Scenario: A project fails or is cancelled
- **WHEN** a project reaches an unsuccessful terminal outcome
- **THEN** the system SHALL NOT create a Feishu completion report
- **AND** the existing VO unsuccessful-project notification behavior SHALL remain unchanged

#### Scenario: A successful completion signal is repeated
- **WHEN** the same successful completion occurrence is observed more than once
- **THEN** the system SHALL retain one completion-report delivery intent for that occurrence
- **AND** automatic processing SHALL NOT deliver duplicate reports for that occurrence

### Requirement: Successful reruns produce distinguishable reports
Each successful rerun of an enabled project SHALL be eligible for a new completion report, and every report MUST identify the completion occurrence with a user-readable execution or version marker.

#### Scenario: An enabled completed project succeeds again
- **WHEN** the project reaches a new successful completion occurrence after a rerun
- **THEN** the system SHALL create a new completion-report delivery intent
- **AND** the new report SHALL carry an execution or version marker distinct from earlier reports

#### Scenario: The owner compares reports from two successful runs
- **WHEN** the owner views completion reports from two successful occurrences of the same project
- **THEN** each report SHALL expose enough project and version context to identify which result is newer

### Requirement: Report generation is limited to final project artifacts
Completion-report generation MUST use only final project artifacts that are eligible for the project owner to receive. Execution logs, intermediate files, internal instructions, hidden reasoning, credentials, and other internal-only information MUST NOT be included in the report-generation input or delivered report.

#### Scenario: Final and intermediate materials both exist
- **WHEN** report generation prepares input for a successfully completed project
- **THEN** it SHALL include eligible final artifacts
- **AND** it SHALL exclude logs, intermediate files, and internal-only information

#### Scenario: A final artifact is unavailable or ineligible
- **WHEN** an expected final artifact is missing, unreadable, too large for supported reporting, or not eligible for owner delivery
- **THEN** the report SHALL identify that the artifact could not be presented
- **AND** the system SHALL NOT substitute excluded process or internal content

### Requirement: Reports are human-readable and delivered by the notification bot
The reporting agent SHALL transform eligible final artifacts into a human-readable report containing the project goal, execution conclusion, key results, non-fatal exceptions, recommended follow-ups, important final artifacts, and execution or version marker. The system SHALL deliver that report only to the project creator through the Feishu notification bot and MUST NOT use the Feishu chat bot for this flow.

#### Scenario: A report is generated from eligible final artifacts
- **WHEN** the reporting agent receives the eligible final artifacts for a completion occurrence
- **THEN** it SHALL produce a structured report covering the required human-readable sections
- **AND** it SHALL preserve references needed to inspect important final artifacts

#### Scenario: The report is ready for delivery
- **WHEN** a generated completion report is ready
- **THEN** the Feishu notification bot SHALL send it to the project creator's mapped Feishu identity
- **AND** no project participant, group, alternate recipient, or chat-bot conversation SHALL receive it through this capability

#### Scenario: The project creator has no usable Feishu destination
- **WHEN** the report is ready but the project creator has no valid Feishu notification destination
- **THEN** delivery SHALL enter a visible failed state
- **AND** the report SHALL NOT be redirected to another recipient

### Requirement: Project completion and report delivery have separate states
The system MUST represent report delivery independently from project execution. Report processing SHALL expose user-visible pending, delivered, and failed outcomes, and no report-generation or delivery failure SHALL reverse, delay, or misrepresent successful project completion.

#### Scenario: Report processing is still pending
- **WHEN** a project has completed successfully and its report has not reached a terminal delivery outcome
- **THEN** the project SHALL remain completed
- **AND** the project experience SHALL expose that report delivery is pending

#### Scenario: Report delivery succeeds
- **WHEN** the notification bot confirms successful delivery
- **THEN** the report delivery state SHALL become delivered for that completion occurrence
- **AND** the project SHALL remain completed

#### Scenario: Report generation or delivery fails
- **WHEN** report generation or Feishu delivery reaches a non-recoverable outcome for the current automatic attempt policy
- **THEN** the report delivery state SHALL become visibly failed with a user-readable reason
- **AND** the project SHALL remain completed

### Requirement: Failed report delivery supports automatic recovery and manual resend
The system SHALL automatically retry recoverable report-generation or delivery failures under a bounded policy and SHALL allow the project owner to manually resend a failed report. Automatic retries and repeated processing MUST NOT create duplicate automatic deliveries for the same completion occurrence.

#### Scenario: A recoverable report failure occurs
- **WHEN** report generation or delivery fails with a recoverable outcome and automatic retry capacity remains
- **THEN** the system SHALL schedule another delivery attempt
- **AND** the project SHALL remain completed while recovery proceeds

#### Scenario: Automatic recovery is exhausted
- **WHEN** the bounded automatic retry policy is exhausted without delivery
- **THEN** the delivery state SHALL remain visibly failed
- **AND** the owner SHALL be offered a manual resend action

#### Scenario: The owner requests a manual resend
- **WHEN** the authorized project owner requests resend for a failed completion report
- **THEN** the system SHALL initiate a new attempt for the same completion occurrence and report version
- **AND** the project completion state SHALL remain unchanged

#### Scenario: An unauthorized user requests resend
- **WHEN** a user other than the authorized project owner requests resend
- **THEN** the request SHALL be rejected
- **AND** no report attempt or recipient SHALL be changed
