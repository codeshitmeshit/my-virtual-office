## Context

Virtual Office already exposes provider-specific conversation controls, but they are split across the browser and `app/server.py`: Codex has reset and native compaction endpoints, Hermes and Claude Code have scoped history/session reset paths, and OpenClaw has Gateway session reset. The browser also owns provider-specific conversation-ID rotation. Feishu Agent Chat derives a stable private or group `conversationId`, serializes accepted turns per conversation, and persists source-message idempotency and delivery records before dispatching to the representative Agent.

The change crosses the browser, HTTP transport, Feishu transport, provider conversation state, audit history, and four provider families. It must preserve the existing `(provider kind, Agent, profile, conversationId)` boundary and must not add command business logic to `app/server.py`. The current runtime has native context compaction only for Codex; other providers can reset but cannot truthfully report compaction success.

## Goals / Non-Goals

**Goals:**

- Recognize the two exact commands once and execute them through one provider-neutral application service.
- Preserve old VO conversations when `/new` creates and selects a new logical conversation.
- Reset context inside the existing stable Feishu private/group identity without changing its isolation dimension.
- Reuse existing provider state, locks, Feishu source indexes, audit records, and communication history rather than introducing a second conversation authority.
- Return stable success, no-op, busy, unsupported, failed, or indeterminate results and make Feishu state-changing commands at-most-once across redelivery.
- Keep transport files thin and make the command service independently testable through injected ports.

**Non-Goals:**

- Implement generic summary-based compaction for providers that do not expose a verified compaction operation.
- Add `/help`, arguments, aliases, completion, menus, or a configurable command registry.
- Delete visible history or migrate existing conversation IDs, provider histories, or Feishu audit records.
- Change existing button confirmation behavior, Feishu admission policy, group membership policy, provider APIs, or ordinary-message semantics.

## Decisions

### 1. Add a focused provider-neutral command application service

Create `app/services/chat_commands.py` as the sole owner of command parsing and orchestration. It will define bounded value objects such as `ChatCommand`, `CommandScope`, `CommandRequest`, and `CommandResult`, plus explicit injected protocols for provider control, conversation-ID creation, operation recording, and clock/ID generation. It MUST NOT import `app/server.py`, HTTP handlers, Feishu SDK code, or provider globals.

The parser will accept only attachment-free text whose trimmed, post-mention content is exactly `/new` or `/compact`. This prevents an attachment accompanying command-looking text from being silently discarded. Unknown, differently cased, argument-bearing, or attachment-bearing input returns `not_command` and follows the existing message path.

Alternative considered: duplicate checks in `app/chat.js` and `app/feishu_chat_channel.py`. Rejected because two parsers would drift and transports would become owners of state transitions.

### 2. Use one HTTP command endpoint and one injected Feishu command callback

Add a thin authenticated management route, `POST /api/chat/commands/execute`, for the VO browser. The request carries the selected `agentId`, current conversation/session identity, exact command, and an idempotency key. Server wiring resolves the Agent and provider from the authoritative roster, rejects mismatches and invalid identifiers, builds a trusted `CommandScope`, and delegates to the command service. The route returns a normalized result including `status`, `reply`, current scope, and any `nextConversationId` or `nextSessionKey`.

`app/chat.js` will perform an early exact-command check before optimistic ordinary-message insertion, call the endpoint through the existing management-auth helper, and render only the normalized command result. On successful `/new`, it switches history/SSE state to the returned new identity; on failure, it retains the current selection. Existing new-session and compact buttons remain separate compatibility paths in this change.

`app/feishu_chat_channel.py` will receive an injected `dispatch_command` callback alongside `dispatch_agent`. It will run command recognition only after existing credential, chat-type, sender, mention, content, representative-Agent, and trusted conversation derivation checks. A non-command continues unchanged to `dispatch_agent`; a command never reaches that callback.

Alternative considered: have Feishu call the new HTTP endpoint. Rejected because it would re-serialize trusted in-process identity through an external transport and complicate authentication, timeouts, and tests.

### 3. `/new` has surface-specific identity behavior behind one result contract

For VO browser chat, `/new` creates a new logical identity and does not reset or delete the old one:

- Codex, Hermes, and Claude Code receive a new bounded opaque `conversationId`; the next ordinary turn lazily creates the provider-native continuation.
- OpenClaw/Gateway receives a new Agent-owned session key derived from a server-generated opaque ID; the next turn uses that key without resetting the previous session.
- The response contains the next identity, and the browser switches cache/history/event subscriptions only after success.

For Feishu, the externally derived private/group `conversationId` remains stable. The provider-control port resets the continuation generation for that existing scope:

- Codex clears only the scoped thread mapping under its existing operation lock.
- Hermes and Claude Code reset only the matching `ProviderConversationService` key and state port. Old provider-native cleanup is best-effort after the new empty generation commits and does not turn a successful logical reset into a retryable failure.
- OpenClaw invokes `sessions.reset` only for the Agent-owned session key derived from the trusted Feishu conversation.

The reset does not delete Feishu audit/communication history. Any provider-state write failure returns failure before success is recorded.

Alternative considered: reset the old VO conversation and then rotate the browser ID, matching the current new-session button. Rejected because it would make the preserved old conversation non-resumable and violates the confirmed `/new` history contract.

### 4. `/compact` is capability-driven and initially succeeds only for Codex

The provider-control registry declares `reset` and `compact` separately. Codex delegates compact to its existing native thread compaction path and operation lock. Hermes, Claude Code, and OpenClaw return normalized `unsupported` without changing state because the repository has no verified provider operation capable of preserving summarized meaning for them.

No local prompt-summary fallback will be introduced: it would create a second context authority, require provider-specific replay semantics, and could falsely claim that a native context was compacted. A later confirmed change can add provider adapters when a real capability exists.

Alternative considered: send a summarization prompt and reset the session with the reply. Rejected because tool state, approvals, attachments, hidden provider context, and replay boundaries cannot be preserved reliably by a transport-level summary.

### 5. Reserve command execution durably before provider side effects

The command service uses an idempotency scope of `(surface, source/idempotency key, provider, Agent, profile, conversation)`. VO retries use the browser-provided idempotency key and the bounded operation journal. Feishu reuses its persistent source-message index and per-conversation audit shard.

For Feishu, the flow is `claim -> persist started -> execute provider operation -> persist terminal outcome -> deliver feedback`. A duplicate terminal command returns the recorded outcome. A duplicate or recovery event that finds `started` without a terminal outcome MUST NOT repeat a state-changing operation; it records/returns `indeterminate` for reconciliation. This chooses at-most-once execution over automatic replay because Codex compaction has no provider idempotency token. Feedback failure never reopens execution.

No separate command database is added. The Feishu source index/audit remains authoritative for Feishu, while existing bounded operation communication records remain authoritative for VO operations.

Alternative considered: rely only on in-memory locks and rerun after restart. Rejected because a crash after provider compaction but before reply persistence could compact twice.

### 6. Commands use non-blocking conversation admission

Command execution attempts a non-blocking reservation for the same provider/Agent/conversation owner used by ordinary turns and provider controls. Existing provider locks remain the final concurrency fence. A busy result is returned rather than waiting behind a long Agent turn.

For Feishu, command messages use a non-blocking acquisition of the existing derived-conversation lock. Ordinary messages retain current serialized behavior. This prevents a command worker from waiting for the full provider timeout and makes the confirmed busy scenario observable.

All state transitions follow compare-and-commit/generation semantics already supplied by `ProviderConversationService`; a stale token cannot overwrite a reset generation.

### 7. Record control outcomes without adding commands to Agent prompt history

Recognized commands produce bounded operation records with command kind, status, trusted scope, source identity, timestamps, duration, and feedback delivery status. They omit provider raw output, unrestricted context, credentials, and unrelated conversation data.

Feishu uses distinct `command_started` and `command_completed` audit events. Communication-history projection emits a system operation rather than an ordinary request/reply pair, so command text is visible/auditable where appropriate but never becomes Agent prompt context. Group command records remain subject to existing group visibility policy. The browser inserts the normalized system feedback into the correct history cache only after the server result.

### 8. Roll out behind bounded feature flags and existing status surfaces

Add a global `VO_CHAT_SLASH_COMMANDS_ENABLED` flag and a narrower `VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED` flag. Initial deployment keeps both disabled; enable VO first, then Feishu private traffic, then mention-gated groups. Disabled commands retain pre-change ordinary-message behavior so rollback is configuration-only and does not require data migration.

Expose bounded counters/status for recognized, succeeded, busy, unsupported, failed, indeterminate, duplicate, and feedback-failed outcomes by surface/provider/command without message text or raw identifiers. Reuse existing Feishu audit rotation and process metrics; do not add an unbounded label dimension.

## Risks / Trade-offs

- **[Non-Codex `/compact` is recognized but unsupported]** → Return an explicit capability result and never simulate success; document the provider matrix and cover each provider in tests.
- **[Group members can reset shared context for everyone]** → Preserve the confirmed mention and human-member admission policy, record actor attribution, and return feedback in the originating group.
- **[Crash after provider side effect but before terminal persistence]** → Persist `started` first and treat recovery as indeterminate without automatic re-execution.
- **[New browser identity and stale async events cross]** → Switch history and SSE keys only after success, invalidate only the affected cache entry, and retain existing mismatched-response rejection.
- **[Provider reset cleanup partially fails]** → Treat the committed empty generation as authoritative and make old-native cleanup best-effort and non-retry-triggering.
- **[Command checks increase hot-path cost]** → Use an O(1) two-string parser before provider work; no history scan or external dependency is added to ordinary messages.
- **[Feature overlaps active Feishu/provider changes]** → Re-read current OpenSpec/code state before each task, keep edits modular, and run focused Feishu/provider characterization tests before integration.
- **[Existing dirty `app/server.py` changes are overwritten]** → Treat them as user-owned, patch only narrow wiring points, and review the task-local diff before any commit.

## Migration Plan

1. Add the service, pure parser, result contract, provider control ports, and unit tests with flags disabled.
2. Add thin HTTP and browser integration; deploy with both flags disabled and verify no ordinary-message regression.
3. Enable the global flag for a local/small VO cohort; observe command outcome counters, conversation switching, busy behavior, and stale-event isolation.
4. Enable Feishu command handling for private chat, then mention-gated groups; verify source-message idempotency, group isolation, feedback delivery, and indeterminate recovery.
5. Roll back by disabling the Feishu flag first and then the global flag. Existing conversation IDs and histories require no migration or repair; already committed resets/compactions remain valid effects.

## Open Questions

None blocking. Adding real compaction for Hermes, Claude Code, or OpenClaw requires a later provider-capability change with its own confirmed specification.
