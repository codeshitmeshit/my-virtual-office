## ADDED Requirements

### Requirement: Project-scoped workflow chat stream
The system SHALL expose a Project Execution chat event stream whose Provider, Agent, conversation, project, task, attempt, and review scope is resolved by the server from the selected project. Client-controlled identifiers MUST NOT broaden or replace that resolved scope.

#### Scenario: Active attempt opens a stream
- **WHEN** a user opens Project Execution chat for a project with an active attempt
- **THEN** the stream emits only events belonging to the server-resolved Provider, Agent, conversation, task, and attempt
- **AND** events from other projects, attempts, Agents, or conversations are excluded

#### Scenario: No execution scope exists
- **WHEN** a project has no eligible task or attempt scope
- **THEN** the endpoint returns a compatible empty or inactive stream result
- **AND** it does not fall back to an Agent-global or prior-attempt conversation

### Requirement: Canonical live projection
Project workflow chat events SHALL carry bounded, sanitized canonical `timelineItem` values produced by the shared conversation timeline authority. The project client MUST NOT independently derive canonical identity, order, lifecycle, reasoning accumulation, tool transitions, or deduplication from Provider-native payloads.

#### Scenario: Provider emits active progress
- **WHEN** Codex, Claude Code, Hermes, or OpenClaw emits eligible activity for the active attempt
- **THEN** Project Execution receives the same canonical identity, content, reasoning, tool, lifecycle, and ordering semantics as standard chat for the overlapping scope
- **AND** the existing project presentation may render that item with its current visual components

#### Scenario: Live item becomes durable
- **WHEN** a streamed item later appears in the workflow-chat snapshot or Provider history
- **THEN** reconciliation settles or updates the existing canonical item
- **AND** it does not append a duplicate visible message, reasoning item, or tool

### Requirement: Snapshot-first recovery and terminal settlement
The existing workflow-chat snapshot SHALL remain the authoritative durable recovery mechanism. The client SHALL reconcile an initial snapshot with buffered live events and SHALL refresh the snapshot after terminal events or when replay cannot guarantee continuity.

#### Scenario: Event arrives during initial snapshot
- **WHEN** a matching live event arrives while the initial workflow-chat snapshot is in flight
- **THEN** the event and snapshot are reconciled deterministically by canonical identity and version
- **AND** neither arrival order loses or duplicates the item

#### Scenario: Run reaches a terminal state
- **WHEN** the stream reports completion, failure, or cancellation
- **THEN** the client performs a bounded authoritative snapshot refresh
- **AND** durable terminal messages and Provider history settle the visible timeline

#### Scenario: Application restarts
- **WHEN** application restart discards permitted transient events
- **THEN** the client replaces from the durable workflow-chat snapshot and resumes streaming from the available journal boundary
- **AND** missing non-durable activity is not fabricated

### Requirement: Replay, reconnect, and polling fallback
The stream SHALL support bounded event-ID replay and heartbeat behavior. Disconnects, cursor gaps, unsupported streaming, or repeated transport failure MUST activate snapshot recovery and bounded polling fallback without interrupting Provider execution.

#### Scenario: Short network interruption
- **WHEN** EventSource reconnects with a retained last event ID
- **THEN** matching retained events are replayed idempotently
- **AND** the visible timeline remains ordered and duplicate-free

#### Scenario: Replay boundary is unavailable
- **WHEN** the requested cursor predates retained events or cannot be recovered after restart
- **THEN** the server or client marks snapshot recovery as required
- **AND** the client refreshes the authoritative snapshot before resuming live reconciliation

#### Scenario: Stream remains unavailable
- **WHEN** the project stream cannot remain connected
- **THEN** the client uses the existing bounded polling path until streaming recovers
- **AND** chat history remains readable with no Provider launch or history mutation

### Requirement: Scope-change isolation
Every project workflow stream SHALL carry an opaque resolved-scope version. A task, attempt, review, Provider, Agent, or conversation change MUST invalidate the prior stream, and stale events MUST NOT update the new visible scope.

#### Scenario: Project advances to another attempt
- **WHEN** the selected project moves from one attempt to another while the stream is connected
- **THEN** the old stream is invalidated or closed and the client loads a snapshot for the new scope
- **AND** queued or replayed events from the old scope are ignored

#### Scenario: User switches projects
- **WHEN** the project view changes or closes
- **THEN** the prior project's stream is closed
- **AND** subsequent events cannot mutate the newly selected project chat

### Requirement: Bounded and content-safe streaming
Project workflow streaming MUST reuse canonical item bounds, Provider event retention, public-payload sanitization, heartbeat and disconnect cleanup. It MUST NOT expose secrets, authorization headers, unrestricted paths, raw Provider transcripts, or unbounded nested payloads in events or diagnostics.

#### Scenario: Malformed or sensitive Provider event arrives
- **WHEN** an eligible source event contains malformed, oversized, deeply nested, secret-bearing, header-bearing, token-bearing, or unrestricted-path values
- **THEN** the public event is rejected, bounded, allowlisted, or redacted according to existing public-data policy
- **AND** healthy events and other Provider streams remain available

#### Scenario: Client disconnects
- **WHEN** a project view closes, becomes ineligible, or the connection breaks
- **THEN** the server releases the stream without retaining unbounded client state
- **AND** Provider execution continues independently

### Requirement: Compatible UI and measurable improvement
The change SHALL preserve the existing Project Execution chat presentation and workflow-chat snapshot contract while reducing active-update latency and repeated unchanged history reads. Acceptance MUST cover all four Providers, browser behavior, reconnect, refresh, scope switching, and fallback recovery.

#### Scenario: Healthy stream is active
- **WHEN** an eligible Provider event is published while Project Execution chat is open
- **THEN** it becomes available without waiting for the 2.5-second primary polling interval
- **AND** unchanged snapshot reads occur less frequently than the characterized polling baseline

#### Scenario: Existing presentation renders streamed data
- **WHEN** canonical streamed messages, reasoning, or tools are rendered
- **THEN** existing labels, expansion behavior, truncation, scrolling, and layout remain compatible
- **AND** no visual redesign is required
