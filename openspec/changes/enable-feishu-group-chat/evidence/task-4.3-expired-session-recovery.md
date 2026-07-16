## Task 4.3 Expired-Session Recovery Evidence

Implemented a provider-neutral recovery coordinator in `ProviderConversationService`.
It attempts the stored native session first, asks the provider adapter whether the
result represents an invalid session, loads source-owned history only in that case,
bounds and canonicalizes the history, retries once without a native ID, and persists
the replacement native ID.

The first source adapter is Feishu group chat. It reads only the digest-named shard
for the exact `feishuChatId`, accepts only completed user/assistant turns, excludes
the current source message, and does not expose delivery, tool, or audit records.
Codex archived-thread recovery now uses this shared coordinator. When no source
history exists, the retry payload is exactly the current message.

Verification on 2026-07-16:

- Focused red-to-green recovery scenarios: 4 passed.
- Provider conversation, Codex server, Feishu notification, and chat-history suites: 116 passed.
- Feishu Node worker suite: 24 passed.
- Group-chat static configuration check: passed.
- `openspec validate enable-feishu-group-chat --type change --strict --no-interactive`: passed.
- `git diff --check`: passed.

The tests cover live-session no-op behavior, no-history fallback, one retry only,
replacement-ID persistence, completed-turn normalization, current-message
deduplication, and cross-group isolation. Task 7.2 remains a separate real-tenant
acceptance gate.
