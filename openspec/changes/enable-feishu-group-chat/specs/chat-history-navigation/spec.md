## MODIFIED Requirements

### Requirement: Supported providers retain history behavior
The optimized history flow SHALL support Codex, Hermes, Claude Code, and Gateway conversations and SHALL preserve chronological display, sender attribution, Markdown, attachments, tool cards, thinking, approval state, visible Feishu private-chat messages, and recovered final responses. Feishu group-chat requests, Agent outcomes, and delivery records MUST NOT be included in normalized VO chat history, conversation caches, or Feishu SSE-driven chat refreshes.

#### Scenario: Load each supported provider
- **WHEN** history is opened for a Codex, Hermes, Claude Code, or Gateway conversation
- **THEN** the provider's displayable messages use the same paged cache and bounded-rendering behavior
- **AND** provider-specific rich message content remains available

#### Scenario: Reconcile cross-platform communication history
- **WHEN** provider history overlaps with visible agent-platform or Feishu private-chat communication history
- **THEN** the merged result preserves chronological order and sender context
- **AND** duplicate representations of the same communication are not shown

#### Scenario: Group turn is persisted outside VO chat history
- **WHEN** VO persists an accepted Feishu group request, Agent outcome, or delivery record
- **THEN** normalized VO chat history SHALL exclude that record from both the active and inactive conversation models
- **AND** the existing private-chat cross-conversation merge SHALL remain unchanged

#### Scenario: Group activity occurs while the VO chat window is open
- **WHEN** a Feishu group turn is accepted, completed, or delivered while a representative Agent chat window is open
- **THEN** the group activity SHALL NOT publish a chat-refresh event to the Feishu SSE surface
- **AND** it SHALL NOT appear in the VO chat window after initial load, refresh, pagination, or SSE reconnect
