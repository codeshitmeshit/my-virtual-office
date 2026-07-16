## ADDED Requirements

### Requirement: Warm continued Codex chat has explicit responsiveness SLOs
For a controlled warm-chat fixture in which the Codex app-server is already running, authentication is ready, and the selected conversation has an existing resumable thread, the system SHALL show working feedback with p95 latency no greater than 200 milliseconds and SHALL deliver the first native Agent event with p95 latency no greater than 1 second. The first-text latency SHALL be measured separately and MUST NOT be represented as meeting a fixed SLO when it depends on model or task behavior.

#### Scenario: Measure working feedback for a warm continued chat
- **WHEN** the controlled fixture submits repeated messages to an existing resumable Codex conversation
- **THEN** the time from accepted user submission to visible working feedback has a p95 no greater than 200 milliseconds
- **AND** the measurement identifies its sample count, warm-up treatment, clock boundaries, and observed p50 and p95

#### Scenario: Measure the first native Agent event
- **WHEN** the warm controlled Provider emits a native event for each accepted turn
- **THEN** the time from accepted user submission to delivery of the first matching native Agent event has a p95 no greater than 1 second
- **AND** first-text latency is reported as a separate observation rather than folded into the native-event result

#### Scenario: Slow model output follows prompt activity
- **WHEN** working feedback and a native event have been delivered but the Provider has not produced text
- **THEN** the chat remains visibly active without claiming that first-text completion met a fixed SLO

### Requirement: The first live fragment is not delayed by batching
The system SHALL make the first displayable fragment of a Codex turn immediately eligible for delivery. After that first fragment, the system MAY adaptively coalesce high-frequency transient fragments within a window from 33 through 100 milliseconds, but MUST preserve content, ordering, conversation attribution, and prompt handling of key lifecycle events.

#### Scenario: First displayable fragment arrives
- **WHEN** a Codex turn produces its first displayable text, reasoning, or activity fragment
- **THEN** the system delivers that fragment without waiting for a coalescing window to expire

#### Scenario: High-frequency transient fragments arrive
- **WHEN** multiple later reasoning or text-delta fragments for the same conversation arrive faster than the configured delivery cadence
- **THEN** the system may combine them within an adaptive 33-100 millisecond window
- **AND** the displayed aggregate has the same ordered content as the original fragments

#### Scenario: Key event arrives while transient fragments are buffered
- **WHEN** an approval, cancellation, failure, completion, or final-message event arrives while transient fragments are pending
- **THEN** the key event is not held behind the normal transient coalescing interval
- **AND** any preceding content required for correct ordering is delivered before the key event

### Requirement: Unrelated Codex conversations do not share a Virtual Office execution bottleneck
Virtual Office SHALL preserve ordered single-turn behavior within one Codex conversation while allowing different Codex conversations to make progress without waiting on a Virtual Office-wide execution or persistence lock. Provider concurrency MUST remain bounded, and capacity rejection or queueing MUST be explicit and observable.

#### Scenario: Two different conversations run concurrently
- **WHEN** two warm Codex chat turns target different conversation identifiers within available Provider capacity
- **THEN** one conversation does not wait for the other conversation's full turn solely because of a Virtual Office-wide lock
- **AND** events from each turn remain attributed only to their matching conversation

#### Scenario: Two turns target the same conversation
- **WHEN** overlapping requests target the same Codex conversation
- **THEN** the system preserves the existing supported single-turn ordering or busy behavior
- **AND** it does not interleave two turns in a way that corrupts the native thread

#### Scenario: Provider capacity is exhausted
- **WHEN** a new Codex turn arrives after the bounded concurrency capacity has been reached
- **THEN** the system returns or exposes a stable busy or queued state according to the existing public contract
- **AND** the request does not create unbounded background work

### Requirement: Durable and transient Codex chat state are separated
The system MUST durably retain accepted user messages, approval requests and resolutions, key lifecycle events, final assistant results, and terminal outcomes according to existing history semantics. Transient reasoning and delta activity MAY be delivered without durable recovery and MAY be lost across process failure, but such loss MUST NOT remove, duplicate, reorder, or falsify durable state.

#### Scenario: Process restarts after a completed turn
- **WHEN** the application restarts after a Codex turn has reached a terminal outcome
- **THEN** the accepted user message, relevant approval state, final result, and terminal outcome remain recoverable through the existing history surfaces
- **AND** recovery does not depend on replaying transient reasoning or delta fragments

#### Scenario: Process fails with transient fragments pending
- **WHEN** the process fails before buffered reasoning or delta activity is persisted
- **THEN** those transient fragments may be absent after restart
- **AND** no durable message or key lifecycle state is reported as committed unless its existing durability requirement was satisfied

#### Scenario: Transient persistence is slow or unavailable
- **WHEN** optional transient-activity persistence is delayed or fails
- **THEN** live delivery and durable key-state handling continue independently within bounded capacity
- **AND** the failure is observable without logging message, reasoning, credential, or approval contents

### Requirement: Fast-path latency is attributable and regression-testable
The system SHALL expose bounded, content-free timing evidence for accepted submission, working feedback, Provider request, first native event, first displayable fragment, Provider terminal state, durable commit, and client delivery where those stages apply. Performance claims MUST include a reproducible pre-change baseline and post-change result for the same fixture.

#### Scenario: Produce warm-chat performance evidence
- **WHEN** the Codex fast-path acceptance fixture runs before and after the implementation
- **THEN** it records stage latencies, p50, p95, sample count, errors, and concurrency conditions
- **AND** it distinguishes Virtual Office delay from observed Provider first-text delay

#### Scenario: Timing evidence is recorded
- **WHEN** stage-level measurements or diagnostics are emitted
- **THEN** they contain identifiers or digests sufficient to correlate stages
- **AND** they do not contain prompts, response text, reasoning text, credentials, approval contents, or unrestricted filesystem paths

#### Scenario: Improvement cannot be reproduced
- **WHEN** the post-change fixture cannot distinguish the expected improvement from noise or changed Provider behavior
- **THEN** the optimization is not claimed as verified
- **AND** the related behavior remains subject to compatibility and correctness gates

### Requirement: Existing Codex chat contracts remain compatible
The fast path MUST preserve public Codex chat routes, accepted request and response fields, critical event names and meanings, final reply content, conversation and thread mapping, history behavior, approval decisions, cancellation, error semantics, and terminal outcomes. Cold start, new-thread chat, history navigation, and unsupported Provider behavior SHALL not regress from the recorded baseline.

#### Scenario: Existing Codex chat regressions run
- **WHEN** the focused API, conversation, thread-resume, SSE, history, approval, cancellation, and terminal-state suites run after the change
- **THEN** their previously supported observable behavior remains valid

#### Scenario: Cold or new-thread chat is used
- **WHEN** Codex is not warm or the conversation has no resumable thread
- **THEN** the request follows a supported cold-start or new-thread path
- **AND** its correctness and measured latency do not regress beyond the accepted baseline tolerance

#### Scenario: Another Provider or Agent workflow is invoked
- **WHEN** Claude Code, Hermes, OpenClaw, Project execution, Meeting execution, or a Feishu entry point invokes an Agent
- **THEN** this change does not require that path to adopt the Codex chat SLO or transient-event policy
- **AND** shared infrastructure changes preserve that path's existing behavior
