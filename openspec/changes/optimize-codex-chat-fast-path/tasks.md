## 1. Baseline and Characterization

- [x] 1.1 Add a deterministic warm continued-Codex-chat performance harness with 10 warm-ups and at least 100 measured turns, record browser/backend stage boundaries, p50/p95/max/errors and operation counts, and save failing-before baseline evidence for working feedback, first native event, first fragment, terminal tail, activity JSON writes, communication progress rewrites, and reader callback duration.
- [x] 1.2 Add characterization coverage for existing Codex run acceptance, same-Agent busy behavior, thread resume/new-thread fallback, activity polling, Provider SSE event names/order, approval, cancellation, final reply recovery, cold start, and non-Codex Provider behavior so the flag-off compatibility contract is executable before implementation.

## 2. Guarded Fast-Path Foundation

- [x] 2.1 Add validated startup configuration and diagnostics for `VO_CODEX_CHAT_FAST_PATH_ENABLED`, `VO_CODEX_MAX_CONCURRENT_TURNS`, and the 33-100 ms coalescing bounds; keep the fast path off by default, clamp capacity to 1-4, fail invalid configuration to the legacy path, and test sanitized status output.
- [x] 2.2 Introduce an isolated Codex event fast-path service with bounded event classification, one-time ingress redaction, per-conversation live sequence state, active-scope lifecycle, content-free counters/timestamps, and no new run or SSE state machine; prove the disabled service does not alter existing callbacks or payloads.

## 3. Durable and Transient State Separation

- [x] 3.1 Make accepted user messages, stable approval requests/resolutions, final replies, and reply-less failure/cancellation/terminal outcomes idempotently durable in their confirmed existing authorities, keyed by stable request/run/turn/approval identity; add duplicate, partial-write, restart, and durable-write-failure tests.
- [x] 3.2 Route transient Codex reasoning, delta, tool-progress, and replaceable progress activity through the bounded in-memory live view when the fast path is enabled, eliminate per-native-event activity JSON and communication-ledger full rewrites, preserve legacy activity/polling compatibility, and verify process restart may lose transient data without losing durable state.

## 4. Bounded Streaming Coalescing

- [x] 4.1 Implement and unit-test the single-dispatcher per-run coalescer: first-fragment bypass, adaptive 33-100 ms windows, ordered text reconstruction, 256-scope/200-fragment/64-KiB-per-bucket/16-MiB-global bounds, forced flush, direct bypass, cleanup, and deterministic clocks.
- [x] 4.2 Integrate coalescing before Provider journal publication, flush ordering barriers for approval/tool transitions/reset/replacement/cancel/failure/completion/final events, preserve critical event names and attribution, and verify SSE reconnect/replay contains no missing, duplicated, cross-conversation, or reordered content.

## 5. Terminal Completion Fence

- [x] 5.1 Replace the unconditional 200 ms Codex terminal sleep with operation callback entry/exit accounting and a bounded terminal-drain fence; cover prior callbacks, malformed late notifications, post-terminal metrics, timeout, runtime exit, cancellation, approval continuation, result augmentation, and prove successful turns have no fixed tail delay.

## 6. Conversation Isolation and Bounded Provider Concurrency

- [x] 6.1 Add a deterministic app-server multiplexing fixture that interleaves two different native threads and verifies request responses, notifications, activity, approvals, cancellation, terminal results, and cleanup never cross-deliver; retain capacity 1 as the required result if this proof fails.
- [x] 6.2 Replace Agent-wide Codex admission with `(agent, conversation)` admission, replace the client-wide run lock with per-thread ordering plus a non-blocking bounded semaphore, preserve same-conversation busy and archived-thread recovery semantics, expose distinct conversation/capacity busy counters, and verify concurrency 1, proven concurrency 2, capacity exhaustion, timeout, and runtime restart.

## 7. End-to-End Timing and User-Visible SLOs

- [x] 7.1 Instrument content-free backend timestamps and histograms for accepted request, run reservation, Provider request, first native event, first displayable fragment, journal publication, SSE write, Provider terminal, durable terminal commit, fence wait, coalescer pressure, and busy reasons; add redaction, bounded-cardinality, and instrumentation-overhead tests.
- [ ] 7.2 Add browser-side run-correlated measurement for optimistic working feedback, first matching native event, first fragment, and first text without comparing browser and server clocks; verify warm working-feedback p95 is at most 200 ms, first-native-event p95 is at most 1 second, first text is reported separately, and the first fragment is not delayed by batching.

## 8. Compatibility, Rollout, and Final Evidence

- [ ] 8.1 Run and fix focused Python/JavaScript/static/browser regressions for Codex API fields/statuses, conversation/thread mapping, history, SSE/polling reconciliation, approval, cancellation, terminal dedupe, restart recovery, cold/new-thread behavior, attachments, archived-thread recovery, and shared Provider infrastructure with the flag both off and on.
- [ ] 8.2 Document startup-only configuration, capacity and memory bounds, metrics interpretation, code-deployed/flag-off rollout, concurrency-1 and concurrency-2 gates, stop/drain/cancel/discard/restart rollback, and perform a rollback rehearsal proving durable history/thread/approval/final state remains readable without data repair.
- [ ] 8.3 Re-run the exact baseline harness and app-server concurrency fixture, publish post-change and comparison evidence with sample counts and call/write counts, prove all confirmed SLO/capacity/compatibility/security gates or keep unproven concurrency at 1, run strict OpenSpec validation, and record every environment-gated or unverified real-Provider check without claiming it passed.
