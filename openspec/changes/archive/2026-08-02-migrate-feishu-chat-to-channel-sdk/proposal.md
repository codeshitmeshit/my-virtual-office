## Why

The Feishu Agent chat channel currently maintains a custom Python `lark_oapi` long-connection receiver, worker lifecycle, event normalization, and channel operations that overlap with the higher-level capabilities now provided by `@larksuite/channel`. Migrating the chat transport to that SDK reduces protocol-specific maintenance while preserving Virtual Office as the authoritative owner of Agent routing, conversation history, audit records, and business-level idempotency.

## What Changes

- Replace the Feishu Chat App's Python long-connection transport with a pinned `@larksuite/channel` Node worker.
- Consume normalized Feishu messages while preserving the complete sender identity and source metadata required by VO bindings and audit records.
- Move Chat App send, reply, reaction, recall, and inbound-resource operations behind the new channel worker without changing the VO Agent execution pipeline.
- Preserve representative-Agent selection, provider routing, conversation identity, mandatory VO history, persistent idempotency, ordering, and existing management APIs.
- Preserve exactly-once visual presentation in the VO chat window by reconciling locally optimistic user messages with their persisted history records instead of rendering both copies after history recovery.
- Preserve live Feishu-to-VO chat synchronization: an accepted Feishu request, Agent reply, or delivery outcome SHALL become visible without a manual refresh even though Feishu uses a separate `feishu-dm:*` conversation identity from the currently selected provider conversation.
- Initialize each opened or switched chat at the newest message and keep following new authoritative/live events only while the user remains at the bottom; scrolling upward SHALL disable automatic bottom jumps until the user returns to the bottom.
- Keep the Feishu notification/card-action application and its existing integration out of this migration.
- Provide observable connection and delivery status plus a controlled rollback path during migration.
- Pin the SDK dependency to an explicitly reviewed version and validate its worker contract through focused automated and end-to-end tests.

## Capabilities

### New Capabilities

- `feishu-agent-chat-channel`: Defines the Feishu private-chat channel contract, including SDK-backed transport, VO-owned routing and persistence, compatibility, failure handling, observability, and rollback behavior.

### Modified Capabilities

- None. No existing main OpenSpec capability defines the Feishu Agent chat channel contract.

## Impact

- Affected runtime areas include the Feishu Chat App worker/supervisor, inbound worker API, outbound chat operations, attachment handling, configuration/status projection, and Feishu-focused tests.
- A new pinned Node dependency on `@larksuite/channel` and its official `@larksuiteoapi/node-sdk` dependency enters the runtime and installation flow.
- Existing Python Agent routing, provider adapters, communication ledger, UI history and live SSE refresh behavior, optimistic-send behavior, and Feishu notification/card-action behavior must remain compatible.
- Operational procedures must cover worker health, reconnect behavior, version upgrades, rollback selection, and credential redaction.
