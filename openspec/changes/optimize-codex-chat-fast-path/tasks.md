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
- [x] 7.2 Add browser-side run-correlated measurement for optimistic working feedback, first matching native event, first fragment, and first text without comparing browser and server clocks; verify warm working-feedback p95 is at most 200 ms, first-native-event p95 is at most 1 second, first text is reported separately, and the first fragment is not delayed by batching.

## 8. Compatibility, Rollout, and Final Evidence

- [x] 8.1 Run and fix focused Python/JavaScript/static/browser regressions for Codex API fields/statuses, conversation/thread mapping, history, SSE/polling reconciliation, approval, cancellation, terminal dedupe, restart recovery, cold/new-thread behavior, attachments, archived-thread recovery, and shared Provider infrastructure with the flag both off and on.
- [x] 8.2 Document startup-only configuration, capacity and memory bounds, metrics interpretation, code-deployed/flag-off rollout, concurrency-1 and concurrency-2 gates, stop/drain/cancel/discard/restart rollback, and perform a rollback rehearsal proving durable history/thread/approval/final state remains readable without data repair.
- [x] 8.3 Re-run the exact baseline harness and app-server concurrency fixture, publish post-change and comparison evidence with sample counts and call/write counts, prove all confirmed SLO/capacity/compatibility/security gates or keep unproven concurrency at 1, run strict OpenSpec validation, and record every environment-gated or unverified real-Provider check without claiming it passed.

## 9. Push Review Remediation

- [x] 9.1 Make conversation admission lock ownership race-free and prevent one timed-out concurrent request from restarting the shared app-server underneath unrelated active turns; add deterministic race and cross-turn timeout isolation tests.
- [x] 9.2 Contain durable approval-write failures inside the affected operation without terminating the JSONL reader, and retain terminal operations from the actual terminal path so post-terminal diagnostics do not depend on reasoning events.
- [x] 9.3 Preserve per-run fragment order when coalescer bounds force direct bypass, treat nested `activity.replace` snapshots as barriers, and add reconstruction tests for both pressure and replacement paths.
- [x] 9.4 Restrict fast-path SSE telemetry to Codex runs/conversations, clean review-artifact whitespace, and re-run focused, full, performance, concurrency, rollback, and strict OpenSpec verification before declaring the review findings resolved.

## 10. Second Push Review Remediation

- [x] 10.1 Correlate app-server notifications with the active turn identity so late notifications from a completed turn cannot mutate a later turn on the same thread, and make the terminal callback fence bounded even when the terminal callback itself blocks; add deterministic regressions for both paths.
- [x] 10.2 Commit final-reply durability before the matching terminal outcome, clear recovered write errors after a successful retry, and ensure the public terminal status always agrees with the durable authorities; add durable failure and recovery tests.
- [x] 10.3 Preserve stable-ID idempotency beyond the communication-history display window using a durable lookup that does not duplicate old approval or terminal operations; add a restart-style test with more than 1,000 later records.
- [x] 10.4 Measure browser first-native latency only from matching native Agent events and retain working-feedback correlation after submission tokens are bound to run IDs; add synthetic-start and animation-frame ordering regressions.
- [x] 10.5 Re-run focused Python/JavaScript suites, full repository tests, the deterministic performance/concurrency/rollback gates, strict OpenSpec validation, and update acceptance evidence before declaring the second push-review findings resolved.

## 11. Terminal Callback Drain Remediation

- [x] 11.1 Keep same-conversation admission closed after a terminal fallback until the late callback has actually drained and the current turn has finished durable finalization; preserve bounded reader/response behavior and add deterministic cross-turn ordering coverage.

## 12. Accepted Run Retry Remediation

- [x] 12.1 Prevent any accepted Codex run from falling back to the blocking chat endpoint after SSE, terminal, or durable failure; recover the accepted run/history and surface an explicit error without re-executing the prompt, while retaining pre-acceptance compatibility fallback and adding a static control-flow regression.

## 13. Terminal Durability Finalization Remediation

- [x] 13.1 Separate bounded reader release from durable terminal completion so a slow successful reply write cannot be reported as failed, and guarantee finalization signaling, active-state cleanup, and same-conversation admission release on every terminal exception path; add deterministic regressions for slow reply persistence and exceptional finalization.

## 14. Turn Identity Response Race Remediation

- [x] 14.1 Treat the `turn/start` response as the authoritative turn identity, buffer native notifications that arrive before that response within a fixed bound, replay only matching notifications in source order, and add a deterministic regression where a stale resumed-thread notification precedes the new turn response.
