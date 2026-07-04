# Feishu CEO Agent Chat Sync

## Background

Virtual Office already supports multiple agents, project workflows, Feishu notification delivery, Feishu card actions, and Feishu message activity parsing. The new product idea is to expose one VO-side agent as a "CEO" identity in Feishu private chat, while keeping VO as the authoritative place for conversation history and context.

Users should be able to select one VO agent to represent VO in Feishu private chat. Technically and experientially, this should reuse the existing VO message/chat module: Feishu is an additional input/output channel for the same message pipeline, not a separate CEO-specific messaging system.

## Target Users

- VO users who have bound their Feishu account to their VO account.
- VO administrators or owners who can choose which VO agent currently carries the CEO identity.

This version is designed for one-to-one user conversations, not broad Feishu group participation.

## Product Goals

- Let a bound user privately talk to the VO CEO identity from Feishu without opening VO.
- Keep VO as the single source of truth for the CEO conversation record.
- Allow the CEO identity to be assigned to an existing VO agent, instead of creating an unrelated standalone bot.
- Let one selected VO agent represent VO in Feishu private chat.
- Extend the existing VO message module so it can accept and emit messages through the Feishu channel.
- Keep Feishu-originated conversation records visible and traceable in VO through normal message history.

## Scope

### CEO Identity Assignment

VO configuration must provide a setting for selecting one existing VO agent to carry the CEO identity.

The Feishu-facing display name should be:

- `CEO (by <Agent Name>)` or an equivalent localized form.

The user should be able to understand both the role being addressed and the underlying VO agent currently carrying the role.

### Feishu Channel Support In Existing Message Module

VO should not introduce a separate CEO private-chat panel in the first version.

Feishu configuration should distinguish two Feishu applications:

- Notification app: existing Feishu app used by prior notification/card-action features.
- Chat app: new Feishu app used by this requirement for long-connection private chat input/output.

The chat app must have its own credentials/configuration and should not silently reuse the notification app as the chat application.

Instead, the existing message module should support Feishu as a channel on top of the normal message send/history flow. The relevant message/conversation records should include channel metadata such as:

- `channel: "feishu"`
- `sourceApp: "feishu"`
- `sourceSurface: "feishu-dm"`
- `representativeAgentId`
- `sourceMessageId`
- `feishuChatId`

Product behavior:

- Feishu private-chat input is normalized into the same message format used by the existing VO chat module.
- Agent replies from the existing message pipeline can be emitted back to Feishu when the input channel is Feishu.
- All Feishu-channel user messages and assistant replies must be synchronized into VO message records. This is mandatory and must not be exposed as a disable-able option.
- VO continues to use normal message rendering, history display, send flow, loading state, and error display where possible.
- The representative agent setting determines which VO agent handles Feishu-channel private messages.

### Feishu Private Chat Entry

Only Feishu private chat is in scope for the first version.

Feishu channel input/output should use the new Feishu chat app's long connection only in the first version. Webhook receiving, polling, and additional receive modes are not in scope.

Supported behavior:

- A bound Feishu user can send a private message to the CEO identity.
- VO associates that message with the bound VO user.
- VO appends the message to that user's current one-to-one CEO conversation.
- The assigned CEO agent responds using the same conversation context.
- The response is delivered back to Feishu and also stored in VO.

### VO Conversation Entry

The same user can inspect Feishu-channel messages from the existing VO chat/history experience if those records are exposed in VO.

Supported behavior:

- Messages sent from Feishu and replies sent back to Feishu are stored through the normal VO message module, with Feishu channel metadata.
- If VO supports continuing the same chat from the existing chat UI, those VO-side messages should use the same normal chat send/rendering logic and channel metadata should make the origin clear.
- Each message records enough metadata to identify sender, channel, time, and representative agent.
- When the configured representative agent changes, old marked conversations do not require special product handling in the first version. Future Feishu messages should use the newly configured representative agent.

### Account Binding Requirement

Only Feishu users bound to a VO account can use the CEO private chat experience.

If a Feishu user is not bound:

- The product should provide a clear explanation that VO binding is required.
- The message must not be stored as a normal CEO conversation for an unknown user.

## Non-Goals

- No Feishu group chat support in the first version.
- No Feishu webhook receiving, polling, or alternative receive modes in the first version; only long connection is supported.
- No reusing the existing Feishu notification app as the chat app by default. The chat application is a separate configuration.
- No mirroring of all conversations where the CEO agent participates in VO.
- No cross-user shared representative thread.
- No special old-CEO/old-representative conversation lifecycle management in the first version.
- No support for unbound Feishu users talking to the CEO.
- No multi-CEO routing, department-specific CEO identity, or per-project CEO identity.
- No separate CEO private-chat panel or separate CEO-specific chat renderer in the first version.
- No requirement to synchronize attachments, voice, images, or rich media in the first version unless existing Feishu text handling already provides safe metadata.
- No requirement to expose every VO agent conversation in Feishu.

## Constraints

- VO is the authoritative record for synchronized CEO conversations.
- Recording Feishu-channel messages in VO is mandatory; there is no `recordMessages` off switch for this channel.
- The first version is private-chat only.
- The first version uses Feishu long connection only for channel input/output.
- Feishu notification app configuration and Feishu chat app configuration must be separate, because they serve different product capabilities.
- Feishu user identity must map to a VO user before a CEO conversation can be created or continued.
- CEO conversations must preserve channel metadata so that VO can audit whether a message came from Feishu or VO.
- The assigned CEO agent must be a VO-side agent visible and selectable within existing agent roster concepts.
- The VO-side and Feishu-side experience should reuse the existing message module, adding Feishu channel input/output support instead of introducing a separate CEO chat module.
- Assignment changes only need to make future Feishu messages use the newly configured representative agent; old marked conversations can be left as ordinary historical records.
- Error states must be understandable in Feishu, especially unbound account, missing CEO assignment, unavailable agent, and stale assignment.

## Success Criteria

- A bound user can message the CEO from Feishu private chat and receive a response.
- The same message and response are visible in VO as part of the user's current CEO conversation.
- Feishu-channel messages handled by the selected representative agent are visible or traceable in VO.
- VO shows which agent currently carries the CEO identity.
- Changing the CEO assignment affects future Feishu private-chat handling.
- Unbound Feishu users cannot create normal CEO conversations and receive a clear binding-required response.

## Product Decisions From Clarification

- Feishu entry: private chat only for the first version.
- Sync source of truth: VO is the only authoritative record.
- Conversation shape: Feishu messages are recorded through the existing VO message module with Feishu channel metadata.
- CEO identity: a VO-side agent can be selected to carry the CEO identity.
- Feishu display: show the role plus underlying agent, such as `CEO (by Agent Name)`.
- Assignment switch: future Feishu messages use the newly configured representative agent; old marked conversations do not need special handling in the first version.
- Access: only Feishu users bound to VO accounts can talk with the CEO.
- Primary value: unified conversation record and traceability in VO.
- Technical approach: reuse the existing message module and add Feishu channel input/output; do not create a standalone CEO private-chat message stack in the first version.
- Feishu app configuration: keep notification app and chat app separate; this requirement uses the chat app.
