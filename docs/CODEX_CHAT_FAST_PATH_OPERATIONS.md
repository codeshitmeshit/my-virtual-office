# Codex Chat Fast Path Operations

This runbook covers deployment, observation, capacity gating, and rollback of the Codex-only chat fast path. The controls are startup-only; changing them requires a controlled process restart.

## Configuration

| Variable | Default | Valid range | Purpose |
| --- | ---: | ---: | --- |
| `VO_CODEX_CHAT_FAST_PATH_ENABLED` | `0` | boolean | Enables transient live-view routing and stream coalescing. Invalid configuration fails closed to the legacy path. |
| `VO_CODEX_MAX_CONCURRENT_TURNS` | `1` | `1`–`4` | Bounds active app-server turns. Same-conversation turns remain serialized. |
| `VO_CODEX_STREAM_COALESCE_MIN_MS` | `33` | `33`–`100` | Minimum adaptive window for compatible fragments after the immediate first fragment. |
| `VO_CODEX_STREAM_COALESCE_MAX_MS` | `100` | `33`–`100` and not below min | Maximum adaptive fragment window. |

The sanitized runtime status reports `requestedEnabled`, effective `enabled`, `valid`, `startupOnly`, capacity, coalescing windows, and non-secret validation issue codes. Confirm the effective values after every restart. Do not treat an environment change without a restart as applied.

## Capacity and memory bounds

- Provider concurrency is non-blocking and bounded to 1–4 active turns. A second turn for the same `(agent, conversation)` returns conversation-busy; a different conversation beyond capacity returns capacity-busy.
- The first displayable fragment bypasses coalescing. Later compatible fragments use one dispatcher with at most 256 buckets, 200 fragments or 64 KiB per bucket, and 16 MiB globally. Pressure forces a flush or direct bypass; it must not drop a critical event.
- Live Codex state is bounded to 4,096 scopes. The shared Provider journal retains 4,000 events, and run results expire under the existing repository retention policy.
- Backend timing retains at most 1,024 runs and 2,048 samples per fixed metric. Browser timing retains 200 bound runs and 100 early-event correlations. Identifiers are digested or run-correlated; message and reasoning content is not recorded.

## Metrics interpretation

Use backend `fastPathRuntime.telemetry` and browser `getCodexChatTimingDiagnostics()` together, but never subtract browser timestamps from server timestamps.

- `accepted_to_first_native_event_ms`: Provider/app-server responsiveness. Warm p95 gate: at most 1 second.
- `accepted_to_first_displayable_fragment_ms`, `accepted_to_journal_published_ms`, and `accepted_to_sse_written_ms`: callback, batching, journal, and transport stages. A gap after first native isolates the local delivery stage.
- `terminal_tail_ms` and `terminal_fence_wait_ms`: terminal drain behavior. Normal success must not show a fixed 200 ms floor.
- `busyByConversation` versus `busyByCapacity`: same-conversation serialization versus global capacity pressure. Sustained capacity pressure is a rollout signal, not a reason to raise the bound without proof.
- Coalescer counters distinguish first-fragment bypass, buffered/coalesced fragments, forced/barrier/dispatcher flushes, and direct bypass. Rising forced flush or direct bypass indicates pressure; it is acceptable only if ordering and reconstruction remain correct.
- Browser `workingFeedbackMs`, `firstNativeEventMs`, `firstFragmentMs`, and `firstTextMs` share one browser-monotonic clock and correlate only by run ID. Warm working-feedback p95 must be at most 200 ms. First text is observational and is not covered by the first-native SLO.

All metrics are bounded and content-free. Never add prompts, replies, reasoning, credentials, approval content, raw Provider payloads, or unrestricted paths to diagnostics.

## Rollout gates

1. Deploy code with `VO_CODEX_CHAT_FAST_PATH_ENABLED=0` and capacity 1. Run the flag-off compatibility suite and compare baseline errors, fields, event names, history, approval, cancellation, and terminal outcomes.
2. Enable the flag in deterministic/staging tests at capacity 1. Require durable restart recovery, rollback rehearsal, ordered reconstruction, immediate first fragment, browser/backend SLOs, and no increased durable write counts.
3. Keep production capacity at 1 unless the app-server multiplexing fixture proves two different native threads can interleave responses, notifications, approvals, cancellation, terminal results, and cleanup without cross-delivery.
4. After that proof, stage capacity 2 on a limited cohort. Watch conversation/capacity busy counters, terminal fence timeouts, coalescer pressure, errors, and memory bounds before widening exposure.
5. Capacity 3–4 is configuration range, not an approved rollout target. It requires separate Provider evidence and capacity review.

Stop rollout on content/order loss, cross-conversation delivery, durable-write failure, history/thread mismatch, approval misrouting, terminal duplication, unexplained SLO regression, unbounded growth, or sensitive diagnostic content.

## Controlled rollback

1. Stop accepting new Codex runs at the ingress or remove the instance from traffic.
2. Inspect active runs. Let safe turns finish; explicitly cancel turns that cannot drain within the operational deadline.
3. Wait for terminal durable commits and the terminal fence. Confirm no active approvals or runs are left unresolved; record deliberate cancellations.
4. Stop the process. In-memory transient reasoning, deltas, tool progress, and coalescer buckets may be discarded after durable drain.
5. Set `VO_CODEX_CHAT_FAST_PATH_ENABLED=0`. Set `VO_CODEX_MAX_CONCURRENT_TURNS=1` for the conservative rollback posture. Restart the process.
6. Confirm sanitized status shows effective flag off. Read the existing history, conversation-to-thread mapping, approval request/resolution, final reply, and terminal outcome. No reverse migration or data repair is expected.
7. Run the flag-off compatibility suite and a continued message on the recovered conversation before returning the instance to normal traffic.

The automated rehearsal is:

```bash
.venv/bin/python -m pytest -q tests/test_codex_fast_path_rollback.py
```

It writes accepted user, approval request/resolution, final reply, terminal outcome, and thread mapping with the fast path enabled; replaces the runtime with a fresh flag-off live view; reads every durable surface; and asserts that recovery did not mutate any status file.
