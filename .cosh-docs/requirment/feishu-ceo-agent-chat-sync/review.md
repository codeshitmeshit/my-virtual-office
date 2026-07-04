# Review

## Product Review

The requirement is product-valid and has a clear first-version boundary.

Strong points:

- It chooses Feishu private chat first, which keeps the social model and privacy expectation simple.
- It keeps VO as the authoritative record, avoiding split-brain history between Feishu and VO.
- It treats CEO as a role carried by an existing VO agent, which fits the VO agent roster model better than creating a disconnected bot.
- It keeps the implementation light by treating Feishu as an input/output channel of the existing message module instead of adding a separate CEO-specific message stack.
- It explicitly avoids mirroring all CEO-agent conversations, preventing accidental exposure of unrelated VO conversations.
- It avoids unnecessary old-conversation lifecycle rules; the first version only needs future Feishu messages to use the currently configured representative agent.

Remaining product risks:

- Users may expect the Feishu bot itself to be named only "CEO"; the transparent `CEO (by Agent Name)` display should be checked in UI copy.
- If VO exposes prior marked chats, they should remain understandable as ordinary chat history, but no special old-CEO archive behavior is required in version one.
- Binding-required errors must be friendly and actionable; otherwise Feishu feels broken before users reach the core value.
- The first version excludes Feishu group chat, which is correct for scope but may need a visible "not supported yet" behavior if users mention or add the app in group contexts.

## Technical Review

Existing relevant implementation and assets:

- `app/feishu_sync.py` already parses Feishu inbound direct-message log lines, response-ready lines, Hermes `state.db` message rows, and exposes a `FeishuEventBus` / `FeishuLogTailer`.
- `app/feishu_notifications.py`, `app/feishu_long_connection.py`, and `app/server.py` already contain Feishu app configuration, send helpers, notification records, and card action handling patterns.
- `app/projects.js` and server project execution paths already use the VO agent roster and agent IDs for assignment-like product flows.
- Existing Feishu workflow notification work already records Feishu-related markers and tests callback behavior, which provides patterns for idempotency and non-blocking Feishu failures.
- Existing VO chat rendering and message flows should be reused; the new product requirement is Feishu channel input/output plus representative-agent routing, not a separate CEO chat UI or message module.
- Existing chat/provider paths already accept source metadata such as `sourceApp`, `sourceSurface`, `sourceLabel`, and `fromType`; Feishu should use this pattern instead of inventing a parallel metadata shape.
- Existing Feishu notification app config should remain for notifications/card actions. This requirement should introduce or use a separate Feishu chat app config for long-connection private chat.

Required product-to-technical capabilities:

- A persisted VO setting for the current CEO assignment, referencing an existing VO agent ID and display metadata.
- A binding lookup between Feishu user identity and VO user identity before any CEO conversation write.
- Message module support for `channel: "feishu"` or equivalent source metadata on inbound user messages and outbound assistant replies.
- Separate Feishu chat app configuration, distinct from the existing notification app configuration.
- A Feishu private-message adapter that normalizes Feishu events into the existing message-send contract instead of directly invoking agent/provider-specific code.
- Representative-agent routing that selects the configured VO agent when the input channel is Feishu private chat.
- A response output adapter that sends the existing message pipeline's assistant reply back to Feishu when the originating channel is Feishu.
- Mandatory VO message recording for both inbound Feishu messages and outbound Feishu replies. This must be a channel invariant, not a user-facing setting.
- Assignment-switch behavior that makes future Feishu private-chat messages use the newly configured representative agent.

## Technical Risks And Required Decisions

No blocking product issue is present, but the following technical decisions must be made before implementation:

- Source of inbound Feishu messages: use Feishu long connection only in the first version. Do not add webhook receiving, polling, or log-tailing as a product path for this feature.
- Feishu app separation: ensure notification delivery/card-action credentials and chat long-connection credentials are not conflated. Backward compatibility for the notification app must be preserved.
- VO user binding source: the repo needs a clear persisted mapping from Feishu sender IDs to VO users. If this does not already exist, the first implementation must include a minimal binding model or reuse an existing identity config.
- Conversation persistence boundary: if the existing VO chat history is primarily UI/runtime state, the Feishu channel metadata and synchronized messages need durable storage so VO can trace Feishu conversations after restart.
- Agent invocation semantics: the selected CEO agent may be Hermes, Codex, Claude Code, or another provider-backed agent. The implementation should use existing provider-neutral agent execution where available rather than creating a CEO-only execution path.
- Idempotency: Feishu message IDs should prevent duplicate user-message writes and duplicate CEO replies when log tailing, retries, or webhook redelivery occurs.
- Ordering: messages from Feishu and VO can arrive near-simultaneously. The conversation model needs stable ordering and should avoid two concurrent CEO runs corrupting the same active context.
- Permissions: only the bound VO user should see and continue their own CEO private conversation unless a later requirement explicitly defines admin visibility.
- Error handling: unbound user, missing CEO assignment, missing/unavailable agent, and failed response generation should not create misleading normal conversation turns.

## Suggested Product-to-Technical Shape

Use VO as the owner of the CEO conversation state:

- Add a CEO assignment setting that points to a VO agent.
- Add a Feishu channel adapter around the existing message module rather than creating a separate CEO chat panel.
- Use the Feishu chat app long connection as the only supported receive path for Feishu private-message events in the first version.
- Normalize Feishu private text events into the existing send contract with `sourceApp: "feishu"`, `sourceSurface: "feishu-dm"`, `fromType: "human"`, `sourceMessageId`, `feishuChatId`, and `representativeAgentId`.
- Route Feishu private text messages through a binding check, then dispatch through the same message/agent pipeline used by normal chat.
- Store each turn with channel metadata, source message ID, sender identity, created time, and representative agent ID.
- Always persist Feishu-channel inbound and outbound messages into VO before treating the turn as complete; do not add a configuration option that disables this recording.
- Use the existing agent/provider abstraction and record the assistant response before or while the Feishu output adapter sends it back to Feishu.

## Review Conclusion

The requirement can proceed to checklist confirmation.

There are no product blockers that require another product clarification round. Technical implementation must still choose the exact Feishu inbound event source and user-binding storage, but those are implementation design decisions rather than blockers to drafting the checklist.
