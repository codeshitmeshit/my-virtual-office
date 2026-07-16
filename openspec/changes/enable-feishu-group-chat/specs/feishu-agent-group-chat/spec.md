## ADDED Requirements

### Requirement: Intentional group membership establishes group trust
The Feishu Agent Chat channel SHALL accept supported group interactions from a group in which the Chat App bot is a member without requiring a separate VO group allowlist, approval, or sender binding. Any human member of that group SHALL be eligible to invoke the representative Agent under the mention policy.

#### Scenario: Unbound group member invokes the bot
- **WHEN** a human member of a group containing the bot sends a supported message that explicitly mentions the bot
- **THEN** VO SHALL accept the interaction without requiring that sender to be bound to a VO user

#### Scenario: Bot is not a member of the group
- **WHEN** a group message cannot be delivered as an event from a group containing the bot
- **THEN** VO SHALL NOT create an Agent turn through another group's trust or conversation state

### Requirement: Group interaction is mention-gated
VO SHALL dispatch a Feishu group message to the representative Agent only when the inbound event proves that the bot was explicitly mentioned. A group message that does not mention the bot MUST NOT create an Agent turn or enter the shared group conversation history.

#### Scenario: Bot is explicitly mentioned
- **WHEN** a supported group message includes an explicit mention of the bot
- **THEN** VO SHALL remove the addressing mention from the user prompt and dispatch the remaining content as one group Agent turn

#### Scenario: Ordinary group discussion does not invoke the bot
- **WHEN** a group member sends a message without explicitly mentioning the bot
- **THEN** VO SHALL NOT invoke the representative Agent, add the message to Agent conversation history, or send a group reply

#### Scenario: Another member is mentioned instead
- **WHEN** a group message mentions another member but does not explicitly mention the bot
- **THEN** VO SHALL treat the message as non-triggering group discussion

### Requirement: Each group has one shared isolated conversation
VO SHALL maintain one continuous Agent conversation identity per Feishu group chat ID. All accepted members' turns in that group SHALL share the same conversation context, while that context MUST remain isolated from private Feishu conversations, other Feishu groups, and unrelated provider conversations.

#### Scenario: Another member continues the group discussion
- **WHEN** one member completes an accepted group turn and a different member later mentions the bot in the same group
- **THEN** the later turn SHALL continue the same group conversation context

#### Scenario: Same member uses private chat
- **WHEN** a member of a group also sends the bot a private message
- **THEN** the private turn SHALL use a private conversation identity and MUST NOT read or mutate the group's conversation context

#### Scenario: Bot participates in multiple groups
- **WHEN** accepted messages arrive from two different Feishu group chat IDs
- **THEN** VO SHALL route them to distinct conversation identities with no history leakage between groups

### Requirement: Group turns preserve human sender attribution
Every accepted group turn SHALL preserve the triggering human member's available Feishu identity and SHALL provide unambiguous speaker attribution to the Agent and audit records without changing the group's shared conversation identity.

#### Scenario: Multiple members speak in one conversation
- **WHEN** different members invoke the bot in successive accepted turns in the same group
- **THEN** the Agent input and persisted records SHALL identify the speaker for each turn while retaining one shared group context

#### Scenario: Only a partial sender identity is available
- **WHEN** Feishu supplies only a subset of open ID, user ID, union ID, or display-name information
- **THEN** VO SHALL retain the available identity fields and SHALL NOT merge the sender with another member based only on missing fields

### Requirement: Group chat supports text and image turns
The group-chat scope SHALL accept text and image messages under the same content safety, attachment size, and local-path protections as existing private Feishu chat. Other group message types MUST remain unsupported unless a later confirmed specification adds them.

#### Scenario: Mentioned text message is accepted
- **WHEN** a group member explicitly mentions the bot in a text message containing a non-empty prompt
- **THEN** VO SHALL dispatch the readable prompt as a group Agent turn

#### Scenario: Mentioned image message is accepted
- **WHEN** a group member explicitly mentions the bot in an image message that satisfies attachment policy
- **THEN** VO SHALL download and dispatch the image through the existing protected attachment pipeline in the group's conversation

#### Scenario: Unsupported group content is received
- **WHEN** a mentioned group message contains a file or another unsupported content type
- **THEN** VO SHALL record a stable unsupported-message outcome and MUST NOT invoke the Agent

### Requirement: Group replies return only to the originating group
An Agent outcome for an accepted group turn SHALL be delivered to the originating Feishu group and associated with the triggering interaction when the Feishu reply contract permits. A delivery failure MUST NOT erase the Agent result, corrupt group context, or redirect the reply to private chat or another group.

#### Scenario: Group reply succeeds
- **WHEN** the Agent completes an accepted group turn and Feishu accepts the outbound operation
- **THEN** the reply SHALL appear in the originating group and VO SHALL record the returned Feishu message identity

#### Scenario: Group reply delivery fails
- **WHEN** Feishu rejects or times out the outbound group reply
- **THEN** VO SHALL preserve the Agent outcome and record a classified delivery failure without retrying into a different conversation

### Requirement: Group processing is durable, idempotent, and ordered
VO SHALL apply persistent source-message idempotency to group events and SHALL serialize accepted Agent turns within the same group conversation. Processing for different groups MAY proceed independently, but MUST NOT share ordering or idempotency state.

#### Scenario: Feishu redelivers a group event
- **WHEN** the same group source message is delivered more than once, including after a worker or server restart
- **THEN** VO SHALL create at most one Agent turn and at most one authoritative reply outcome for that source message

#### Scenario: Members invoke the bot rapidly in one group
- **WHEN** two accepted messages arrive close together from the same group
- **THEN** their Agent turns SHALL observe deterministic group-conversation order without overwriting either member's attribution

#### Scenario: Two groups invoke the bot concurrently
- **WHEN** accepted messages arrive concurrently from different group chat IDs
- **THEN** each message SHALL progress only within its own group conversation and failure in one group SHALL NOT block or contaminate the other

### Requirement: Existing private-chat behavior remains compatible
Enabling group chat MUST NOT change the existing private-message admission, sender binding policy, conversation identity, supported content, delivery behavior, normalized VO history visibility, or Feishu SSE refresh behavior.

#### Scenario: Private message is received after group chat is enabled
- **WHEN** the Chat App receives a supported `p2p` message
- **THEN** VO SHALL process and synchronize it according to the existing private-chat contract without consulting group membership or group history

#### Scenario: Group and private turns interleave
- **WHEN** group and private messages are processed near the same time
- **THEN** each turn SHALL retain its own conversation identity, policy, history visibility, and delivery destination
