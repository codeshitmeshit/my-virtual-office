## ADDED Requirements

### Requirement: Fixed daily collection cycle
The system SHALL run one global HR daily-report collection cycle at a configured VO-local time, establish a bounded submission window, and target every Agent that is eligible at the cycle's effective roster snapshot.

#### Scenario: Daily cycle becomes due
- **WHEN** the configured daily collection time is reached and HR is available
- **THEN** one cycle SHALL be opened for the VO-local date and each eligible Agent SHALL receive one report request

#### Scenario: HR or an Agent is unavailable
- **WHEN** HR is paused or an Agent is ineligible at cycle time
- **THEN** the applicable request SHALL be skipped with a reason
- **AND** other eligible Agents SHALL continue through the cycle

### Requirement: Raw and normalized daily reports
For each submitted report, HR SHALL preserve the Agent's original response and produce a normalized report containing the date, Agent identity, completed work, related projects or tasks, produced artifacts, blockers, requested help, submission state, and timestamps.

#### Scenario: Agent submits during the window
- **WHEN** a targeted Agent responds with its daily work
- **THEN** the system SHALL store the immutable raw response and HR's normalized representation under that Agent and date
- **AND** the record SHALL identify HR as the normalizer rather than the source of the Agent's claims

#### Scenario: Normalization fails
- **WHEN** HR cannot normalize a valid raw response
- **THEN** the raw response SHALL remain available and the report SHALL be marked `normalization_failed` for retry

### Requirement: Versioned structured report request contract
Every HR daily-report question SHALL identify its request as `vo.hr.daily_report` using a JSON context containing schema version, stable Agent AI ID, and VO-local date, and SHALL provide an exact preferred JSON response shape for completed work, related projects or tasks, artifacts, blockers, and requested help.

#### Scenario: Agent supports structured output
- **WHEN** a targeted Agent can produce valid JSON
- **THEN** it SHOULD return only the requested JSON object without Markdown or additional fields
- **AND** HR SHALL still preserve that JSON text as the Agent-authored raw response before normalization

#### Scenario: Provider cannot reliably produce JSON
- **WHEN** a targeted Agent cannot return valid JSON in its current runtime
- **THEN** it MAY return a clear natural-language report
- **AND** the system SHALL preserve and normalize that response through the same strict HR output contract instead of rejecting the submission

### Requirement: Neutral non-submission and late submission
The reporting workflow MUST treat missing responses as an unknown submission state rather than evidence of low work, MUST NOT invent a replacement report, and SHALL allow a later response to complete the same dated record.

#### Scenario: Submission window closes without response
- **WHEN** a targeted Agent has not responded by window close
- **THEN** its dated record SHALL be marked `not_submitted`
- **AND** no work conclusion, synthetic self-report, or negative assessment SHALL be inferred from non-response alone

#### Scenario: Agent submits after the window
- **WHEN** a previously non-submitting Agent later supplies a report for that date
- **THEN** the same dated record SHALL become a late submission with original request, close, and submission timestamps retained

### Requirement: Daily idempotency and restart recovery
The reporting workflow MUST maintain at most one authoritative collection cycle and one authoritative report record per Agent and VO-local date despite retries, duplicate delivery, scheduler overlap, or service restart.

#### Scenario: Scheduler fires twice
- **WHEN** the same daily occurrence is delivered repeatedly
- **THEN** the system SHALL reuse the existing cycle and SHALL NOT send duplicate effective requests or create duplicate reports

#### Scenario: VO restarts during an open cycle
- **WHEN** VO restarts before the collection window closes
- **THEN** the workflow SHALL recover the existing cycle, reconcile outstanding Agents, and preserve already received responses

#### Scenario: VO starts after a missed occurrence
- **WHEN** VO starts after a due cycle did not run
- **THEN** the scheduler SHALL record and process the occurrence according to the configured catch-up policy without creating multiple cycles for the date

### Requirement: Per-Agent failure isolation
Failure, timeout, malformed response, or unavailability for one Agent SHALL NOT block report requests, submissions, normalization, or cycle completion for other Agents.

#### Scenario: One Agent request fails
- **WHEN** delivery to one eligible Agent fails
- **THEN** that Agent's request state SHALL record the failure and retry disposition
- **AND** the cycle SHALL continue for all other eligible Agents

#### Scenario: HR sends a daily-report request
- **WHEN** HR requests a scheduled or manually corrected daily report from an Agent
- **THEN** the request SHALL use the shared provider-neutral VO communication application service
- **AND** VO SHALL record the visible HR-to-Agent request and reply under the deterministic conversation identity
- **AND** timeout, busy, empty reply, communication-skill readiness, and Provider error codes SHALL remain distinguishable to the HR workflow

### Requirement: Traceable reporting states
The system SHALL expose enough state to distinguish not due, waiting, submitted, late submitted, not submitted, normalization failed, skipped, and complete outcomes at both cycle and Agent levels.

#### Scenario: Human inspects today's cycle
- **WHEN** the Human Resources module loads the active or most recent cycle
- **THEN** it SHALL show accurate counts and per-Agent states without presenting unfinished data as completed

### Requirement: Explicit selected-Agent daily correction
Human management SHALL be able to select one or more currently available non-HR Agents, including selecting all available Agents, and request a new report for the current VO-local date without closing the global cycle.

#### Scenario: Selected Agent returns a corrected report
- **WHEN** a human confirms a manual daily synchronization and a selected Agent returns a non-empty report
- **THEN** the same authoritative Agent/date record SHALL replace its raw response, clear stale normalization, increment its revision, and be normalized again
- **AND** no second authoritative dated report SHALL be created

#### Scenario: Selected Agent does not respond
- **WHEN** a selected Agent times out, fails, or returns no report
- **THEN** its previous report and assessment SHALL remain unchanged
- **AND** successful selected Agents SHALL continue independently
