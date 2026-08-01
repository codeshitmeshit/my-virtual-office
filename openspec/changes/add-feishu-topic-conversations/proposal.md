## Why

When a main Agent conversation is blocked by a long-running turn, Virtual Office sends an AI notification through an application-level bot direct message. A user can continue from a topic under that notification, but Virtual Office currently scopes the follow-up primarily to the containing bot DM. As a result, topic replies can block or pollute the bot DM conversation and cannot reliably continue from the originating main conversation with a small amount of relevant context.

## What Changes

- Treat the first supported user reply in a bot-DM topic rooted at a verified long-running AI notification as activation of one independent topic conversation.
- Route every later supported message in that topic to the same conversation, in message order, while keeping other topics and the originating conversation isolated.
- Seed the topic conversation with the source message, its originating request and response when available, a bounded summary plus recent relevant turns from the originating conversation, and the triggering topic message.
- Keep all Agent acknowledgements, status, and results in the originating Feishu topic and clearly identify the new conversation and its source relationship.
- Degrade gracefully when originating conversation context is unavailable: continue from the source and topic messages and disclose that context inheritance is incomplete.
- Use the Agent associated with the originating main chat when the topic conversation is activated, keep that Agent stable for the topic, and leave a narrow policy boundary for a later confirmed Agent-selection change.
- Preserve the bot DM's supported text, image, and file behavior in topic conversations.
- Reuse the notification App long connection, Feishu thread metadata, notification App reply operations, and the existing provider-neutral conversation bridge; do not add a parallel receiver, external queue, conversation store, transport, or Agent-routing subsystem.

## Capabilities

### New Capabilities

- `feishu-topic-conversations`: Activation, context inheritance, isolation, ordering, Agent binding, reply placement, degradation, and capability parity for conversations rooted in long-running AI notifications delivered through a Virtual Office bot DM.

### Modified Capabilities

None. The change composes the existing Feishu direct-message channel, notification, and Provider-conversation contracts through a new product capability. Group chats and group-message permissions are explicitly outside this change.

## Impact

- Notification App inbound normalization in `app/feishu_long_connection.py` and topic-aware conversation routing in focused new service modules.
- Thin orchestration and source-context lookup in focused new modules, wired from `app/server.py` without adding new business logic to that legacy entry point.
- Existing provider dispatch and `ProviderConversationService` conversation scoping in `app/services/provider_conversations.py` and provider bridge handlers.
- Existing long-running AI-notification delivery/audit metadata so an outbound bot-DM source message can be related back to its originating main conversation and Agent context.
- Focused Feishu channel, provider conversation, notification, recovery, ordering, isolation, and attachment tests.
- No new external dependency, daemon, database, queue, transport, or standalone tool is intended.
