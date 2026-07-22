## 1. Freeze Compatibility and Defect Baselines

- [x] 1.1 Create a four-Provider characterization manifest and evidence snapshot for standard chat history, Project Execution workflow chat, Provider SSE, and refresh recovery, recording canonical fields, route/status/error contracts, cursor behavior, event names/order, scope isolation, and current performance bounds without recording message or reasoning content.
- [x] 1.2 Define and automate the allowed-difference policy: all existing product behavior must remain unchanged except the confirmed Claude Code workflow-history selection, Hermes completed-reasoning state, OpenClaw structured-block consistency, and Codex duplicate reasoning ownership corrections; make unexplained DTO, status, order, event, history, interaction, or visual-behavior differences fail the comparison.

## 2. Build the Canonical Timeline Core

- [x] 2.1 Add `app/services/conversation_timeline.py` with bounded scope/query/item/page contracts, lifecycle normalization, one reasoning visibility policy, and delta/replace/boundary/deduplication state; add focused unit tests for every Provider alias, placeholder, terminal state, empty reasoning, replay, and malformed input.
- [x] 2.2 Implement stable scoped identity, versioning, Provider-sequence-first ordering, conservative live/durable matching, deterministic merge, cursor paging, and copied public results in the timeline service; test missing IDs, fallback collisions, duplicate text, equal/missing timestamps, overlapping sources, repeated reads, and cross-conversation/attempt rejection.
- [ ] 2.3 Add injected, read-only timeline source ports and focused source-reader helpers for Provider history, office communication history, live event/activity snapshots, OpenClaw structured blocks, session metrics, and active state; verify bounded reads, no Provider launch/history writes, source failure isolation, and no dependency on `app/server.py`.

## 3. Migrate Standard Chat History Without Product Drift

- [ ] 3.1 Move existing provider-neutral history normalization, source merge, paging, cursor, and bounded cache responsibilities behind `ConversationTimelineService`, leaving `/api/chat/history` as a thin compatibility delegate; preserve exact supported request fields, status/error semantics, cursor format, response fields, page limits, sender attribution, attachments, tools, approvals, Feishu-visible history, and session metrics.
- [ ] 3.2 Run the frozen standard-chat old/new comparison for Codex, Claude Code, Hermes, and Gateway/OpenClaw and update compatibility tests so cached switching, older-page loading, bounded DOM history, Markdown/media/tool/approval rendering, optimistic reconciliation, bottom-follow behavior, and refresh recovery show no product-visible change.

## 4. Migrate Project Execution Scope and Provider Reads

- [ ] 4.1 Add `app/services/project_workflow_chat.py` to resolve project, task, active attempt/review, Agent, Provider, conversation, phase, and session-active scope through injected readers; delegate `_handle_workflow_chat()` to it while preserving the existing workflow-chat route, response envelope, polling behavior, empty/not-found semantics, task selection, and project lifecycle behavior.
- [ ] 4.2 Route Claude Code and Hermes Project Execution timelines through the shared service; add failing-before regression evidence and tests proving Claude Code uses its attempt-scoped Claude history rather than OpenClaw storage and completed Hermes reasoning is terminal, while preserving current successful Hermes/Claude messages, tools, errors, and conversation isolation.
- [ ] 4.3 Route OpenClaw Project Execution timelines through the shared OpenClaw structured-content reader; add failing-before regression evidence and tests for text, supported media, tool call/result/error, Provider-supplied reasoning, gateway-prefixed session lookup, active state, malformed JSONL, tail bounds, and strict attempt/session isolation without changing current visible summaries outside the confirmed corrections.
- [ ] 4.4 Route Codex Project Execution history and eligible fast-path/live activity through the shared service; add failing-before regression evidence and tests for delta, boundary, replace, duplicate event, placeholder filtering, terminal settlement, timeout recovery, durable/transient separation, tool ordering, and attempt isolation while preserving Codex fast-path latency and durability contracts.

## 5. Unify Live Reconciliation Without UI Redesign

- [ ] 5.1 Add a bounded canonical `timelineItem` projection to existing Provider SSE payloads for all four Providers without removing or renaming current events or fields; verify Last-Event-ID replay, heartbeat, history recovery, approval, tool, terminal, malformed-event, and cross-conversation behavior remains compatible.
- [ ] 5.2 Update `ChatHistoryStore` and `ChatWindow` data plumbing to reconcile canonical `timelineItem` values instead of independently deriving history identity, ordering, status, tools, and reasoning; retain current visual components, labels, expansion behavior, streaming feedback, typing indicators, approval actions, scrolling, cache bounds, and Provider-specific presentation.

## 6. Remove Parallel Authorities

- [ ] 6.1 After all four Provider parity suites pass, remove `_codex_reasoning_events_to_chat_messages()`, Provider parsing from `_wf_get_task_session_messages()`, the duplicate project OpenClaw transcript parser, and obsolete server compatibility helpers; prove both public routes still delegate to one timeline owner.
- [ ] 6.2 Remove obsolete client `mergeLiveHistoryRecord()` canonical mappings and the client-side Codex reasoning accumulator where canonical projection now owns those decisions; retain only presentation state and a temporary compatibility fallback if still required by an explicitly supported old-server window, then remove that fallback before final acceptance.
- [ ] 6.3 Add static boundary checks confirming timeline and project workflow services do not import `server.py`, Provider-native parsing is not duplicated by consumers, no second runtime authority remains, and legacy entry points contain only validation, wiring, transport adaptation, and compatible field mapping.

## 7. Security, Performance, and Failure Verification

- [ ] 7.1 Verify malformed/unavailable source isolation plus allowlisting, size/depth bounds, secret/header/token redaction, unrestricted-path suppression, safe OpenClaw session resolution, and content-free/rate-limited diagnostics across all timeline sources and public responses.
- [ ] 7.2 Measure fixed 10/50/500/1,000 source-record and 0/1/4,000 live-event fixtures before and after migration; record candidates, normalized items, dedupe count, cache hit/miss, response bytes, lock-held work, median, and p95, and reject increased Provider calls/writes, unbounded scans, cache growth, or material regression in chat/project read latency.
- [ ] 7.3 Exercise partial-source failure, corrupt history, stale progress, SSE disconnect/reconnect, application restart, concurrent polling/refresh, cache eviction, and one-Provider-unavailable scenarios; prove durable terminal/message recovery, truthful transient loss, deterministic repeated reads, and failure containment.

## 8. Full Regression, Rollback, and Acceptance Evidence

- [ ] 8.1 Run the complete regression scope for chat history/API/store/UI, Project Execution lifecycle and polling, all Provider history/run/SSE/event/conversation suites, Codex fast path, approvals/cancellation, Feishu-visible history, HTTP contracts, startup, and static browser checks; document every failure and allow no unexplained product-visible difference.
- [ ] 8.2 Perform per-Provider rollback rehearsals during the compatibility-delegate stage and a final prior-revision rollback rehearsal after legacy removal, proving rollback requires no data repair, old code reads unchanged history/session metadata, and projection switching never launches Provider work or mutates conversation history.
- [ ] 8.3 Produce the final Provider consistency matrix and verification evidence mapping every specification scenario to automated commands/results, explicitly listing the four intentional bug corrections, unchanged product-behavior evidence, performance comparison, security/failure results, residual manual checks, and any accepted limitations.
