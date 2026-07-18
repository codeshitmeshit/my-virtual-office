## Why

Users currently need surface-specific controls to start a clean Agent conversation or reduce accumulated context. A small, consistent slash-command contract will make those operations available directly from both the Virtual Office chat UI and Feishu without changing existing conversation-isolation rules.

## What Changes

- Add `/new` as an immediate command that starts a clean Agent context for the current chat scope without deleting existing visible history.
- Add `/compact` as a command that compacts older context for the current conversation and then continues that conversation.
- Support both commands in the Virtual Office chat UI, Feishu private chats, and mention-gated Feishu group chats.
- Return explicit success or failure feedback and leave the existing context usable when a command cannot complete.
- Preserve current Feishu scope boundaries: private conversations remain isolated by the existing user-and-chat identity, while all accepted members of one group share that group's existing conversation identity.
- Keep ordinary messages and existing Feishu admission, attribution, delivery, history, and provider behavior compatible.

## Capabilities

### New Capabilities

- `chat-slash-commands`: Defines command recognition, `/new` and `/compact` behavior, supported VO and Feishu surfaces, scope isolation, feedback, and compatibility requirements.

### Modified Capabilities

None.

## Impact

- Affected surfaces: Virtual Office chat input and the Feishu Agent Chat private/group message path.
- Affected application behavior: provider conversation reset/new-session and compaction orchestration for the current provider, Agent, profile, and conversation scope.
- Affected persistence and history behavior: existing visible messages remain available; provider context and continuation state change only within the targeted scope.
- Compatibility dependencies: existing chat-history conversation keys, Feishu private/group conversation IDs, group mention admission, provider capabilities, and provider-specific compact/reset support.
- Implementation must place command parsing and orchestration in a focused module with thin transport integration rather than adding business logic to `app/server.py`.
