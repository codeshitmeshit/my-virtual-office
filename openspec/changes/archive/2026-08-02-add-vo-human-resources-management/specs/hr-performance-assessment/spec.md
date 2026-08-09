## ADDED Requirements

### Requirement: HR-only assessment authority
Only the globally registered HR role SHALL create, revise, or finalize an Agent performance assessment; humans may inspect assessments, and ordinary Agents SHALL NOT impersonate HR or mutate assessment content.

#### Scenario: HR evaluates an Agent
- **WHEN** the daily collection window has ended and HR is available
- **THEN** HR SHALL create or update that Agent's dated assessment from permitted evidence

#### Scenario: Non-HR actor attempts assessment mutation
- **WHEN** an ordinary Agent or untrusted caller attempts to create, edit, replace, or finalize an assessment
- **THEN** the operation SHALL be rejected and no assessment state SHALL change

### Requirement: Evidence-backed daily assessment
Each assessment SHALL distinguish traceable facts from HR judgment and MAY use the Agent's report, project and task records, relevant meeting records, artifacts, execution results, and known blockers without treating any single source as sufficient by default.

#### Scenario: Multiple evidence sources are available
- **WHEN** HR assesses an Agent with a report and relevant VO activity
- **THEN** the assessment SHALL reference the evidence used and explain the relationship between evidence, contribution, workload, blockers, and recommendations

#### Scenario: Meeting evidence is relevant
- **WHEN** a meeting record demonstrates work relevant to the evaluated date
- **THEN** HR MAY cite that record as evidence
- **AND** mere meeting attendance or HR's participation SHALL NOT automatically create a positive or negative performance conclusion

### Requirement: Structured non-ranking assessment
An assessment SHALL contain the Agent, date, principal contributions, workload level, rationale, evidence references, blockers, strengths, improvement opportunities, runtime-state diagnosis, information sufficiency or confidence explanation, HR identity, and timestamps, and SHALL NOT contain a numeric score or cross-Agent rank.

#### Scenario: Assessment has sufficient evidence
- **WHEN** HR can support a daily conclusion
- **THEN** workload SHALL be classified as `low`, `appropriate`, `high`, or `overloaded` with written rationale and evidence

#### Scenario: Evidence is insufficient
- **WHEN** available evidence cannot support a workload conclusion
- **THEN** workload SHALL be `insufficient_information`
- **AND** HR SHALL state what is missing instead of inferring low activity

#### Scenario: Assessments are compared
- **WHEN** a caller views multiple Agents or dates
- **THEN** the system SHALL NOT calculate or present a leaderboard, ordinal rank, aggregate numeric score, or automatic elimination recommendation

### Requirement: Growth and operational-diagnostic purpose
HR assessments SHALL focus on contribution understanding, actionable improvement, blocker visibility, and signs of idle, overloaded, unavailable, or mismatched operation and SHALL NOT automatically punish, pause, delete, or reassign an Agent.

#### Scenario: HR detects overload or a recurring blocker
- **WHEN** evidence indicates overload or a repeated operational problem
- **THEN** HR SHALL explain the observation and suggest support or improvement
- **AND** it SHALL NOT automatically change the Agent's lifecycle or project assignments

### Requirement: Assessment idempotency and revision history
The system SHALL maintain one current assessment per Agent and date while preserving prior versions, reasons, evidence changes, and timestamps whenever a late report or corrected evidence causes reassessment.

#### Scenario: Assessment job is retried
- **WHEN** HR repeats evaluation with the same evidence version
- **THEN** the system SHALL return or retain the current assessment without creating a duplicate effective version

#### Scenario: Late report changes the evidence set
- **WHEN** an Agent submits late after an assessment exists
- **THEN** HR MAY issue a revised assessment with the earlier version and revision reason retained

#### Scenario: Human manually corrects today's report
- **WHEN** manual daily synchronization successfully replaces an Agent's current-date report
- **THEN** HR SHALL immediately generate the corresponding assessment from the refreshed report without waiting for global cycle closure
- **AND** the new assessment SHALL become current with revision reason `manual_daily_sync` while all prior assessment versions remain readable

### Requirement: Assessment failure isolation
An assessment failure for one Agent SHALL be visible and retryable without preventing other Agents' dated assessments or corrupting the last valid assessment.

#### Scenario: HR cannot assess one Agent
- **WHEN** evidence loading or assessment generation fails for one Agent
- **THEN** that assessment SHALL be marked failed with a safe reason
- **AND** other Agents SHALL continue through the assessment cycle
