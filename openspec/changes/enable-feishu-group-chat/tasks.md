## 1. Baseline and Rollout Controls

- [x] 1.1 Add characterization tests for the current private-only configuration, group rejection, private conversation identity, sender binding, text/image handling, communication-ledger visibility, normalized history, Feishu SSE publish/replay, notification isolation, and Node/legacy transport behavior; save the reproducible baseline command and result under this change.
- [x] 1.2 Add the default-off `feishu.chatApp.groupChatEnabled` setting and `VO_FEISHU_GROUP_CHAT_ENABLED` override, preserve it across unrelated settings saves, project dynamic `allowedChatTypes`, reject group enablement on legacy transport, and expose the switch plus trust warning in the existing Feishu settings/status UI with focused API/UI tests.

## 2. Worker Policy and Inbound Identity

- [x] 2.1 Configure the Node SDK policy explicitly for open private chat, membership-trusted groups, required direct bot mention, blocked `@all`, zero-delay single-message batching, and unchanged bounded queues; extend worker tests for accepted group mentions and SDK `no_mention`, `mention_all_blocked`, and bot-loop/policy counters without per-message content logging.
- [x] 2.2 Preserve bounded sender name/type/bot metadata and structured `mentions[].isBot` through Node normalization, strict v1 validation, durable spool replay, and Python envelope adaptation without changing the v1 shape; test restart/rollback compatibility and prove forged text `@`, missing bot identity, and non-human senders cannot reach the Agent.

## 3. Group Admission, Context, and Delivery

- [x] 3.1 Implement pure group admission and identity helpers in the Feishu channel adapter: default-off policy, Node-transport requirement, human-sender validation, identity-backed mention validation, stable ignored reasons, `feishu-group:<digest>` derivation from chat ID only, private-ID preservation, group source metadata, and stable sender attribution; cover same-group cross-member continuity plus cross-group/private isolation with focused unit tests.
- [x] 3.2 Route accepted group text and rich-post image turns through the representative Agent with original audit text, bounded untrusted speaker metadata, source-message provider idempotency, existing attachment protections, and all four provider paths; verify unsupported files, empty prompts, image download failure, representative-Agent absence/switch, and provider failure do not corrupt group context.
- [x] 3.3 Add a group-only outbound reply port using the existing authenticated worker `reply` command, preserve flat-group versus topic/thread placement, keep private send behavior unchanged, and record successful message identity or classified delivery failure without redirect fallback; test reaction/receipt cleanup, revoked targets, timeouts, and wrong-chat prevention.

## 4. Durability, Ordering, and Capacity

- [x] 4.1 Audit the existing bounded channel-record and communication-ledger lookup against cross-restart source-message idempotency; add a compact atomic status-directory source-ID index only if required, then fault-test duplicate delivery before/after acknowledgement and restart so one source message creates at most one provider turn and one authoritative reply outcome without an O(N) hot-path scan.
- [x] 4.2 Prove deterministic same-group ordering and independent cross-group progress under the existing conversation locks, global callback limit 16, per-chat depth 20, spool pressure/full behavior, slow Agent, callback retry, and shutdown/restart; add observable accepted/ignored/duplicate/Agent/delivery/pressure counters and verify bounded memory, threads, queue, spool, and rate-limited logs.
- [x] 4.3 Add provider-neutral expired-session recovery orchestration to the shared conversation bridge, canonicalize bounded completed turns from one Feishu group shard without replaying the current message or operational audit rows, wire Codex archived-thread recovery through it, persist the replacement native ID, and test no-history fallback plus cross-group isolation.

## 5. Audit, History, and SSE Isolation

- [x] 5.1 Persist group request, reply, and delivery audit/communication rows with stable member references, `feishu-group` source metadata, and `visibleInOffice=false`; add structured group classification and tests proving records remain diagnosable/idempotent while private ledger fields and notification/card-action records remain unchanged.
- [x] 5.2 Exclude group-classified rows from normalized history initial load, pagination, caches, legacy agent-chat merging, Feishu SSE live publication, replay, and reconnect recovery while preserving existing private request/reply visibility and invisible private-delivery invalidations; add server and history-store regressions for mixed private/group data and representative-Agent filtering.
- [x] 5.3 Add deterministic browser acceptance that opens the representative Agent chat, injects accepted group request/reply/delivery records and SSE reconnect conditions, proves no group bubble or refresh is produced, and simultaneously proves private Feishu events still refresh and render exactly once.

## 6. Security and Compatibility Regression

- [x] 6.1 Add end-to-end security tests for forged/unauthenticated worker callbacks, structured-mention tampering, bot/system/anonymous/unknown senders, display-name prompt injection, oversized or unsafe image resources, cross-group identifiers, and secret canaries; verify no unauthorized Agent/outbound effect and no credential or group-message leakage in logs, status, API responses, history, or SSE.
- [x] 6.2 Run and fix the focused Node/Python Feishu suite covering worker protocol/spool/status, configuration and UI, private chat, group text/image, all providers, idempotency, ordering, capacity, ledger/history/SSE isolation, outbound failures, notification/card-action isolation, and legacy rollback; record exact commands, results, failures, and intentional compatibility changes in verification evidence.

## 7. Rollout, Real-Tenant Acceptance, and Final Verification

- [x] 7.1 Update the operator documentation for the default-off group switch, trusted-membership warning, Node-only requirement, status/counter interpretation, pressure recovery, disable semantics, in-flight reconciliation, and code/legacy rollback; perform an offline rehearsal from switch-off through test enablement, injected failure, disablement, restart, and rollback without history migration.
- [ ] 7.2 Perform redacted real-tenant acceptance in a disposable trusted group for human mention text (including null optional mention identities observed in production events), rich-post image, ordinary non-mentioned traffic, another-member mention, `@all`, multiple humans, multiple groups with digest-named per-group audit shards, private/group interleaving, topic reply, duplicate, rapid messages, Agent/delivery failure, reconnect, restart, status, VO-history/SSE absence, private-chat compatibility, switch disablement, and legacy rollback; do not broaden activation until every scenario passes.
- [x] 7.3 Run the relevant full Python, Node, static, browser, Provider, Project, Meeting, notification, Feishu, history, SSE, security, concurrency, startup/rollback, and OpenSpec strict-validation suites; document all results and unresolved environment-gated checks, resolve every change-caused regression, and prepare the specification-linked evidence for the test-result confirmation gate.
