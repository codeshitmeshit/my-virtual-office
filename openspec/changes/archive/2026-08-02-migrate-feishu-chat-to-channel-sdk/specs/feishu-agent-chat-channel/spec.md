## ADDED Requirements

### Requirement: SDK-backed Feishu Chat App transport
The Feishu Agent chat channel SHALL use a separately supervised Node worker built on a pinned, explicitly reviewed version of `@larksuite/channel` for Chat App connection lifecycle and event delivery. The worker MUST use WebSocket transport, report initial handshake success or failure, reconnect automatically after recoverable disconnects, and terminate when its owning VO server process is no longer alive.

#### Scenario: Chat channel starts successfully
- **WHEN** the Feishu Chat App is enabled with valid credentials and VO starts the channel worker
- **THEN** the worker SHALL complete the WebSocket handshake and report a connected status that VO exposes through the existing chat-channel status surface

#### Scenario: Recoverable connection loss
- **WHEN** an established Feishu Chat App connection is interrupted by a recoverable network failure
- **THEN** the worker SHALL attempt reconnection and expose reconnecting and reconnected state without requiring a VO restart

#### Scenario: Invalid credentials
- **WHEN** the worker cannot authenticate or resolve the Chat App identity
- **THEN** it SHALL report a stable failure status without logging the App Secret or repeatedly dispatching inbound work

#### Scenario: Parent server exits
- **WHEN** the VO server process that owns the Chat App worker exits
- **THEN** the worker SHALL disconnect and terminate instead of remaining as an orphaned Feishu consumer

### Requirement: Normalized inbound message contract
The channel worker SHALL convert each supported SDK `NormalizedMessage` into a versioned VO worker envelope while preserving the Feishu message ID, chat ID, chat type, original content type, readable content, creation time, thread/reply identifiers, mentions, resource descriptors, and complete sender identity needed by VO. SDK normalization MUST NOT decide the representative Agent, VO user binding, conversation ID, or persistence outcome.

#### Scenario: Text private message is normalized
- **WHEN** the SDK emits a private text message
- **THEN** the worker SHALL deliver one authenticated VO envelope containing the normalized content and all identifiers required to route, audit, and reply to that message

#### Scenario: Sender identifiers are preserved
- **WHEN** a raw Feishu event contains open ID, user ID, or union ID information beyond the SDK's primary `senderId`
- **THEN** the worker SHALL preserve the available identifiers in the VO envelope so the existing VO-owned binding policy can run without reduced identity fidelity

#### Scenario: Thread and reply context is present
- **WHEN** a supported inbound message is a reply or belongs to a thread
- **THEN** its root, thread, and replied-to message identifiers SHALL be included in the VO envelope

#### Scenario: Unsupported event is received
- **WHEN** the SDK emits an event that the VO Feishu Agent chat contract does not support
- **THEN** the worker or VO adapter SHALL record a stable ignored reason and MUST NOT dispatch an Agent

### Requirement: Existing private-chat product scope is preserved
The migration SHALL preserve the current Feishu Agent private-chat product scope. SDK support for group chat, bot-to-bot collaboration, comments, or additional event types MUST NOT enable those product behaviors unless a later confirmed specification explicitly adds them.

#### Scenario: Private message enters the Agent pipeline
- **WHEN** an accepted private message reaches VO
- **THEN** VO SHALL apply its existing binding and representative-Agent policies and dispatch the message through the existing Agent message pipeline

#### Scenario: Group message does not expand scope
- **WHEN** the Chat App receives a group message during this migration
- **THEN** the message SHALL be rejected or ignored according to the current private-chat policy and MUST NOT create an Agent turn

### Requirement: VO remains authoritative for Agent routing and conversation state
VO SHALL remain the sole authority for representative-Agent selection, sender binding policy, provider routing, conversation identity, mandatory message history, communication-ledger projection, and business outcome records. The channel worker MUST act only as a Feishu transport adapter and MUST NOT maintain an independent Agent conversation history.

#### Scenario: Representative Agent handles a message
- **WHEN** an accepted Feishu message is associated with a configured representative Agent
- **THEN** VO SHALL route it through the existing Hermes, Codex, Claude Code, or OpenClaw provider path selected by that Agent

#### Scenario: Representative Agent changes
- **WHEN** an operator changes the representative Agent and a later Feishu message arrives
- **THEN** the later message SHALL use the new representative Agent while existing historical records remain readable without migration

#### Scenario: Feishu turn is visible in VO
- **WHEN** an Agent turn completes or fails for a Feishu-originated message
- **THEN** VO SHALL retain auditable inbound, Agent outcome, and delivery records with Feishu source metadata through the existing history and communication-ledger model

### Requirement: Persistent business idempotency and ordering
VO SHALL retain persistent `sourceMessageId`-based idempotency across worker and server restarts and SHALL serialize Agent turns for the same VO Feishu conversation. SDK in-memory deduplication or chat queuing MAY provide an additional transport guard but MUST NOT replace the VO persistence-backed decision.

#### Scenario: Duplicate delivery in one worker lifetime
- **WHEN** Feishu or the SDK delivers the same source message more than once
- **THEN** VO SHALL create at most one Agent turn and return or reuse the recorded outcome for later deliveries

#### Scenario: Duplicate delivery after restart
- **WHEN** a previously completed source message is delivered after the Node worker or VO server restarts
- **THEN** VO SHALL identify the persisted completed turn and MUST NOT invoke the Agent again

#### Scenario: Rapid messages in one conversation
- **WHEN** two accepted messages for the same VO Feishu conversation arrive close together
- **THEN** their Agent turns and persisted outcomes SHALL retain deterministic conversation order without overwrite or cross-conversation leakage

### Requirement: SDK-backed outbound and resource operations
Chat App reply, send, reaction, reaction removal, recall, and inbound-resource download operations SHALL be available through an authenticated local worker command contract backed by `@larksuite/channel`. VO SHALL record the outcome of each operation, and a Feishu delivery failure MUST NOT erase the Agent result or inbound history.

#### Scenario: Agent reply is delivered
- **WHEN** VO completes an Agent turn for a Feishu private message
- **THEN** the worker SHALL send or reply with the requested content to the intended Feishu chat and return the resulting message identifier for VO audit

#### Scenario: Delivery fails
- **WHEN** the SDK reports rate limiting, permission denial, a revoked reply target, timeout, or another classified outbound error
- **THEN** VO SHALL preserve the Agent reply, record a stable delivery failure category, and expose a diagnosable result without leaking credentials

#### Scenario: Inbound resource is downloaded
- **WHEN** a supported Feishu message contains an image or file resource accepted by VO policy
- **THEN** the worker SHALL stream the resource to an approved VO attachment location, enforce configured size and path safety limits, and return metadata needed by the existing attachment pipeline

#### Scenario: Resource is unsafe or too large
- **WHEN** a resource violates VO path, type, or size policy
- **THEN** it SHALL be rejected with an auditable reason and MUST NOT be passed to an Agent as a trusted local attachment

### Requirement: Authenticated and secret-safe worker boundary
Every local request between VO and the channel worker SHALL be authenticated with a per-process secret or an equivalently scoped local credential. The worker SHALL bind only to a loopback or private process transport, validate request size and shape, redact App Secrets and tokens from logs/status/errors, and reject unauthenticated commands before performing a Feishu or Agent-related effect.

#### Scenario: Authenticated inbound callback
- **WHEN** the active worker delivers a valid normalized message using the current worker credential
- **THEN** VO SHALL accept the envelope for business processing

#### Scenario: Forged worker request
- **WHEN** a caller omits or supplies an invalid worker credential
- **THEN** VO and the worker command surface SHALL reject the request without dispatching an Agent, sending a Feishu message, or revealing the expected credential

#### Scenario: Sensitive failure occurs
- **WHEN** startup, connection, callback, or outbound processing fails
- **THEN** logs and status responses SHALL omit App Secrets, bearer tokens, cookies, authorization headers, and unredacted worker credentials

### Requirement: Backward-compatible VO surfaces
The migration MUST NOT intentionally change existing Feishu Chat App configuration fields, representative-Agent semantics, binding configuration, public management route paths, status response fields consumed by the UI, conversation metadata fields, history rendering, or provider request contracts. Any additive envelope or status versioning SHALL remain compatible during the migration window.

#### Scenario: Existing configuration is loaded
- **WHEN** VO starts with a previously saved Feishu Chat App configuration
- **THEN** the new worker SHALL use that configuration without requiring users to re-enter credentials or migrate history

#### Scenario: Existing UI inspects status and history
- **WHEN** the current VO settings or chat UI reads Feishu status, records, or conversation history
- **THEN** the documented fields and behavior used by that UI SHALL remain available

#### Scenario: Accepted Feishu message appears through live synchronization
- **WHEN** the representative Agent chat window is open and VO persists an accepted Feishu request, Agent reply, or delivery outcome
- **THEN** the existing Feishu SSE surface SHALL notify the UI and an authoritative normalized-history refresh SHALL make every new visible request or reply appear without a manual page refresh

#### Scenario: Feishu conversation identity differs from provider conversation
- **WHEN** a Feishu communication event uses a `feishu-dm:*` conversation ID while the chat window is displaying the representative Agent's provider conversation
- **THEN** normalized history SHALL include that visible Feishu event for the selected Agent without broadening the merge to unrelated Agents, unrelated non-Feishu conversations, or non-visible delivery records

#### Scenario: SSE reconnect recovers missed Feishu history
- **WHEN** the Feishu SSE connection reconnects after one or more events were missed
- **THEN** the UI SHALL refresh from authoritative normalized history and recover the missed visible Feishu messages without duplicating records already rendered

#### Scenario: Chat initialization starts at newest history
- **WHEN** a chat window is first opened or switched to another Agent or conversation and its initial cached or remote history finishes rendering
- **THEN** the message viewport SHALL settle at the bottom so the newest message is visible, including content whose height changes during immediate post-render layout

#### Scenario: New event follows an already-bottomed viewport
- **WHEN** a new live or authoritative chat event arrives while the message viewport is at the bottom within the UI's existing near-bottom tolerance
- **THEN** the history window SHALL advance to include the new event and the message viewport SHALL scroll to the bottom after rendering

#### Scenario: New event does not interrupt history reading
- **WHEN** a new event arrives after the user has scrolled above the near-bottom tolerance to inspect older messages
- **THEN** the UI SHALL preserve the user's viewport and MUST NOT force-scroll to the bottom until the user returns there

#### Scenario: Optimistic user message is reconciled with persisted history
- **WHEN** the chat UI immediately renders a locally optimistic user message and later receives the persisted communication/history record for the same `idempotencyKey`
- **THEN** the UI SHALL replace or merge the optimistic representation with the persisted record so the user message is displayed exactly once while retaining the authoritative persisted message ID, timestamp, status, and attachments

#### Scenario: History recovery does not duplicate a pending user message
- **WHEN** history refresh or provider recovery occurs while an optimistic user message is still present
- **THEN** the UI SHALL reconcile only an exact request identity match and MUST NOT collapse two distinct messages that happen to have the same text

#### Scenario: Existing provider receives a Feishu message
- **WHEN** VO dispatches a normalized Feishu message to an existing provider adapter
- **THEN** the provider SHALL receive the same required source metadata and attachment semantics as before the SDK migration

### Requirement: Notification integration remains isolated
The Feishu notification and card-action application SHALL remain operational on its existing configuration and runtime path during this change. Chat App SDK credentials, worker lifecycle, policy, failures, and rollback selection MUST NOT overwrite or implicitly reuse notification application configuration.

#### Scenario: Both Feishu applications are configured
- **WHEN** notification and Chat App credentials are both present
- **THEN** each application SHALL start and operate with its own credentials and responsibilities

#### Scenario: Chat worker fails
- **WHEN** the new Chat App worker cannot start or reconnect
- **THEN** existing Feishu notifications and card actions SHALL continue to operate independently

### Requirement: Observable operation and controlled rollback
VO SHALL expose the selected Chat App transport implementation, worker process state, SDK connection state, last successful event time, reconnect activity, callback/command failures, and redacted last error. Operators SHALL be able to switch back to the legacy Chat App worker during the migration window without changing credentials, VO conversation records, or representative-Agent configuration.

#### Scenario: Operator checks channel health
- **WHEN** an operator requests Feishu Chat App status
- **THEN** VO SHALL return enough redacted state to distinguish disabled, starting, connected, reconnecting, callback failure, command failure, authentication failure, and stopped conditions

#### Scenario: New worker fails acceptance checks
- **WHEN** an operator selects the legacy rollback implementation after a failed SDK rollout
- **THEN** VO SHALL stop the Node worker, start the legacy worker with the same Chat App configuration, and continue using existing VO history and idempotency records

#### Scenario: Process restart preserves selected transport
- **WHEN** VO restarts during the migration window
- **THEN** it SHALL start only the configured Chat App transport implementation and SHALL prevent simultaneous consumers for the same Chat App credentials

### Requirement: Reproducible dependency and installation behavior
The project SHALL declare and lock an exact reviewed `@larksuite/channel` version, install it through the supported project startup/dependency workflow, and fail with an actionable status when the required Node runtime or package is unavailable. An unreviewed dependency update MUST NOT be selected implicitly by a broad version range.

#### Scenario: Supported environment starts VO
- **WHEN** VO is installed or started with the supported Node runtime
- **THEN** the declared lockfile SHALL resolve the reviewed SDK version and the Chat App worker SHALL be launchable without a separate manual global installation

#### Scenario: Dependency is unavailable
- **WHEN** the Node runtime or pinned SDK package is missing or incompatible
- **THEN** VO SHALL report an actionable Chat App dependency error while leaving unrelated VO and Feishu notification functionality available
