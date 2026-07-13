## ADDED Requirements

### Requirement: Incremental provider-service extraction
The system SHALL migrate provider-neutral run, conversation, approval, cancellation, and event orchestration from transport handlers into cohesive application services in independently testable slices.

#### Scenario: One provider slice is migrated
- **WHEN** a provider orchestration slice has migrated and its compatibility suite passes
- **THEN** HTTP, SSE, Project Execution, Meeting, and internal callers SHALL delegate that slice to the extracted service
- **AND** provider paths outside the slice SHALL retain their existing behavior

### Requirement: Provider-neutral service dependencies
Provider services MUST accept validated application commands and explicit registry, clock, ID, task-launcher, adapter, persistence, approval, and event-sink dependencies without constructing HTTP handlers or importing the main server module.

#### Scenario: Service is tested without a server
- **WHEN** a test invokes a provider service using in-memory ports and a fake provider adapter
- **THEN** run lifecycle, conversation, approval, cancellation, and event results SHALL be assertable without starting an HTTP or SSE server

#### Scenario: Transport response is produced
- **WHEN** a service result reaches an HTTP or SSE adapter
- **THEN** only the transport layer SHALL choose status lines, headers, framing, and connection behavior

### Requirement: Provider adapter responsibility
OpenClaw, Codex, Claude Code, and Hermes adapters SHALL own provider-specific command invocation, protocol parsing, authentication handoff, and native identifier conversion, while provider services SHALL own provider-neutral orchestration and state transitions.

#### Scenario: Provider-specific invocation runs
- **WHEN** a provider-neutral command targets a supported provider kind
- **THEN** the service SHALL select the matching adapter and pass a bounded provider-neutral request
- **AND** the adapter SHALL return normalized events and results without mutating shared run state directly

#### Scenario: Unsupported provider kind is requested
- **WHEN** a command names an unsupported or unavailable provider kind
- **THEN** the system SHALL preserve the existing stable rejection status and error semantics
- **AND** no run, conversation, approval, or event state SHALL be partially registered

### Requirement: Run registry and lifecycle compatibility
Provider services MUST preserve run creation, provider and Agent identity, conversation linkage, background execution, status polling, completion, failure, timeout, cleanup, retention, and existing metadata semantics.

#### Scenario: Background run completes
- **WHEN** an accepted provider run emits progress and reaches a terminal result
- **THEN** the registry SHALL expose the same run identity, provider path, conversation identity, progress metadata, terminal status, and compatible result fields
- **AND** exactly one terminal transition SHALL be published

#### Scenario: Run fails before or during execution
- **WHEN** validation, adapter launch, event parsing, persistence, or provider execution fails
- **THEN** the run SHALL fail closed using the existing error/status contract
- **AND** active-run, cancellation, approval, and retention state SHALL not remain falsely active

### Requirement: Run idempotency and concurrent ownership
Provider run start commands SHALL preserve their existing idempotency scope across provider kind, Agent, conversation, and caller key, and concurrent starts SHALL not create duplicate provider work for one accepted scope.

#### Scenario: Start request is repeated
- **WHEN** the same valid idempotent run-start request is delivered again
- **THEN** the system SHALL return the existing compatible run or terminal result without launching the adapter twice

#### Scenario: Concurrent starts use different scopes
- **WHEN** independent Agents, conversations, providers, or idempotency keys start concurrently
- **THEN** their registry state and event streams SHALL remain isolated
- **AND** one run SHALL not block unrelated provider work beyond existing capacity limits

### Requirement: Normalized event ordering and SSE replay
Provider services SHALL normalize provider events into the existing public event names and payload shapes while preserving monotonic event identity, ordering, replay-after behavior, terminal delivery, keepalive behavior, and bounded retention.

#### Scenario: Client reconnects to a run stream
- **WHEN** an SSE client reconnects with the last observed event identity
- **THEN** the system SHALL replay only later retained events in order
- **AND** it SHALL deliver the compatible terminal event when the run has completed

#### Scenario: Provider emits duplicate or malformed progress
- **WHEN** an adapter reports duplicate, unsupported, oversized, or malformed progress data
- **THEN** normalization SHALL preserve existing compatibility rules and bounded payloads
- **AND** malformed progress SHALL not corrupt the registry or fabricate a successful terminal result

### Requirement: Provider conversation continuity and isolation
Conversation services MUST preserve provider-specific continuation identifiers, Agent/profile scoping, history association, attachment context, conversation creation and reset behavior, and isolation between unrelated conversations.

#### Scenario: Existing conversation continues
- **WHEN** a caller sends another compatible message with an existing conversation identity
- **THEN** the selected adapter SHALL receive the correct native continuation identity and bounded prior context
- **AND** newly normalized activity SHALL remain associated with that conversation

#### Scenario: Conversation identity is absent or foreign
- **WHEN** a caller starts without an identity or supplies an identity outside the current Agent/provider/profile scope
- **THEN** the system SHALL create or reject according to existing provider behavior
- **AND** it SHALL not expose or append another conversation's history

### Requirement: Approval lifecycle compatibility
Provider approval services SHALL preserve pending approval detection, bounded command and description data, Agent/profile/session/run linkage, allowed decisions, queue ordering, Feishu delivery coordination, resolution, retry, and audit semantics.

#### Scenario: Provider requests approval
- **WHEN** an adapter emits a valid approval request during a run
- **THEN** exactly one linked pending approval SHALL be registered and exposed through existing APIs and notifications
- **AND** the run SHALL retain enough state to continue or terminate according to the selected decision

#### Scenario: Approval decision is stale, forged, or repeated
- **WHEN** a decision names an unsupported action, mismatched Agent/session/run, missing approval, or already resolved approval
- **THEN** it SHALL be rejected or replayed idempotently according to the existing contract
- **AND** no unrelated provider command SHALL be approved

### Requirement: Cancellation and terminal race safety
Cancellation services MUST preserve provider-specific stop behavior, cooperative local cancellation, stable cancelled results, terminal event publication, and idempotency when cancellation races with normal completion or failure.

#### Scenario: Active run is cancelled
- **WHEN** an authorized caller cancels an active run
- **THEN** the service SHALL invoke the matching adapter cancellation port at most as required by the existing provider contract
- **AND** registry and SSE consumers SHALL observe a compatible terminal cancellation result

#### Scenario: Cancellation races with completion
- **WHEN** cancellation and provider completion arrive concurrently
- **THEN** exactly one compatible terminal outcome SHALL win
- **AND** a late result SHALL not reopen, overwrite, or duplicate terminal events for the run

### Requirement: Provider isolation and failure containment
A failure, unavailable binary, invalid native response, timeout, or cancellation in one provider path SHALL not corrupt or disable other providers, conversations, runs, approvals, or event streams.

#### Scenario: One adapter is unavailable
- **WHEN** one configured provider cannot start or its health check fails
- **THEN** only commands targeting that provider SHALL report the compatible unavailable/error state
- **AND** healthy provider adapters SHALL continue to accept work

#### Scenario: Adapter callback arrives after cleanup
- **WHEN** a late provider event or result targets an expired, cancelled, or cleared run
- **THEN** it SHALL be ignored or recorded using existing bounded diagnostics
- **AND** it SHALL not recreate active state or attach to another run

### Requirement: Sensitive provider data boundaries
Provider services and normalized events MUST keep credentials, authorization headers, cookies, environment secrets, unrestricted prompts/transcripts, raw provider output, and disallowed absolute paths out of public DTOs, persisted diagnostics, notifications, and logs.

#### Scenario: Adapter returns sensitive error data
- **WHEN** a provider failure contains a credential, private path, raw request, or unrestricted response
- **THEN** public and persisted diagnostics SHALL contain only bounded redacted fields
- **AND** the original secret-bearing value SHALL not be copied into run events or approval records

### Requirement: API and event compatibility
The change MUST NOT intentionally alter existing provider route paths, accepted request fields, response JSON fields, status semantics, SSE event names/payloads, polling behavior, conversation identifiers, approval actions, cancellation contracts, or Project Execution and Meeting provider ports.

#### Scenario: Compatibility regression suite runs
- **WHEN** OpenClaw, Codex, Claude Code, Hermes, provider-run, conversation, approval, cancellation, HTTP, SSE, Project Execution, and Meeting regression tests execute
- **THEN** every previously supported scenario SHALL remain valid unless a separately confirmed specification explicitly changes it

### Requirement: Bounded registry and performance behavior
Provider orchestration SHALL retain bounded run, event, idempotency, conversation, and approval state, and extraction MUST NOT increase provider launches, duplicate event publication, unbounded scans, or lock duration around slow provider work.

#### Scenario: Fixed small, medium, and large fixtures run
- **WHEN** fixed run/event/conversation fixtures execute before and after extraction
- **THEN** provider invocation and terminal-event counts SHALL not increase
- **AND** registry scans, retained bytes, lock-held work, median, and p95 measurements SHALL remain within documented acceptance bounds

### Requirement: Final dependency direction and seam removal
After a provider slice migrates, compatibility delegates SHALL contain transport adaptation only, provider services SHALL not import `server.py`, HTTP handler types, or provider-specific transport implementations, and obsolete parallel registries or orchestration paths SHALL be removed.

#### Scenario: Static boundary checks run
- **WHEN** module dependency and direct-state-access checks inspect the final code
- **THEN** migrated provider business orchestration SHALL have one service owner
- **AND** no second runtime authority or server-to-service dependency cycle SHALL remain

### Requirement: Verified defect correction during extraction
The change SHALL permit correction of a provider defect only when it is reproducible, expected behavior follows an existing compatibility or safety invariant, and a regression test distinguishes the correction from refactoring drift.

#### Scenario: Confirmed in-scope provider defect is found
- **WHEN** extraction exposes a reproducible provider defect with unambiguous expected behavior
- **THEN** the defect MAY be corrected in the active slice
- **AND** the correction SHALL be documented and covered by a failing-before regression

#### Scenario: Suspected or out-of-scope issue is found
- **WHEN** an issue lacks reproducible evidence, changes product policy, or belongs outside provider orchestration
- **THEN** it SHALL not be changed incidentally
- **AND** it SHALL be recorded for clarification or a separately confirmed change

### Requirement: Backend-only final modularization scope
This change SHALL limit experience improvements to provider reliability, isolation, recovery, latency, testability, and error correctness, and MUST NOT introduce frontend workflow, visual, provider-policy, authentication-policy, or approval-policy redesign.

#### Scenario: Product behavior redesign is proposed
- **WHEN** an adjustment changes a user workflow, UI contract, provider choice policy, approval policy, or credential-management behavior
- **THEN** it SHALL be excluded unless a separate specification is confirmed
