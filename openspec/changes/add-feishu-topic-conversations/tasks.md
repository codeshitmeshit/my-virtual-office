## 1. Baseline contracts and feature boundary

- [x] 1.1 Add characterization tests for the notification App long-connection startup, its currently unused message handler, current message projection, notification audit record shape, and existing bot-DM behavior before changing implementation.
- [x] 1.2 Create `app/services/feishu_notification_topics.py` with immutable DTOs and injected protocols for root lookup, binding persistence, source history, Agent lookup, dispatch, delivery, time, and bounded scheduling; keep it independent from `app/server.py`.
- [x] 1.3 Add the default-off `topicConversationsEnabled` notification configuration and environment override, expose a secret-safe effective status, and verify that enabling it does not change Chat App, group-chat, or mention-filter configuration.

## 2. Notification App inbound topic normalization

- [x] 2.1 Extend `FeishuLongConnectionReceiver._message_event_to_body` to preserve `chat_type`, root/thread/reply identifiers, sender classification, mentions, resource descriptors, content type, and event time with bounded normalization tests.
- [x] 2.2 Wire the existing notification receiver `message_handler` through thin `app/server.py` dependency injection to the topic service while leaving the existing card-action handler and notification App identity unchanged.
- [x] 2.3 Implement early admission that accepts only human `chatType=p2p` topic-shaped messages when the feature is enabled, preserves bot-loop protections, and proves ordinary bot DMs, non-topic messages, unsupported senders, and every group path remain unchanged.

## 3. Root verification and durable topic binding

- [x] 3.1 Implement the versioned `NotificationRootLookup` DTO and redacted production-shape fixtures covering authenticated message ID, long-running-diversion classification, originating conversation, Agent, request/response references, and bounded display text.
- [x] 3.2 Extend the existing hashed source-message index with backward-compatible typed notification-root and topic-binding projections, atomic create-if-absent semantics, restrictive permissions, bounded fields, and no raw topic identifiers in public records.
- [x] 3.3 Implement O(1) notification-root lookup plus a first-activation-only bounded scan of current and rotated notification/communication audit records, followed by source-index read-repair; reject roots lacking authenticated long-running-notification evidence.
- [x] 3.4 Derive a stable redacted conversation ID from notification App identity, tenant, chat, and topic identity, and test cross-app, cross-tenant, cross-chat, and cross-topic isolation across restart.
- [x] 3.5 Implement the replaceable Agent-selection policy using the originating main conversation's associated Agent, atomically pin the first valid selection in the topic binding, and test configuration changes, missing Agents, duplicate activation, and concurrent activation.

## 4. Bounded inherited context

- [x] 4.1 Implement injected source-history loading and bounded selection for the root notification, originating request/response, goal and established constraints, at most 12 recent relevant turns, and the triggering topic message.
- [x] 4.2 Build the first-turn prompt as one semantic XML envelope with JSON-encoded escaped `<untrusted_data>`, a 32,000-character total limit and 8,000-character per-field limit, and injection/special-character tests.
- [x] 4.3 Persist and disclose complete, partial, or unavailable inheritance status; continue from available notification/topic content without fabricating missing source context, and prove the originating conversation and Provider-native session remain read-only.

## 5. Ordering, idempotency, and restart recovery

- [x] 5.1 Add a bounded per-topic in-process coordinator in the focused service that records accepted work in the existing source index before returning from the notification callback, serializes one topic, and permits different topics to progress up to existing global Provider limits.
- [x] 5.2 Implement duplicate-delivery reuse, queue-capacity rejection with a visible retryable result, and create-at-most-once activation acknowledgement; test concurrent first messages and messages arriving during an active turn.
- [x] 5.3 Reuse the existing source-index startup recovery pattern for accepted/processing notification-topic messages, including stale-owner fencing and deterministic topic/Agent restoration, and test restart before dispatch, during dispatch, and after persisted completion.

## 6. Generic Agent dispatch and topic delivery

- [x] 6.1 Dispatch accepted turns through the existing representative-Agent bridge with the pinned Agent, derived conversation ID, notification-topic source metadata, and validated attachments; do not add Provider-specific session creation or routing branches.
- [x] 6.2 Add a notification-App message-reply helper in `app/feishu_notifications.py` that reuses existing token acquisition, HTTP request, timeout, redaction, and audit machinery while preserving native topic placement.
- [x] 6.3 Deliver the one-time activation acknowledgement, Agent text/markdown results, degraded-context notices, and classified errors through the notification-App reply helper, persisting the Agent outcome before delivery classification and never redirecting to the bot-DM main timeline.
- [x] 6.4 Reuse `download_feishu_message_resource` and `ProviderConversationService.validate_attachments` for image, file, and multi-resource topic turns, with count, size, MIME, allowed-root, download-failure, and cleanup regressions.
- [x] 6.5 Propagate topic placement through existing approval-card context and callbacks; prove actor authorization and callback idempotency remain authoritative and protected actions stay unapproved when a topic card cannot be delivered.

## 7. Provider and compatibility verification

- [x] 7.1 Add contract tests proving Hermes, Codex, Claude Code, and OpenClaw all receive the same derived conversation scope through existing bridges, create new native state for a new topic, and reuse it for later turns.
- [x] 7.2 Add integration tests for two notification topics in one bot DM, isolation from the originating main conversation and ordinary DM, same-topic ordering, different-topic progress, duplicate delivery, restart recovery, and Agent pinning.
- [x] 7.3 Run and preserve regressions for existing notification sends and updates, card actions, Chat App direct messages, all group-chat behavior, chat commands, Provider history, approvals, resource handling, and source-index recovery.

## 8. Observability, rollout, and rollback

- [x] 8.1 Add bounded counters and hashed diagnostics for eligible/ignored topic events, activation created/reused, root verification misses, inheritance state, queue rejection, Agent failure, recovery, and topic delivery failure using existing status and audit surfaces only.
- [x] 8.2 Add a feature-disabled, read-only production preflight path that reports only notification classification, required-field presence, and hashed identifiers for an explicitly selected root; prohibit message bodies, credentials, and raw user/conversation identifiers in its output.
- [x] 8.3 Document configuration, notification-App identity boundaries, local fixture verification, production preflight, single-notification enablement, metrics gates, and flag-only rollback without permission, Chat App worker, or data migration steps.

## 9. Acceptance evidence

- [x] 9.1 Run focused Python and Node tests plus OpenSpec strict validation and record the commands/results in an evidence artifact without marking production-only scenarios as locally verified.
- [ ] 9.2 Deploy with the feature disabled and capture read-only production evidence for the actual long-running notification/audit shape; if required, add and locally test only a focused `NotificationRootLookup` compatibility adapter.
- [ ] 9.3 Enable one explicitly selected production test notification and verify `p2p` topic delivery without `@`, independent conversation creation, bounded context inheritance, pinned Agent, same-topic continuation, topic-local result placement, and ordinary DM/group non-regression.
- [ ] 9.4 Exercise flag-only rollback, confirm new topic activation stops while existing notification, card-action, Chat App, and group behavior remain unchanged, and record final acceptance results for the separate test-results review gate.
