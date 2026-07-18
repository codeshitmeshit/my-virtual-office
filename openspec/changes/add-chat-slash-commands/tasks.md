## 1. Baseline and Command Domain

- [x] 1.1 Add passing characterization coverage for existing VO new-session behavior, Codex reset/compact outcomes, Feishu private/group admission and idempotency, provider conversation isolation, and unknown slash-prefixed ordinary messages before production behavior changes.
- [x] 1.2 Create the independent `app/services/chat_commands.py` domain service with exact attachment-free parsing, bounded scope/request/result objects, injected provider-control, ID, clock, reservation, and audit ports, plus pure unit tests for command, no-op, busy, unsupported, failure, stale, and indeterminate outcomes.

## 2. Provider Control and Persistence

- [x] 2.1 Implement provider-control adapters for VO logical conversation creation and Feishu scoped reset across Codex, Hermes, Claude Code, and OpenClaw, preserving old VO conversations and using existing `ProviderConversationService` generation/state ports; add focused reset, stale-commit, cross-scope, and cleanup-failure tests.
- [x] 2.2 Integrate Codex native compaction behind the command capability port, return no-mutation `unsupported` for Hermes, Claude Code, and OpenClaw, and add provider-matrix tests for success, no context, busy, timeout/failure, and unsupported behavior.
- [ ] 2.3 Add bounded command operation recording, non-blocking per-scope reservation, feature-flag evaluation, low-cardinality counters, and durable started/terminal/indeterminate semantics using existing VO/Feishu journals and indexes; test duplicate, crash-window, feedback-failure, redaction, and retention behavior.

## 3. Virtual Office Transport and UI

- [ ] 3.1 Add the thin management-authenticated `POST /api/chat/commands/execute` route and server wiring that resolves provider/profile from the authoritative Agent roster, validates Agent-owned conversation/session identities, delegates to the command service, and returns normalized status and next-identity fields; add API authorization, validation, spoofing, idempotency, and status tests.
- [ ] 3.2 Integrate exact command submission into `app/chat.js` before optimistic ordinary-message insertion; switch history cache and SSE subscriptions only after successful `/new`, preserve the old conversation and current selection on failure, show normalized feedback, and add JavaScript/browser regression coverage for old-history reopening and stale-response isolation.

## 4. Feishu Transport Integration

- [ ] 4.1 Extend `app/feishu_chat_channel.py` with an injected command callback after existing admission and trusted conversation derivation, route only exact attachment-free commands away from Agent dispatch, use non-blocking conversation admission, and emit distinct bounded command audit/feedback outcomes; add direct channel tests for private, mentioned group, unmentioned group, actor attribution, shared scope, and cross-group isolation.
- [ ] 4.2 Wire Feishu command execution in the server through existing source-message claim/index, provider-control, audit-shard, communication-history projection, recovery, and delivery paths; add restart/redelivery, started-without-terminal, feedback failure, same-group concurrency, private/group compatibility, and representative-Provider matrix tests.

## 5. Rollout, Documentation, and Verification

- [ ] 5.1 Add configuration and status documentation for `VO_CHAT_SLASH_COMMANDS_ENABLED` and `VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED`, document the Provider capability matrix, exact command grammar, group shared-context effect, rollout order, observability, indeterminate reconciliation, and configuration-only rollback.
- [ ] 5.2 Run OpenSpec validation plus focused Python, JavaScript/static, chat-history, Provider, and Feishu suites; perform flag-off and staged flag-on acceptance for every specification scenario, record commands/results/unverified external-tenant items in change evidence, and fix only regressions within the confirmed scope.
