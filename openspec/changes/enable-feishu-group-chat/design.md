## Context

The Feishu Chat App currently uses a supervised Node worker built on `@larksuite/channel` 0.4.0. The SDK already normalizes `p2p` and `group` messages, resolves the bot identity during connection, identifies whether the bot was mentioned, strips the addressing bot mention from readable content, applies a policy gate before spooling, and preserves sender, mention, thread, and resource metadata in the authenticated `vo.feishu-chat.inbound/v1` envelope.

VO currently narrows that transport capability to private chat in Python: configuration projects `allowedChatTypes: ["p2p"]`, `feishu_chat_channel.handle_message_event` ignores every non-`p2p` event, private conversation IDs use the `feishu-dm:*` namespace, and communication-ledger synchronization marks accepted Feishu request/reply rows visible in the office and publishes Feishu SSE invalidations. The communication-ledger and normalized-history paths therefore need an explicit group/private distinction; merely accepting `chat_type=group` would leak group activity into the representative Agent's VO chat window and would derive conversation identity from the triggering member.

Stakeholders are the administrator who intentionally adds the bot to trusted groups, every human member of those groups, operators responsible for the representative Agent and its permissions, and maintainers of the worker, provider, history, audit, and rollout paths. Group volume is bounded by the existing worker controls: at most 16 active callbacks, a per-chat queue depth of 20, a durable inbound spool, and Python conversation locks. Non-mentioned messages must be rejected before the durable spool and Agent pipeline so ordinary group traffic does not become VO load.

## Goals / Non-Goals

**Goals:**

- Accept mention-gated text and image interactions from every group that intentionally contains the bot, without a VO allowlist or user binding.
- Maintain one deterministic shared conversation per Feishu group while preserving complete isolation from private chat and other groups.
- Preserve the triggering human's identity in audit/provider metadata and make the active speaker unambiguous to every supported provider.
- Reply only in the originating group, preserving a topic/thread when Feishu supplies one.
- Keep group request, reply, and delivery records auditable but invisible to normalized VO chat history and absent from Feishu chat SSE publication and replay.
- Reuse the existing worker authentication, spool, resource safety, provider routing, idempotency, ordering, and outbound error classification.
- Provide a default-off operational switch so the code can ship before real-tenant activation and can be disabled without affecting private chat.

**Non-Goals:**

- Reading, persisting, or summarizing ordinary group messages that do not mention the bot.
- A VO-managed group allowlist, group approval workflow, member synchronization, or group administration.
- Files or message types beyond the existing text/image scope, bot-to-bot collaboration, `@all` triggering, comments, or cards.
- Displaying or navigating Feishu group history in the VO chat UI.
- Changing private-chat binding, conversation identity, visibility, delivery, or SSE behavior.
- Making the legacy Python Feishu receiver group-capable; disabling or rolling back from the Node transport returns the product to private-only behavior.

## Decisions

### 1. Gate groups in both the SDK and VO, with membership as the trust decision

The Node worker will set the SDK policy explicitly to `requireMention: true`, `respondToMentionAll: false`, `dmMode: "open"`, and an empty `groupAllowlist`. In SDK 0.4.0 an empty group allowlist accepts any group in which Feishu can deliver an event to the bot, while `requireMention` rejects ordinary traffic before batching, spooling, or callback delivery. Existing zero-delay, one-message batching and `mergeWhileBusy: false` remain unchanged.

The worker envelope already preserves normalized `mentions`; the SDK marks the mention that targets its resolved bot identity with `isBot: true` and removes that addressing token from readable content. VO will independently require `chatType == "group"`, `groupChatEnabled == true`, at least one `mentions[].isBot == true`, and a sender positively identified as a human user. Known bot, system, or anonymous senders and missing/ambiguous bot-mention evidence are ignored with stable policy reasons. This is defense in depth against a forged or legacy callback and preserves the confirmed human-only scope.

The group switch will be represented as `feishu.chatApp.groupChatEnabled`, with `VO_FEISHU_GROUP_CHAT_ENABLED` as an environment override. It defaults to `false` when absent. The management response will project `allowedChatTypes` dynamically as `["p2p"]` or `["p2p", "group"]`; saving unrelated Feishu settings must preserve the switch. Enabling the switch requires the `channel-sdk-node` transport; status reports a clear unsupported-transport reason otherwise.

Alternatives considered:

- A VO group allowlist was rejected because intentional bot membership is the confirmed trust boundary.
- Relying only on the SDK policy was rejected because VO owns business admission and authenticated callback compatibility.
- Inferring a mention from text was rejected because display text is forgeable and localized; only normalized identity metadata proves the bot target.

### 2. Give every group a deterministic identity independent of its members

Private conversation derivation remains unchanged. Accepted group turns use `feishu-group:<digest>`, where the digest is derived only from the Feishu chat ID under a domain-separated hash. The triggering member is never part of this key. This identity is passed through the existing provider conversation service, so the same group's Hermes, Codex, Claude Code, or OpenClaw turns serialize and resume through existing provider-specific mappings while other groups and `feishu-dm:*` conversations remain distinct.

The Python conversation lock remains keyed by the derived conversation ID. This provides same-group ordering even though the Node worker permits bounded cross-chat callback concurrency. Different groups retain independent locks and can progress concurrently.

Alternatives considered:

- Reusing `feishu-dm:*` was rejected because history filters and operators cannot safely distinguish visibility domains.
- Deriving the key from member plus group was rejected because it creates private sub-conversations rather than one shared group context.
- Using an unredacted chat ID as the conversation ID was rejected to avoid spreading external identifiers into provider-native state and diagnostics.

### 3. Separate speaker attribution from shared conversation identity

The worker-to-VO adapter will retain the normalized sender name, type, bot flag, and available open/user/union IDs. Group audit records and communication-ledger request rows use a stable Feishu sender reference rather than the current constant `user` ID. Display names are bounded and treated as untrusted metadata; an open ID or other stable identifier is the fallback.

Provider dispatch retains the original user text in audit/history, supplies the complete source metadata, and sets `idempotencyKey` to the Feishu source message ID. To make the active speaker unambiguous across all providers, the provider-facing input uses the existing human-source envelope with a bounded, JSON-quoted display label and `sourceSurface=feishu-group`; it does not treat the display name as instructions. Attachments continue through the existing validated attachment path.

Alternatives considered:

- Separate provider conversations per member were rejected because they break shared context.
- Prefixing the stored user text with an arbitrary display name was rejected because it pollutes the canonical message and increases prompt-injection ambiguity.
- Depending only on ledger metadata was rejected because not every provider exposes that metadata to the model context.

### 4. Reuse the inbound envelope and resource pipeline without a protocol version bump

No new field is required in `vo.feishu-chat.inbound/v1`: `chatType`, `mentions`, `resources`, thread/reply identifiers, and sender data already carry the required facts. The Node normalizer will preserve the sender fields it currently has but the Python adaptation drops, and the Python policy will read `mentions[].isBot`. Avoiding a new envelope shape keeps durable spooled v1 messages readable across restart and rollback.

Mentioned text is dispatched after SDK bot-mention removal. A rich `post` containing an accepted bot mention and image resource is adapted to the existing image path; a bare image without bot-mention evidence remains non-triggering. Image download keeps the current size, path, MIME, timeout, and attachment validation. Files and other content types receive a durable ignored outcome without Agent execution.

Alternatives considered:

- Adding `mentionedBot` to v1 was rejected because the validator rejects unknown fields and an old server could not replay a new-worker spool during rollback.
- Bumping to v2 was rejected because existing structured mention data is sufficient and a version migration adds no product value.

### 5. Reply to the source message and preserve Feishu thread placement

Private chat continues to use its current send operation. Group completion uses the worker's existing authenticated `reply` command with the source message ID and originating chat ID. `replyInThread` is true when the inbound message has a thread/root context and false for an ordinary flat group message. No fallback may redirect content to private chat or another group. If the reply target is revoked or Feishu rejects the operation, VO preserves the Agent result and records the classified delivery failure.

Reactions and temporary receipt behavior remain best-effort and scoped to the source message. They do not determine whether the Agent result is durable.

Alternatives considered:

- Always sending a new group message was rejected because replies could fall out of an existing topic and lose the trigger association.
- Reusing private-chat send behavior for all cases was rejected because it cannot preserve thread semantics.

### 6. Persist group audit records but make office visibility an explicit invariant

Group channel and communication records use `sourceSurface=feishu-group`, `sourceLabel=Feishu Group`, `chatType=group`, and `visibleInOffice=false`. Private rows keep `feishu-dm`, `Feishu DM`, and their existing visibility. A dedicated `_comm_is_feishu_group` classification based on structured metadata/source surface, not a conversation-prefix substring alone, will be used at every projection boundary.

The communication-ledger synchronizer persists group request, reply, and delivery outcomes for audit and idempotency but does not call `_publish_feishu_chat_comm_event` for them. The SSE replay scanner also excludes group-classified rows, preventing reconnect from reintroducing events that were intentionally not published. Normalized history already rejects `visibleInOffice=false`; it will additionally have focused group-classification tests so a future visibility default cannot leak group rows. Private invisible delivery events continue to publish their existing invalidation signal, so the filter must be group-specific rather than a blanket `visibleInOffice` check.

Alternatives considered:

- Omitting group communication records entirely was rejected because delivery diagnosis, durable source-message reconciliation, and sender audit would be lost.
- Filtering only in the frontend was rejected because initial history, pagination, reconnect replay, legacy history surfaces, and other consumers could still leak rows.
- Suppressing every invisible Feishu SSE event was rejected because private delivery invalidations are intentionally invisible records that refresh visible private replies.

### 7. Keep source-message idempotency and bounded concurrency end to end

The source message ID remains the durable business key in the channel audit and communication ledger and is also passed as the provider `idempotencyKey`. The existing double-checked Python conversation lock prevents concurrent same-group duplicates; the worker spool retains unacknowledged envelopes across restart. Completion lookup and reply lookup remain scoped by the source ID and group conversation. A duplicate must return the recorded outcome without another provider dispatch or outbound reply.

The existing worker bounds remain unchanged: 16 active callbacks, per-chat depth 20, one normalized message per batch, and durable-spool pressure disconnect/recovery. Non-mentioned group traffic is dropped by the SDK policy before these bounds. Status counters will distinguish SDK `no_mention`, VO group-disabled/non-human/invalid-mention decisions, accepted group turns, duplicates, Agent failures, delivery failures, and queue/spool pressure without logging message text or full member tables.

The implementation must add a regression for a restart boundary where an accepted source ID is already durable. If existing bounded record lookup cannot prove that duplicate without rescanning unbounded history, the implementation task must add a compact durable source-ID index under the existing status directory; it must not replace correctness with a full JSONL scan on every message.

Alternatives considered:

- Trusting the SDK's one-minute in-memory dedup was rejected because it does not survive restart.
- Serializing all groups through one lock was rejected because one slow Agent would block unrelated groups.
- Unbounded callback queues or history scans were rejected because a busy group could exhaust memory or make admission O(N).

### 8. Preserve current external contracts and isolate rollout

The management API changes only add `groupChatEnabled` and the dynamic allowed-chat projection. Existing credentials, representative Agent selection, transport selection, private bindings, route paths, worker authentication, notification/card-action application, and provider request contracts remain compatible. Group records are additive and old code ignores the new config field; their `visibleInOffice=false` marker prevents old normalized history from rendering them after rollback.

No database migration is required. Existing private histories remain unchanged, and group conversation state begins only after the switch is enabled. Disabling the switch rejects new group callbacks before provider dispatch; an already executing turn is allowed to finish and record its delivery outcome so the state is not left ambiguous.

## Risks / Trade-offs

- **[Security: membership is a broad trust grant]** Any human in a group containing the bot can invoke the representative Agent and its configured tools → Default the switch off, show an operator warning, preserve sender audit, keep provider approval/sandbox policy unchanged, and require explicit mention.
- **[Security: bot or forged mention loop]** Another bot or crafted callback could attempt repeated invocation → Require SDK identity-backed mention data, reject senders not positively identified as human, keep callback authentication, and record bounded policy counters.
- **[Privacy: group content leaks into VO chat]** Generic Feishu classification currently merges across conversation IDs and SSE replay scans all Feishu rows → Use the dedicated group source surface, `visibleInOffice=false`, and server-side exclusions at ledger publication, replay, normalized history, legacy history, and pagination boundaries.
- **[Consistency: member-derived conversation identity]** Reusing the private formula would fork one group into per-member histories → Use a group-only deterministic namespace and tests across members, groups, providers, and restart.
- **[Consistency: crash between Agent effect and completion record]** A replay could repeat an external provider effect → Pass the source message ID as provider idempotency, retain the durable spool/audit state, test restart recovery, and add a compact durable index if current lookup is insufficient.
- **[Stability: a busy group occupies callback capacity]** Long Agent turns can fill per-chat and global queues → Preserve the bounded queue/spool controls, expose pressure counters, reject overload without merging messages, and keep cross-group concurrency independent.
- **[Compatibility: envelope change breaks spool rollback]** Adding new fields to strict v1 validation would make old-server replay fail → Derive mention proof from existing `mentions` and keep the v1 shape.
- **[Compatibility: legacy transport lacks reliable normalized bot identity]** Enabling groups on the legacy receiver could accept ambiguous mentions → Require the Node SDK transport for group enablement; rollback intentionally restores private-only service.
- **[Delivery: replies leave a topic or target disappears]** A generic send loses context and a revoked message can fail → Use the existing reply command with thread metadata, preserve the Agent result, and classify delivery failures.
- **[Observability: ignored traffic creates a log storm]** Busy groups may contain many ordinary messages → Count policy rejections in worker status, rate-limit summaries, and avoid per-message content logs for `no_mention`.

## Migration Plan

1. Ship worker, server, configuration, history-filter, and tests with `groupChatEnabled=false`. Verify private chat, notification/card actions, status, worker spool replay, and current Feishu SSE behavior are unchanged.
2. Enable the switch only in a disposable/test Feishu group on `channel-sdk-node`. Verify explicit mention text, rich-post image, non-mentioned traffic, `@all`, bot sender, multiple humans, threads, duplicate delivery, rapid same-group messages, concurrent different groups, Agent failure, outbound failure, reconnect, process restart, and private/group isolation.
3. Confirm through API/browser acceptance that group rows remain absent on initial VO history load, pagination, live SSE, SSE reconnect replay, and legacy agent-chat history while private Feishu rows still refresh normally.
4. Observe accepted/ignored/duplicate/failure counts, callback/queue/spool pressure, Agent latency, and delivery errors before enabling the intended trusted groups.
5. To roll back behavior, set `groupChatEnabled=false`; new group events are ignored while private chat continues. Allow already-running turns to finish, then reconcile their recorded outcomes. If code rollback is required, stop the worker, restore the prior release, and restart through `start.sh`; no history transformation is required.

## Open Questions

None. Product trust, trigger, participant, context, content, and VO-visibility semantics were explicitly confirmed before this design.
