## Why

Switching between long chat conversations currently reloads, reparses, and remounts the full history, so previously visited conversations can still feel slow and large histories can block the main thread. This change makes conversation switching responsive while preserving message order, rich message content, live provider updates, and access to older history.

## What Changes

- Show a previously visited conversation immediately from a conversation-scoped cache, then reconcile it with current server history in the background.
- Load and render the newest history page first instead of rebuilding up to 500 messages before the conversation becomes usable.
- Support cursor-based loading of older messages while preserving the user's visible scroll position.
- Keep the mounted history DOM bounded so long conversations do not continuously increase layout and rendering cost.
- Reuse stable rendered message content and merge SSE updates into the same cached conversation state without duplicates or stale cross-conversation updates.
- Avoid full history reloads when reselecting an unchanged conversation or reopening a chat panel whose state is still valid.
- Add automated regression and performance-oriented acceptance coverage for all supported chat providers.

## Capabilities

### New Capabilities

- `chat-history-navigation`: Responsive conversation switching, recent-first history paging, bounded rendering, scroll anchoring, cache reconciliation, and live-event consistency for chat history.

### Modified Capabilities

None. The project has no existing OpenSpec capabilities to modify.

## Impact

- Frontend chat state, history loading, message rendering, scrolling, and provider event reconciliation in `app/chat.js` and related styles.
- Chat history HTTP APIs and history-source merging in `app/server.py`.
- Existing Codex, Hermes, Claude Code, Gateway, tool-card, approval, attachment, and Feishu-history behavior must remain compatible.
- New static, unit-style, API, and browser performance regression tests under `tests/`.
