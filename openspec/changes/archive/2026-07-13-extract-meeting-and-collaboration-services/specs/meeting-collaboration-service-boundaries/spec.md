## ADDED Requirements

### Requirement: Incremental meeting-domain extraction
The system SHALL migrate meeting and collaboration behavior from HTTP and callback handlers into cohesive meeting-domain services in independently testable slices, and each migrated slice SHALL remain deployable without requiring later slices.

#### Scenario: One meeting slice is migrated
- **WHEN** a meeting-domain operation has migrated and its compatibility tests pass
- **THEN** HTTP, Feishu, and internal callers SHALL delegate that operation to the extracted service
- **AND** operations outside that slice SHALL retain their existing behavior

### Requirement: Explicit service dependencies
Meeting-domain services MUST accept validated application inputs and explicit persistence, project, clock, identity, agent-runtime, notification, and callback dependencies without reading HTTP handler state or writing transport responses.

#### Scenario: Service is tested without a server
- **WHEN** a test invokes an extracted meeting service with test dependencies
- **THEN** the operation SHALL complete without constructing an HTTP handler, Feishu receiver, or network server
- **AND** its result and state changes SHALL be assertable as application data

### Requirement: Meeting lifecycle compatibility
Extracted meeting lifecycle operations MUST preserve meeting creation, preparation, run, turn progression, completion, cancellation, failure, timeout, transition validation, participant configuration, context budgeting, summaries, resolutions, and stored record semantics.

#### Scenario: Executable meeting completes
- **WHEN** a valid meeting progresses through its supported turns and completion path
- **THEN** the same lifecycle states, timestamps, transcript metadata, summary, resolution, and terminal result SHALL be persisted

#### Scenario: Invalid or stale lifecycle command arrives
- **WHEN** a command targets an invalid transition, stale turn, terminal meeting, or missing meeting
- **THEN** the command SHALL preserve the existing rejection status and error code
- **AND** no partial meeting state mutation SHALL occur

### Requirement: Agent occupancy and restoration safety
Meeting services SHALL preserve participant eligibility, archive-manager exclusion, occupancy ownership, pre-meeting status snapshots, concurrent occupancy protection, and restoration of each Agent's prior state after every terminal or recovery path.

#### Scenario: Meeting occupies eligible Agents
- **WHEN** a meeting starts with eligible participants
- **THEN** each participant SHALL be marked occupied by that meeting only after its prior state is recorded
- **AND** another incompatible meeting SHALL not claim the same Agent concurrently

#### Scenario: Meeting terminates or is recovered
- **WHEN** a meeting completes, is cancelled, fails, times out, or is recovered after restart
- **THEN** each participant SHALL be released only if the meeting still owns its occupancy
- **AND** its recorded pre-meeting state SHALL be restored without overwriting a newer owner

### Requirement: AI meeting request confirmation and linkage
AI meeting requests MUST preserve project/task linkage, required request fields, urgency policy, context selection, duplicate blocking-request prevention, confirmation and rejection rules, conversion to one executable meeting, and project-execution blocker updates.

#### Scenario: Agent creates a meeting request
- **WHEN** an authorized execution Agent submits a valid request for its linked project task
- **THEN** the system SHALL create at most one unresolved blocking request for that project task
- **AND** the project execution state SHALL reflect that it is awaiting meeting resolution

#### Scenario: Meeting request requires human confirmation
- **WHEN** the existing confirmation policy requires a human decision
- **THEN** no executable meeting SHALL be created before an authorized confirmation
- **AND** rejection SHALL preserve the reason and return the linked execution to its existing human-decision state

#### Scenario: Confirmation or rejection is repeated
- **WHEN** the same valid decision is delivered more than once
- **THEN** the resulting request, meeting, and project state SHALL be equivalent to applying the decision once

### Requirement: Meeting result and project execution integration
Meeting completion MUST preserve the linkage between meeting request, meeting, project, task, and execution attempt, and SHALL resume, block, or await human intervention according to the existing resolution rules.

#### Scenario: Linked meeting resolves an execution blocker
- **WHEN** a linked executable meeting reaches a valid terminal resolution
- **THEN** its summary, resolution, and action items SHALL be recorded against the same linked context
- **AND** project execution SHALL advance only if the request, meeting, task, and attempt linkage is still current

#### Scenario: Stale meeting result arrives
- **WHEN** a meeting result targets a superseded request, task, attempt, or blocker
- **THEN** the stale result SHALL not overwrite newer project execution state

### Requirement: Action-item projection compatibility
Meeting action-item workflows MUST preserve action-item text, ownership, completion state, meeting linkage, explicit user selection, project/task destination, duplicate prevention, and existing API and persistence semantics.

#### Scenario: Selected action item is attached to an existing target task
- **WHEN** an authorized user confirms a selected meeting action item using the Meeting's linked source task or an explicit existing project/task destination for an unbound Meeting
- **THEN** exactly one compatible action-item record SHALL be attached to that existing target task with traceable Meeting and action-item linkage
- **AND** unrelated action items SHALL remain unchanged

#### Scenario: Action-item projection is repeated
- **WHEN** the same confirmation request is retried
- **THEN** the system SHALL return the existing target task and action-item record instead of creating a duplicate record

### Requirement: Notification delivery isolation
Meeting and request state transitions SHALL persist independently of external notification delivery, while notification intents, redacted DTOs, retry markers, and existing best-effort delivery behavior remain compatible.

#### Scenario: Notification provider fails
- **WHEN** a meeting, request, or action-item transition commits and Feishu notification delivery fails
- **THEN** the committed business state SHALL not roll back
- **AND** the sanitized delivery result SHALL be recorded using the existing diagnostic semantics

#### Scenario: Notification payload is constructed
- **WHEN** meeting-domain data is passed to a notification adapter
- **THEN** credentials, raw provider output, unrestricted transcripts, and disallowed absolute paths SHALL not be included

### Requirement: Feishu callback authenticity and idempotency
Feishu meeting actions MUST preserve callback authenticity checks, actor extraction, action allowlists, request and meeting linkage, duplicate-event handling, stable response content, and callback audit records.

#### Scenario: Authorized Feishu action is received
- **WHEN** an authentic callback contains a supported meeting-request or meeting action linked to current state
- **THEN** the callback adapter SHALL invoke the corresponding service command with a trusted entry context
- **AND** the action outcome SHALL be recorded once

#### Scenario: Forged, unsupported, or duplicate callback is received
- **WHEN** a callback is unauthenticated, contains an unsupported action, forges linkage, or repeats an already processed event
- **THEN** the system SHALL reject or idempotently replay it according to the existing contract
- **AND** no unauthorized meeting or project mutation SHALL occur

### Requirement: Recovery and persistence compatibility
Meeting, request, notification, and callback records written before extraction MUST remain recoverable through the supported migration path, and restart recovery SHALL preserve terminal-state detection, preparation timeout handling, occupancy repair, and request-to-meeting linkage.

#### Scenario: Application restarts with active meeting records
- **WHEN** the application loads compatible pre-extraction records containing an active or preparing meeting
- **THEN** recovery SHALL either resume the supported state or fail it using the existing timeout and cleanup rules
- **AND** Agent occupancy SHALL be reconciled without duplicate ownership

### Requirement: Unified authoritative Meeting store
The system SHALL maintain executable Meetings, Meeting events, Agent occupancy, AI meeting requests, request-to-meeting conversion state, and Meeting-domain idempotency metadata in one authoritative JSON store after migration.

#### Scenario: Meeting-domain state is committed
- **WHEN** a Meeting lifecycle, request, occupancy, conversion, or idempotency command commits
- **THEN** the command SHALL update the unified JSON store through one atomic replacement boundary
- **AND** runtime code SHALL not require coordinated writes to a second Meeting-domain JSON store

#### Scenario: Unified store is loaded
- **WHEN** the application starts after successful migration
- **THEN** Meeting lifecycle, request, recovery, callback, and project-linkage operations SHALL read from the unified store
- **AND** the two legacy stores SHALL not remain parallel authorities

### Requirement: Safe and idempotent legacy-store migration
The system MUST provide a migration script that combines the existing executable-Meeting and Meeting-request JSON stores into the unified schema without losing compatible records, events, occupancy, linkage, idempotency, or timestamps.

#### Scenario: Migration succeeds
- **WHEN** both legacy stores are valid and their records can be combined without an identity or linkage conflict
- **THEN** the script SHALL create timestamped backups of both inputs
- **AND** it SHALL write and validate the unified store atomically before reporting success
- **AND** the resulting counts and relationship checks SHALL be included in a migration report

#### Scenario: Migration is repeated
- **WHEN** the migration script runs again after the same data has already migrated successfully
- **THEN** it SHALL produce an equivalent unified state without duplicate Meetings, requests, events, occupancy claims, conversion links, or idempotency entries
- **AND** it SHALL report that no destructive re-migration was required

#### Scenario: Legacy input is invalid or conflicting
- **WHEN** a legacy file is malformed, a record identity collides with different content, a request references an incompatible Meeting, or occupancy cannot be reconciled safely
- **THEN** the script SHALL fail closed before replacing the authoritative store
- **AND** it SHALL preserve both legacy inputs and any previously valid unified store
- **AND** it SHALL report sanitized conflict details for manual resolution

#### Scenario: Application starts before migration
- **WHEN** the unified store is absent but either legacy store contains Meeting-domain data
- **THEN** the application SHALL refuse Meeting-domain mutations with a stable migration-required error
- **AND** it SHALL not silently create an empty unified store or partially migrate data at runtime

#### Scenario: Migration rollback is requested
- **WHEN** post-migration verification fails before release approval
- **THEN** operators SHALL be able to stop the single server process and restore both timestamped legacy backups
- **AND** the rollback procedure SHALL not depend on reverse-transforming partially modified unified data

### Requirement: API, event, and storage compatibility
The change MUST NOT intentionally alter public route paths, accepted request fields, response JSON fields, status semantics, meeting projections, SSE or WebSocket events, frontend calls, Feishu payload contracts, or project-execution interfaces. The internal Meeting persistence layout SHALL change only through the confirmed unified-store migration contract.

#### Scenario: Compatibility regression suite runs
- **WHEN** service, HTTP, callback, persistence, notification, project-linkage, SSE, and WebSocket regression tests run for migrated slices
- **THEN** all previously supported scenarios SHALL remain valid unless a separately confirmed specification explicitly changes them

### Requirement: Verified defect correction during migration
The change SHALL permit correction of a defect discovered in the active meeting slice only when it is reproducible, the expected behavior follows an existing product or safety invariant, and a regression test distinguishes the correction from migration drift.

#### Scenario: Confirmed in-scope defect is found
- **WHEN** migration exposes a reproducible meeting-domain defect with unambiguous expected behavior
- **THEN** the defect MAY be fixed in that slice
- **AND** the behavior difference SHALL be documented and covered by a failing-before regression

#### Scenario: Suspected or out-of-scope defect is found
- **WHEN** an issue lacks reproducible evidence, has ambiguous expected behavior, or belongs outside the active slice
- **THEN** it SHALL not be changed incidentally
- **AND** it SHALL be recorded for clarification or a separately scoped change

### Requirement: Backend-only modularization scope
This change SHALL limit experience improvements to meeting-domain reliability, recovery, latency, testability, and error correctness, and MUST NOT introduce meeting-page interaction or visual redesign.

#### Scenario: Frontend redesign is proposed
- **WHEN** an adjustment changes meeting-page layout, styling, user workflow, or interaction behavior
- **THEN** it SHALL be excluded unless a separate specification is confirmed
