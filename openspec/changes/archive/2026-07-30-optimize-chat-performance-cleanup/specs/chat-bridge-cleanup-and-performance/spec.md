## Purpose

Keeps the chat bridge maintainable and fast by removing unreachable legacy run authorities while preserving routed chat behavior and requiring measured hot-path performance evidence.

## ADDED Requirements

### Requirement: Routed chat bridge uses a single authoritative run path
The system SHALL serve normal Codex, Hermes, and Claude Code chat run routes through the authoritative Provider run path. Compatibility route modules MUST resolve to that authority before handling normal chat run start and run event requests.

#### Scenario: Codex run routes resolve to the authoritative path
- **WHEN** the Codex run start route or Codex run event route is served through the chat bridge route module
- **THEN** the handler used for the request is the authoritative Codex run handler
- **AND** it does not use a service-local in-memory run queue as an alternate authority

#### Scenario: Hermes run routes resolve to the authoritative path
- **WHEN** the Hermes run start route or Hermes run event route is served through the chat bridge route module
- **THEN** the handler used for the request is the authoritative Hermes run handler
- **AND** it does not use a service-local in-memory run queue as an alternate authority

#### Scenario: Claude Code run routes resolve to the authoritative path
- **WHEN** the Claude Code run start route or Claude Code run event route is served through the chat bridge route module
- **THEN** the handler used for the request is the authoritative Claude Code run handler
- **AND** it does not use a service-local in-memory run queue as an alternate authority

### Requirement: Obsolete Provider run authorities are removed
The system MUST NOT retain obsolete Provider run authorities in the active chat bridge modules after they are proven unreachable from normal routed chat APIs. Static and runtime checks SHALL fail if an obsolete parallel run authority is reintroduced in the routed bridge path.

#### Scenario: Bridge modules are statically checked
- **WHEN** the Provider bridge boundary checks inspect the server and chat bridge service modules
- **THEN** no obsolete parallel run authority or legacy run-idempotency authority is present in those modules
- **AND** the checks require the current repository, journal, coordinator, and SSE transport boundary instead

#### Scenario: A future change reintroduces an obsolete run authority
- **WHEN** a future edit adds an obsolete parallel run authority to the routed chat bridge path
- **THEN** the boundary checks fail before the change is accepted
- **AND** the public route behavior is not used as evidence to ignore the stale authority

### Requirement: Public chat contracts remain compatible
The cleanup and performance work SHALL preserve public Codex, Hermes, and Claude Code chat and run route contracts, including request validation, response fields, SSE event names, cancellation behavior, approval behavior where supported, terminal outcomes, history visibility, and conversation attribution.

#### Scenario: Codex public contract is exercised
- **WHEN** focused Codex chat, run, SSE, approval, cancellation, terminal, and history regressions run after cleanup
- **THEN** previously supported public fields, event names, terminal semantics, and conversation/thread mapping remain valid

#### Scenario: Hermes and Claude Code public contracts are exercised
- **WHEN** focused Hermes and Claude Code chat, run, SSE, cancellation, terminal, and history regressions run after cleanup
- **THEN** previously supported public fields, event names, terminal semantics, and conversation attribution remain valid

#### Scenario: A stale direct-import expectation conflicts with the routed contract
- **WHEN** a test or helper expects a service-local bridge implementation instead of the routed authoritative behavior
- **THEN** the expectation is migrated to the routed contract or an explicit thin delegation
- **AND** it does not preserve a second state authority solely for compatibility

### Requirement: Internal optimized event publication remains bounded and private
The system MAY provide an internal optimized publication path for already bounded Codex fast-path events. That path MUST remain private to trusted server-side event processing, MUST NOT accept raw HTTP request payloads directly, and MUST preserve redaction, payload bounds, indexing, terminal deduplication, and replay behavior.

#### Scenario: Trusted event publication receives sanitized input
- **WHEN** the internal optimized publication path receives an event from the Codex fast path
- **THEN** the event has already passed through bounded sanitization
- **AND** replayed SSE payloads preserve the same public event semantics as the fully defensive publication path

#### Scenario: Raw external payload attempts to use the optimized path
- **WHEN** an HTTP route or other untrusted external input attempts to bypass normal publication defenses
- **THEN** the system rejects that path or routes through the fully defensive publication behavior
- **AND** untrusted input cannot skip redaction or payload bounding

#### Scenario: Terminal event is published through the optimized path
- **WHEN** a terminal event reaches the optimized publication path
- **THEN** terminal deduplication still prevents duplicate terminal outcomes for the same run
- **AND** run and conversation replay indexes remain consistent

### Requirement: Durable chat semantics are preserved over transient speed
The system MUST preserve durable user messages, final assistant replies, approvals, cancellations, failures, completions, terminal outcomes, history recovery, and conversation/thread mappings. Transient reasoning, text deltas, and tool progress MAY use faster or lower-copy handling only when durable semantics and ordering are not weakened.

#### Scenario: Completed turn is recovered after restart
- **WHEN** the application restarts after a completed chat turn
- **THEN** accepted user content, final assistant result, relevant approval state, terminal outcome, and conversation mapping remain recoverable through existing history surfaces
- **AND** recovery does not require every transient reasoning or delta fragment to have been durably stored

#### Scenario: Durable event and transient fragments overlap
- **WHEN** a durable approval, cancellation, failure, completion, or final result arrives while transient fragments are pending
- **THEN** the durable event is not reordered behind unrelated transient optimization work
- **AND** any required preceding transient content is delivered or discarded according to the existing transient-loss contract without corrupting durable state

### Requirement: Chat performance changes are measured and non-regressing
The system SHALL treat chat performance cleanup as verified only when reproducible before-and-after evidence uses the same deterministic fixture identity and shows no compatibility regression. Performance evidence MUST include sample counts, p50, p95, maximum latency, errors, and any relevant operation counts.

#### Scenario: Baseline and candidate fixtures are compared
- **WHEN** the deterministic Codex chat performance harness is run before and after the optimization
- **THEN** both runs use the same warm-up count, measured turn count, fake local app-server behavior, existing-thread setup, and event volume
- **AND** the evidence reports p50, p95, maximum latency, errors, and relevant operation counts

#### Scenario: Performance improvement is not distinguishable
- **WHEN** measured candidate results cannot distinguish an improvement from noise or changed fixture behavior
- **THEN** the optimization is not claimed as verified
- **AND** the change must still pass compatibility and correctness regressions

#### Scenario: Performance optimization regresses a public contract
- **WHEN** a performance optimization changes public route semantics, critical event names, terminal outcomes, replay behavior, approval handling, cancellation handling, or durable history
- **THEN** the optimization is rejected or revised before the change is accepted

### Requirement: Observability remains content-free and bounded
The system SHALL expose enough bounded diagnostics to identify cleanup safety, route authority, optimized publication usage, performance deltas, busy conditions, bypasses, and failures without logging prompts, replies, reasoning text, credentials, approval contents, or unrestricted filesystem paths.

#### Scenario: Diagnostics are emitted for optimized chat processing
- **WHEN** optimized chat processing records timing, counters, or fallback information
- **THEN** diagnostics use bounded identifiers, counters, categories, or digests
- **AND** diagnostics do not expose prompt text, reply text, reasoning text, credentials, approval contents, or unrestricted filesystem paths

#### Scenario: Optimized path falls back or fails
- **WHEN** the optimized event publication or telemetry path falls back or fails
- **THEN** the failure is observable through bounded diagnostics
- **AND** durable chat handling remains governed by the compatibility and durability requirements
