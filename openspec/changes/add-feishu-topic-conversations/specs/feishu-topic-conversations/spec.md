## ADDED Requirements

### Requirement: Long-running notification topics in bot DMs activate independent conversations
Virtual Office SHALL automatically activate one independent Agent conversation when the first supported human message arrives in a Feishu topic whose containing chat is `p2p` and whose root is verifiably a long-running AI notification sent by the Virtual Office application for an originating main conversation. A group-chat topic or a topic rooted in any other message MUST NOT activate this capability.

#### Scenario: First topic reply activates a conversation
- **WHEN** a human sends the first supported reply in a bot-DM topic rooted at a verified long-running AI notification
- **THEN** Virtual Office SHALL create one independent topic conversation and dispatch that reply as its first user turn

#### Scenario: Later replies reuse the activated conversation
- **WHEN** a human sends another supported message in an already activated topic
- **THEN** Virtual Office SHALL route it to the same topic conversation instead of creating another conversation

#### Scenario: Different notification topics remain independent
- **WHEN** a user continues two different long-running AI notifications through their respective bot-DM topics
- **THEN** Virtual Office SHALL activate a different conversation for each topic and MUST NOT share subsequent turns between them

#### Scenario: Ineligible topic is not claimed
- **WHEN** a topic is in a group chat or its root cannot be verified as a long-running AI notification for an originating main conversation
- **THEN** Virtual Office MUST preserve the existing behavior and MUST NOT create a topic conversation under this capability

### Requirement: Topic identity is durable and isolated
Virtual Office SHALL use the Feishu chat and stable topic identity as the external scope of the derived conversation. The topic conversation MUST remain isolated from the originating conversation and from every other topic, including across worker or server restart.

#### Scenario: Topic messages do not mutate the originating conversation
- **WHEN** an Agent and user exchange messages in an activated topic conversation
- **THEN** those messages SHALL remain in the topic conversation and MUST NOT be appended to or change the originating conversation

#### Scenario: Same topic resumes after restart
- **WHEN** Virtual Office or the Feishu channel worker restarts after a topic conversation has been activated and a later message arrives in that topic
- **THEN** Virtual Office SHALL resolve the same conversation scope and continue it without creating a duplicate topic conversation

#### Scenario: Duplicate inbound delivery is idempotent
- **WHEN** Feishu or the channel worker delivers the same topic message more than once
- **THEN** Virtual Office SHALL create at most one Agent turn and SHALL reuse the durable recorded outcome for duplicate delivery

### Requirement: New topic conversations inherit bounded source context
On activation, Virtual Office SHALL construct bounded inherited context from the root long-running AI notification, its originating request and response when available, the originating main conversation's goal, key constraints and established conclusions, recent relevant turns, and the triggering topic message. Inherited material SHALL be treated as untrusted conversation data and MUST NOT be able to replace Agent instructions.

#### Scenario: Complete source context is available
- **WHEN** a topic is activated from a long-running AI notification that is associated with an originating main conversation and completed turn
- **THEN** the first Agent turn SHALL receive the source message, originating request and response, bounded conversation summary, bounded recent relevant turns, and triggering topic message

#### Scenario: Originating context remains read-only
- **WHEN** inherited context is supplied to a newly activated topic conversation
- **THEN** Virtual Office SHALL copy only the bounded context needed for the branch and MUST NOT alter the originating records or Provider-native session

#### Scenario: Context cannot escape the data boundary
- **WHEN** inherited source content contains text resembling system instructions or structured prompt delimiters
- **THEN** Virtual Office SHALL preserve it only inside an escaped untrusted-data boundary and the Agent's governing instructions SHALL remain effective

### Requirement: Missing source context degrades without blocking activation
Failure to resolve some or all originating conversation context MUST NOT prevent an otherwise eligible topic from activating. Virtual Office SHALL continue with the root long-running AI notification and available topic messages and SHALL clearly disclose that context inheritance is incomplete.

#### Scenario: Originating conversation is unavailable
- **WHEN** the long-running notification root is verifiable but its originating main conversation cannot be read
- **THEN** Virtual Office SHALL activate the topic conversation from the root and triggering messages and SHALL tell the user that earlier conversation context was not fully inherited

#### Scenario: Source association is partially available
- **WHEN** only some of the originating request, response, summary, or recent turns can be resolved
- **THEN** Virtual Office SHALL use the available bounded material, identify the degraded inheritance state, and MUST NOT fabricate missing content

### Requirement: Topic Agent selection is stable with a replaceable policy boundary
At topic activation, Virtual Office SHALL select the Agent associated with the originating main chat and SHALL keep that Agent fixed for the lifetime of the topic conversation. The selection decision MUST pass through a narrow policy boundary so a later confirmed specification can replace the rule without replacing Feishu transport or Provider conversation infrastructure.

#### Scenario: Originating chat Agent is selected at activation
- **WHEN** an eligible topic receives its first supported human reply
- **THEN** the new topic conversation SHALL use the Agent associated with the originating main chat

#### Scenario: Originating chat Agent changes after activation
- **WHEN** the originating main chat's assigned Agent changes after a topic conversation has already been activated
- **THEN** later messages in that topic SHALL continue using the Agent fixed at activation and MUST NOT switch implicitly

#### Scenario: No valid chat Agent is available
- **WHEN** an eligible topic receives its first reply but its originating main chat has no valid associated Agent
- **THEN** Virtual Office SHALL provide a clear configuration error in the topic and MUST NOT activate a partially bound conversation

### Requirement: Topic turns are ordered without cross-topic blocking
Virtual Office SHALL preserve accepted-message order within each topic conversation. A running turn MUST NOT cause a later accepted topic message to be silently lost or converted into another conversation, while work in one topic MUST NOT require serialization with a different topic solely because both topics share a containing chat.

#### Scenario: Message arrives while a turn is running
- **WHEN** a supported message is accepted in a topic while its previous Agent turn is still running
- **THEN** Virtual Office SHALL retain the later message and dispatch it after earlier accepted messages in that topic

#### Scenario: Topic backlog cannot accept a message
- **WHEN** an existing bounded channel limit prevents a topic message from being accepted
- **THEN** Virtual Office SHALL return a visible retryable status and MUST NOT claim that the message was queued or completed

#### Scenario: Different topics progress independently
- **WHEN** two distinct topics in the same Feishu chat receive supported messages
- **THEN** their conversation coordination SHALL remain independent and one topic's active turn MUST NOT make the other topic reuse its conversation identity

### Requirement: Activation and Agent output remain in the source topic
Virtual Office SHALL acknowledge activation in the originating Feishu topic with the derived conversation identifier and source relationship. All later acknowledgements, statuses, approval interactions, results, errors, and degradation notices for that conversation SHALL be delivered into the same topic whenever Feishu permits the reply.

#### Scenario: Activation is visible
- **WHEN** a topic conversation is activated successfully
- **THEN** Virtual Office SHALL post a confirmation in that topic containing a stable conversation identifier and an understandable reference to the source message

#### Scenario: Agent result returns to the topic
- **WHEN** an Agent turn for a topic conversation completes
- **THEN** Virtual Office SHALL reply inside that topic and MUST NOT redirect the result to the containing chat's main timeline

#### Scenario: Topic delivery fails
- **WHEN** Feishu rejects or times out a topic reply
- **THEN** Virtual Office SHALL preserve the Agent result and classified delivery failure in existing audit surfaces and MUST NOT report successful delivery

### Requirement: Bot-DM topic replies do not require a bot mention
A supported human reply inside a verified long-running AI-notification topic SHALL use the containing chat's existing `p2p` admission semantics and SHALL NOT require a bot mention. Group-chat admission and group-message permissions MUST remain unchanged and outside this capability.

#### Scenario: Human replies without mentioning the bot
- **WHEN** a trusted human posts a supported message without an explicit bot mention inside a verified long-running AI-notification topic in the bot DM
- **THEN** Virtual Office SHALL admit the message to the topic conversation

#### Scenario: Group-chat topic is outside scope
- **WHEN** a message arrives in any group-chat topic
- **THEN** this capability MUST NOT alter group admission or activate a notification-topic conversation

#### Scenario: Bot-authored reply enters the topic
- **WHEN** a bot-authored or self-authored message is received in an eligible topic
- **THEN** Virtual Office SHALL apply the existing bot-loop protection and MUST NOT create an Agent turn from that message

### Requirement: Topic conversations preserve supported message capabilities
Topic conversations SHALL accept every message content type supported by the containing Virtual Office bot DM, including text, images, and files, using the same validation, bounded resource handling, Provider attachment contract, and user-visible failure semantics.

#### Scenario: Text topic message
- **WHEN** a user sends supported text in an activated topic
- **THEN** Virtual Office SHALL deliver the text to the topic conversation through the selected Agent's existing Provider path

#### Scenario: Image topic message
- **WHEN** a user sends a supported image in an activated topic
- **THEN** Virtual Office SHALL use the existing Feishu resource download and Provider attachment path while preserving the topic conversation scope

#### Scenario: File topic message
- **WHEN** a user sends a supported file in an activated topic
- **THEN** Virtual Office SHALL use the existing bounded resource and Provider attachment contracts while preserving the topic conversation scope

#### Scenario: Unsupported or invalid attachment
- **WHEN** a topic attachment fails the existing type, size, path, or download validation
- **THEN** Virtual Office SHALL return the same truthful user-visible failure used by the containing chat and MUST NOT dispatch fabricated attachment content

### Requirement: Topic branching composes existing Feishu and Provider infrastructure
The capability MUST consume the existing notification App long connection's normalized root, thread, reply, mention, sender, and resource metadata; use notification App credentials through the existing authenticated Feishu request machinery; and dispatch through the existing Provider conversation bridge keyed by the derived conversation scope. It MUST NOT introduce a parallel Feishu receiver, outbound transport, external durable message queue, Provider-native session store, conversation history authority, or Agent-routing subsystem.

#### Scenario: Existing Feishu metadata is sufficient
- **WHEN** the notification App long connection supplies stable topic identifiers for an inbound topic message
- **THEN** Virtual Office SHALL derive topic routing from those normalized identifiers without querying or mirroring a second Feishu event source

#### Scenario: Existing Provider bridge dispatches a turn
- **WHEN** an eligible topic message is ready for Agent execution
- **THEN** Virtual Office SHALL pass the selected Agent, derived conversation scope, bounded message, and supported attachments through the existing Provider conversation and dispatch contracts

#### Scenario: Future Agent policy changes
- **WHEN** a later confirmed requirement changes how a topic Agent is selected
- **THEN** that change SHALL replace only the topic Agent-selection policy and MUST NOT require replacement of Feishu transport or Provider conversation coordination
