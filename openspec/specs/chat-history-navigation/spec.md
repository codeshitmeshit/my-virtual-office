# Chat History Navigation Specification

## Purpose

Define the performance, consistency, and compatibility requirements for paged, cached, and bounded chat history navigation.

## Requirements

### Requirement: Cached conversations switch without waiting for the network
The chat UI SHALL keep a bounded, runtime conversation cache keyed by provider kind, agent identifier, and conversation identifier. When a cached conversation is selected, the UI SHALL present its cached recent history before any history refresh completes and SHALL preserve the cached conversation's scroll state.

#### Scenario: Return to a previously visited conversation
- **WHEN** a user selects a conversation that has valid cached history
- **THEN** the cached recent history is shown without waiting for a history HTTP response
- **AND** the conversation is refreshed in the background without first clearing the cached messages

#### Scenario: Reopen an unchanged chat panel
- **WHEN** a user closes and reopens a chat panel whose selected conversation and cache are still valid
- **THEN** the existing cached history and scroll state are restored without a full blocking history reload

#### Scenario: Conversation cache remains bounded
- **WHEN** the user visits more conversations than the configured cache capacity
- **THEN** the least recently used inactive conversation state is evicted
- **AND** active conversations are not evicted

### Requirement: Cold history loads the newest page first
The system SHALL expose a provider-neutral paged history response that merges the sources needed for the selected conversation. The initial request SHALL return at most 50 newest displayable messages in chronological order and SHALL include an opaque cursor and a `hasMore` indication when older history exists.

#### Scenario: Open an uncached long conversation
- **WHEN** a user opens an uncached conversation containing more than 50 displayable messages
- **THEN** the first response contains no more than the newest 50 messages in chronological order
- **AND** the UI becomes usable without fetching or rendering the complete conversation
- **AND** the response indicates that older history can be loaded

#### Scenario: Open a short conversation
- **WHEN** a conversation contains 50 or fewer displayable messages
- **THEN** the response contains all available messages in chronological order
- **AND** `hasMore` is false

### Requirement: Older history loads incrementally with a stable viewport
The chat UI SHALL request older pages only when the user approaches the top of the rendered history. Prepending an older page SHALL preserve the message and offset currently visible to the user, and repeated or overlapping pages SHALL not create duplicate messages.

#### Scenario: Load the previous page
- **WHEN** the user scrolls near the top and older history is available
- **THEN** one older page is requested using the current opaque cursor
- **AND** the returned messages are prepended in chronological order
- **AND** the previously visible message remains at the same visual offset

#### Scenario: Prevent concurrent older-page requests
- **WHEN** an older-page request is already in flight and the top threshold is crossed again
- **THEN** the UI does not start another request for the same cursor

#### Scenario: Merge an overlapping page
- **WHEN** an older page contains a message already present in the conversation cache
- **THEN** the existing message is updated or retained by stable identity
- **AND** no duplicate bubble is rendered

### Requirement: Mounted history DOM remains bounded
The chat UI SHALL keep no more than 160 historical message root elements mounted for a conversation, excluding transient typing and live-activity elements. Messages removed from the DOM SHALL remain available in the conversation model so they can be restored when the user navigates back toward them.

#### Scenario: Navigate a one-thousand-message conversation
- **WHEN** the user repeatedly loads and navigates through a conversation with at least 1,000 messages
- **THEN** no more than 160 historical message root elements are mounted at one time
- **AND** the user can still reach both older and newer cached messages

#### Scenario: Windowed messages include rich content
- **WHEN** a message containing Markdown, attachments, tool cards, thinking details, or approval state leaves and later re-enters the mounted window
- **THEN** its visible content and interactive state are restored consistently

### Requirement: Stable message rendering is reusable
The chat UI SHALL reuse rendered output for a message whose stable identity and render-affecting content have not changed. Changed content SHALL invalidate the reusable output, and transient running content SHALL not be treated as immutable.

#### Scenario: Render an unchanged cached message
- **WHEN** an unchanged stable message is mounted again during a conversation switch or window movement
- **THEN** its cached sanitized rendering is reused instead of repeating full Markdown parsing

#### Scenario: Update a previously rendered message
- **WHEN** a message with the same stable identity receives changed text, tools, thinking, approval, attachments, or status
- **THEN** the cached rendering is invalidated and the updated content is rendered

### Requirement: Refresh and live events reconcile into one conversation state
History refreshes and provider SSE events SHALL merge into the same keyed conversation model using stable message identity. A refresh SHALL not clear a valid cached view, and an event or response for a different or previously selected conversation SHALL not mutate the current conversation.

#### Scenario: Receive a live event during background refresh
- **WHEN** a matching SSE message or tool event arrives while cached history is being refreshed
- **THEN** both sources are reconciled without duplicate messages or loss of the live update

#### Scenario: Ignore a stale history response
- **WHEN** the user switches conversations before an earlier history request completes
- **THEN** the earlier response does not replace or append to the newly selected conversation

#### Scenario: Ignore a mismatched live event
- **WHEN** an SSE event does not match the current provider, agent, and conversation key
- **THEN** it does not change the visible conversation
- **AND** it may update only the matching inactive cached conversation

### Requirement: Supported providers retain history behavior
The optimized history flow SHALL support Codex, Hermes, Claude Code, and Gateway conversations and SHALL preserve chronological display, sender attribution, Markdown, attachments, tool cards, thinking, approval state, Feishu-visible messages, and recovered final responses.

#### Scenario: Load each supported provider
- **WHEN** history is opened for a Codex, Hermes, Claude Code, or Gateway conversation
- **THEN** the provider's displayable messages use the same paged cache and bounded-rendering behavior
- **AND** provider-specific rich message content remains available

#### Scenario: Reconcile cross-platform communication history
- **WHEN** provider history overlaps with visible agent-platform or Feishu communication history
- **THEN** the merged result preserves chronological order and sender context
- **AND** duplicate representations of the same communication are not shown

### Requirement: History navigation has measurable performance acceptance
The implementation SHALL expose deterministic test seams or measurements for cache hits, page size, mounted history count, request cancellation, and render completion. In a controlled browser fixture with at least 1,000 historical messages, a cached switch SHALL show cached content before network completion and SHALL not produce a history-rendering long task of 50 milliseconds or more.

#### Scenario: Measure a cached long-history switch
- **WHEN** the browser acceptance fixture switches to a cached conversation containing at least 1,000 messages while its refresh response is delayed
- **THEN** cached message content is visible before the delayed response is released
- **AND** the mounted historical message count is no more than 160
- **AND** no measured history-rendering task lasts 50 milliseconds or more

#### Scenario: Verify rapid switching isolation
- **WHEN** the fixture rapidly switches across at least three conversations and resolves history responses out of order
- **THEN** only the selected conversation is visible
- **AND** each response is retained only in its matching cache entry
