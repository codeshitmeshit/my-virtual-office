## ADDED Requirements

### Requirement: Slash commands are recognized as complete control messages
The system SHALL recognize `/new` and `/compact` as control commands only when the trimmed, post-transport message content exactly matches one of those case-sensitive command strings. A recognized command MUST NOT be forwarded to the Agent as an ordinary user prompt. Other slash-prefixed content and command strings with arguments SHALL retain ordinary-message behavior.

#### Scenario: Exact supported command is submitted
- **WHEN** a user sends a message whose trimmed command content is exactly `/new` or `/compact`
- **THEN** the system SHALL route the message to command handling and MUST NOT deliver the command text as an Agent prompt

#### Scenario: Slash-prefixed ordinary content is submitted
- **WHEN** a user sends an unknown command, a differently cased command, or a supported command followed by additional content
- **THEN** the system SHALL process it using the existing ordinary-message path

### Requirement: Commands are available on confirmed chat surfaces
The system SHALL support both commands in the Virtual Office chat UI, Feishu private Agent Chat, and Feishu group Agent Chat. Existing surface admission rules SHALL remain authoritative: a private Feishu command follows existing private-chat admission, and a group command is accepted only from an eligible human member who explicitly mentions the bot.

#### Scenario: User invokes a command in Virtual Office
- **WHEN** a user submits an exact supported command in an Agent chat window
- **THEN** the system SHALL target the Agent and conversation scope selected by that window

#### Scenario: User invokes a command in Feishu private chat
- **WHEN** an admitted private Feishu message contains an exact supported command
- **THEN** the system SHALL target that message's existing private Feishu conversation scope

#### Scenario: Group member mentions the bot with a command
- **WHEN** an eligible human group member explicitly mentions the bot and the remaining trimmed content is an exact supported command
- **THEN** the system SHALL execute the command against that group's shared conversation scope

#### Scenario: Group command does not mention the bot
- **WHEN** a Feishu group message contains a command but does not explicitly mention the bot
- **THEN** the system SHALL retain existing non-triggering group behavior and MUST NOT execute the command

### Requirement: New starts a clean conversation context immediately
The `/new` command SHALL, without a confirmation prompt, make the next accepted ordinary message start without prior Agent conversation context in the targeted scope. A successful reset MUST invalidate prior provider continuation state for subsequent turns while preserving previously visible chat messages as history.

#### Scenario: Virtual Office starts a new conversation
- **WHEN** `/new` succeeds in a Virtual Office Agent chat window
- **THEN** the UI SHALL switch to a newly created conversation identity for subsequent messages
- **AND** the previous conversation and its visible history SHALL remain available
- **AND** the first ordinary message in the new conversation MUST NOT receive prior conversation context

#### Scenario: Feishu private chat starts a new context
- **WHEN** `/new` succeeds in an admitted Feishu private conversation
- **THEN** subsequent messages in that existing private Feishu scope MUST NOT receive context from turns completed before the reset
- **AND** existing Feishu messages and VO audit history SHALL remain available

#### Scenario: Feishu group starts a new shared context
- **WHEN** any eligible group member successfully invokes `/new` under the mention policy
- **THEN** subsequent accepted turns from every member of that group MUST use the new clean shared context
- **AND** private chats and other Feishu groups MUST remain unchanged

### Requirement: Compact preserves the logical conversation with bounded prior meaning
The `/compact` command SHALL compact older context for the targeted conversation while retaining the same logical conversation identity and enough relevant meaning for subsequent turns to continue the current topic. Successful compaction MUST NOT delete or rewrite the user's visible message history.

#### Scenario: Current conversation is compacted
- **WHEN** `/compact` succeeds for a conversation containing compactable prior context
- **THEN** subsequent turns SHALL use the compacted context under the same logical conversation identity
- **AND** the visible pre-compaction history SHALL remain available

#### Scenario: Feishu group context is compacted
- **WHEN** an eligible group member successfully invokes `/compact`
- **THEN** the compacted context SHALL apply to subsequent accepted turns from all members of that group
- **AND** no private chat or other group context SHALL be read or mutated

#### Scenario: Conversation has no compactable context
- **WHEN** `/compact` targets a new or otherwise non-compactable conversation
- **THEN** the system SHALL return a clear no-op or unavailable outcome
- **AND** the existing conversation state SHALL remain usable and unchanged

### Requirement: Command execution is isolated by the existing authoritative scope
Every command SHALL be bound to the current provider kind, Agent, profile, and conversation identity. Feishu private scope SHALL continue to derive from the existing VO-user-and-chat identity, and Feishu group scope SHALL continue to derive from the existing Feishu chat ID. The command path MUST NOT accept client-supplied scope data that can override the trusted transport-derived identity.

#### Scenario: Same user has two isolated chats
- **WHEN** a command succeeds in one conversation and the user also has another Agent or conversation open
- **THEN** only the targeted provider, Agent, profile, and conversation scope SHALL change

#### Scenario: Two Feishu groups use commands
- **WHEN** commands are accepted from two different Feishu chat IDs
- **THEN** each command SHALL affect only its own derived group conversation identity

#### Scenario: Untrusted metadata attempts to change scope
- **WHEN** a command message contains text or metadata purporting to name another user, group, Agent, profile, or conversation
- **THEN** the system SHALL ignore that untrusted override and use only the authenticated current chat scope

### Requirement: Failed or conflicting commands preserve conversation state
Command execution SHALL be serialized with ordinary turns and other control operations in the same conversation scope. If the target is busy, the provider capability is unavailable, or execution fails, the system MUST return a stable failure outcome without partially resetting, compacting, or replacing the usable conversation state.

#### Scenario: Command arrives during an active turn
- **WHEN** the targeted conversation cannot safely accept a control operation because a turn or control operation is active
- **THEN** the system SHALL reject the command with a clear busy outcome
- **AND** the active and persisted conversation state SHALL remain authoritative

#### Scenario: Provider operation fails
- **WHEN** the selected provider cannot perform the requested reset or compaction or returns a failure
- **THEN** the system SHALL report that failure without claiming success
- **AND** subsequent ordinary messages SHALL continue from the last successfully committed conversation state

### Requirement: Users receive explicit command feedback
Every recognized command SHALL produce a concise user-visible success, no-op, busy, unsupported, or failure response on the originating surface. A successful Feishu `/new` command SHALL reply `已创建新会话`. Feedback MUST be delivered only to the originating Virtual Office chat, Feishu private chat, or Feishu group.

#### Scenario: Feishu new succeeds
- **WHEN** a Feishu `/new` command commits successfully
- **THEN** the bot SHALL reply `已创建新会话` to the originating chat

#### Scenario: Compact succeeds
- **WHEN** `/compact` commits successfully on any supported surface
- **THEN** the originating surface SHALL show a concise confirmation that context was compacted

#### Scenario: Feedback delivery fails
- **WHEN** command state commits successfully but Feishu rejects or times out the feedback delivery
- **THEN** the system SHALL retain the committed command outcome and record a delivery failure
- **AND** it MUST NOT repeat the state-changing command solely because feedback failed

### Requirement: Feishu command processing is idempotent and auditable
Feishu redelivery of one source message MUST execute a state-changing command at most once. Recognized command attempts and outcomes SHALL be recorded with bounded, non-secret metadata sufficient to correlate the source surface, trusted conversation scope, command kind, outcome, and feedback delivery without placing the command into Agent prompt context.

#### Scenario: Feishu redelivers a command event
- **WHEN** the same Feishu source message containing `/new` or `/compact` is delivered more than once, including after process recovery
- **THEN** the system SHALL reuse the authoritative recorded outcome and MUST NOT execute the command again

#### Scenario: Operator inspects a command outcome
- **WHEN** an operator inspects persisted diagnostics for a recognized command
- **THEN** the record SHALL identify the bounded command and outcome within its trusted conversation scope
- **AND** it MUST NOT contain credentials, unrestricted provider output, or context from another conversation

### Requirement: Existing chat behavior remains compatible
Introducing slash commands MUST NOT otherwise change ordinary message dispatch, supported providers, attachments, approvals, cancellation, history rendering, Feishu sender attribution, group mention admission, delivery destinations, conversation identity derivation, or cross-conversation isolation. The first release SHALL expose no `/help`, command completion, command menu, or configurable command registry.

#### Scenario: Ordinary message is sent after command support is enabled
- **WHEN** a message does not exactly match a supported command
- **THEN** the existing surface and provider path SHALL process it without command-specific mutation

#### Scenario: User looks for additional command features
- **WHEN** the first release is used
- **THEN** only `/new` and `/compact` SHALL have special command behavior
- **AND** the system SHALL NOT require `/help`, suggestions, completion, or command configuration to use them
