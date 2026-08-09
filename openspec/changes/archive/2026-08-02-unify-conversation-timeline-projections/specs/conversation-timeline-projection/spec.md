## ADDED Requirements

### Requirement: One authoritative conversation timeline per scope
The system SHALL derive displayable conversation items for standard chat and Project Execution chat from one provider-neutral timeline authority. For the same Provider, Agent, conversation, run, and overlapping requested window, both surfaces MUST receive the same canonical item identities, content, reasoning, tool activity, lifecycle state, and chronological order, while each surface MAY render those items differently.

#### Scenario: Same active run is viewed from both surfaces
- **WHEN** standard chat and Project Execution chat request the same active run and conversation scope
- **THEN** every canonical item present in both requested windows has the same identity, content, reasoning, tools, state, and relative order
- **AND** neither surface applies an independent provider-specific interpretation that changes those semantics

#### Scenario: Surfaces request different bounded windows
- **WHEN** standard chat and Project Execution chat request different page sizes or time windows for the same conversation
- **THEN** items in the overlapping portion remain semantically identical and consistently ordered
- **AND** the smaller window does not cause the shared timeline authority to mutate or discard the larger conversation state

### Requirement: Complete supported-provider coverage
The shared timeline authority MUST support Codex, Claude Code, Hermes, and OpenClaw for both standard chat and Project Execution chat. Provider-specific readers SHALL normalize native history, progress, and activity into the common timeline contract instead of requiring either consuming surface to parse a provider-native transcript or invent provider-specific behavior.

#### Scenario: Each supported Provider executes a project attempt
- **WHEN** a Codex, Claude Code, Hermes, or OpenClaw Agent produces displayable activity for a Project Execution attempt
- **THEN** Project Execution chat reads the attempt-scoped canonical timeline for that Provider
- **AND** the equivalent standard-chat consumer can interpret the same canonical item semantics without a separate Provider-specific projection

#### Scenario: Claude Code attempt history is requested
- **WHEN** Project Execution chat requests a Claude Code attempt that has conversation-scoped provider history
- **THEN** the system returns that Claude Code conversation history and eligible live progress
- **AND** it does not fall back to an unrelated OpenClaw session lookup

### Requirement: Strict conversation and attempt isolation
Timeline resolution MUST bind Provider kind, Agent or profile, conversation identity, and any Project Execution project, task, attempt, or review identity before reading or merging data. Missing, stale, or foreign identifiers MUST NOT broaden the lookup to an Agent-global conversation or another project execution.

#### Scenario: Two attempts use the same Agent
- **WHEN** two project attempts use the same Agent with different attempt conversation identities
- **THEN** each timeline contains only the messages, reasoning, tools, and progress associated with its own attempt
- **AND** Agent-global or prior-attempt history is not merged into either timeline

#### Scenario: Requested identity does not belong to the selected scope
- **WHEN** a timeline request contains a conversation, task, attempt, or Provider identity that does not belong to the selected scope
- **THEN** the system rejects the request or returns an empty compatible result
- **AND** it does not expose or mutate another scope's timeline

### Requirement: Deterministic live and durable reconciliation
The timeline authority SHALL reconcile eligible provider live activity, transient progress, durable provider history, and office-owned communication history into one deterministic view. A live item that later appears in durable history MUST update or settle the same canonical item rather than producing a duplicate, and a completed durable result MUST remain recoverable after an ordinary page refresh or application restart according to existing persistence guarantees.

#### Scenario: Live progress settles into durable history
- **WHEN** a running item is delivered from live progress and the corresponding completed item later appears in durable history
- **THEN** the canonical timeline transitions that item to its terminal state without duplicating its visible content
- **AND** both consuming surfaces observe the same settled result

#### Scenario: Completed conversation is refreshed
- **WHEN** a user refreshes either surface after a completed turn has been durably recorded
- **THEN** the recovered canonical timeline preserves the completed content, reasoning made durable by the Provider contract, tools, state, and order
- **AND** it does not reclassify completed items as live

#### Scenario: Non-durable transient activity is lost during failure
- **WHEN** a process failure discards transient activity that the existing Provider contract does not guarantee to persist
- **THEN** the timeline does not fabricate or reconstruct that missing activity
- **AND** durable messages and terminal outcomes remain accurate and consistently recoverable

### Requirement: Stable identity, ordering, and deduplication
Canonical timeline items SHALL have stable identities within their conversation scope and SHALL be ordered deterministically using Provider sequence and lifecycle relationships where available, with normalized timestamps used only as a compatible fallback. Repeated events, overlapping history sources, polling refreshes, and reconnect replay MUST NOT create duplicate canonical items or reverse previously established order.

#### Scenario: Provider event is replayed
- **WHEN** polling, SSE reconnect, or history refresh delivers an event that the timeline has already accepted
- **THEN** the existing canonical item is retained or updated idempotently
- **AND** no duplicate message, reasoning item, or tool activity is produced

#### Scenario: Multiple sources overlap
- **WHEN** provider history and office communication history represent the same visible turn or activity
- **THEN** the timeline reconciles the overlapping records using stable scope and identity evidence
- **AND** preserves one deterministic chronological representation with correct sender attribution

#### Scenario: Timestamps are equal or incomplete
- **WHEN** related events have equal, missing, or low-resolution timestamps but provide Provider ordering or lifecycle identity
- **THEN** the timeline preserves their Provider-established order
- **AND** repeated reads return the same order

### Requirement: Accurate reasoning semantics without fabrication
The timeline SHALL expose only reasoning or thinking content supplied by the selected Provider and allowed by its existing visibility policy. It MUST filter transport placeholders and status-only text, preserve Provider-supported replacement and section-boundary semantics, normalize reasoning state to a common lifecycle, and MUST NOT synthesize reasoning when the Provider supplies only a run status.

#### Scenario: Provider supplies incremental reasoning
- **WHEN** a Provider supplies reasoning deltas, replacement snapshots, boundaries, and a terminal state
- **THEN** the canonical reasoning item applies those semantics exactly once and reaches the corresponding normalized terminal state
- **AND** both surfaces receive the same final reasoning text and state

#### Scenario: Provider supplies only execution state
- **WHEN** a Provider reports that a run is starting or active without providing displayable reasoning content
- **THEN** the timeline may expose the truthful run state
- **AND** it does not create reasoning text that the Provider did not supply

#### Scenario: Completed Hermes history is recovered
- **WHEN** a completed Hermes message with visible reasoning is loaded from durable history
- **THEN** its canonical reasoning state is terminal rather than live
- **AND** the recovered reasoning content matches the Provider history after visibility filtering

#### Scenario: Placeholder thinking is received
- **WHEN** a Provider emits a configured status placeholder such as a completion label or waiting message
- **THEN** the placeholder is not exposed as reasoning content
- **AND** the actual lifecycle state remains available independently

### Requirement: Consistent message and tool semantics
The shared timeline SHALL normalize user and assistant content, sender attribution, attachments or media, tool identity, tool arguments, tool result, tool error, and tool lifecycle without allowing standard chat and Project Execution chat to derive conflicting meanings from the same Provider record. Provider-native tool payloads and unsupported content MUST remain bounded and sanitized according to existing public-data policies.

#### Scenario: Tool progresses during a turn
- **WHEN** a Provider reports a tool start followed by completion or failure
- **THEN** the canonical tool item retains one stable identity and transitions to the accurate terminal state
- **AND** the associated message and reasoning order is the same for both surfaces

#### Scenario: OpenClaw transcript contains supported structured blocks
- **WHEN** an OpenClaw session contains supported text, media, tool, result, or Provider-supplied reasoning blocks
- **THEN** the shared Provider reader normalizes each supported block consistently for both surfaces
- **AND** unsupported or sensitive native fields are not exposed as invented display content

### Requirement: Compatible public surfaces and independent presentation
The change MUST preserve existing public route paths, accepted request fields, compatible response fields, Provider execution contracts, and existing standard-chat and Project Execution entry points. It SHALL NOT require the two surfaces to share visual components, layout, truncation presentation, interaction design, or styling, provided presentation does not alter canonical timeline meaning.

#### Scenario: Existing client requests workflow chat
- **WHEN** an existing project client calls the supported workflow-chat route
- **THEN** it receives a backward-compatible response containing items derived from the canonical timeline
- **AND** no Provider-native storage or protocol detail becomes a client prerequisite

#### Scenario: Surfaces render canonical reasoning differently
- **WHEN** standard chat and Project Execution chat choose different visual components for the same canonical reasoning item
- **THEN** both presentations retain the same underlying text, lifecycle meaning, identity, and order
- **AND** visual differences alone do not require duplicate Provider projection logic

### Requirement: Bounded and failure-isolated timeline reads
Timeline reads and reconciliation MUST remain bounded by requested limits and existing retention policies. Failure, malformed data, or unavailable history from one Provider or one conversation MUST NOT corrupt another timeline, broaden its scope, fabricate success, or disable healthy Provider timelines.

#### Scenario: Provider history is malformed or unavailable
- **WHEN** one scoped Provider history source cannot be read or contains malformed records
- **THEN** the affected timeline returns a compatible empty, partial, or error result according to the existing contract
- **AND** unrelated Providers and conversations remain available and unmodified

#### Scenario: Repeated project polling reads an unchanged timeline
- **WHEN** Project Execution repeatedly requests an unchanged bounded timeline
- **THEN** results remain stable and bounded without accumulating duplicate state
- **AND** the read does not trigger additional Provider execution or mutate durable conversation history

### Requirement: Verified in-scope defect correction
A defect discovered while migrating conversation timeline behavior MAY be corrected only when it is reproducible, lies within the migrated timeline paths, and the expected result follows the confirmed consistency, accuracy, isolation, visibility, compatibility, or non-fabrication requirements. Every such correction MUST have a failing-before regression scenario and MUST be documented as an intentional behavior correction rather than an incidental refactor effect.

#### Scenario: Reproducible timeline defect is found
- **WHEN** migration exposes a reproducible defect in Provider history selection, live reconciliation, status normalization, ordering, deduplication, isolation, or visibility
- **THEN** the defect may be fixed within this change with a regression test proving the expected behavior
- **AND** the relevant OpenSpec artifact is updated before implementation if the correction changes confirmed behavior

#### Scenario: Suspected defect is ambiguous or unrelated
- **WHEN** an observation cannot be reproduced, requires a new product policy, or lies outside the migrated timeline paths
- **THEN** it is not changed under this change
- **AND** work pauses for specification clarification if the issue blocks the authorized migration

### Requirement: Cross-surface acceptance evidence
The change MUST provide repeatable acceptance evidence for Codex, Claude Code, Hermes, and OpenClaw covering active progress, completed history, refresh or restart recovery where guaranteed, ordering, deduplication, state normalization, unavailable reasoning, and scope isolation. The evidence SHALL compare standard-chat and Project Execution projections at the canonical-data level rather than requiring pixel-identical UI.

#### Scenario: Provider consistency matrix is verified
- **WHEN** the acceptance suite runs fixed live and durable fixtures for all four supported Providers
- **THEN** overlapping canonical items returned to both surfaces match in identity, content, reasoning, tools, state, and order
- **AND** any Provider-specific absence of reasoning is represented consistently without fabricated content

#### Scenario: Existing compatibility suites run
- **WHEN** timeline, chat history, provider event, Project Execution, HTTP, SSE, and session-isolation regression suites execute
- **THEN** previously correct behavior remains valid except for intentional defect corrections documented by this change
