# Section 6 whole-group code review

## Verdict

Section 6 is accepted for progression to Section 7. All live Provider run and conversation routes now use `ProviderSSETransport`; repositories and journals expose snapshots, indexed replay, and wait operations but no longer perform HTTP response selection or active transport framing.

## Ownership and compatibility review

- The transport adapter owns HTTP status/headers, `Last-Event-ID` and `after` parsing, `id/event/data` frames, ten-second comments/heartbeat events, flushes, and disconnect handling.
- `ProviderRunRepository` remains the in-memory run authority and `ProviderEventJournal` remains the global monotonic cursor, terminal fence, bounded retention, and run/conversation index authority.
- Missing-run and invalid-scope response bodies, initial provider snapshots, active-run projection, pending approval replay, recovered progress, terminal replay/fallback, CORS/cache headers, and frontend event names retain their compatibility contracts.
- Disconnecting a run or conversation stream does not start, cancel, complete, clear, or otherwise mutate provider work.
- Restart creates empty run/event authorities by design. Existing JSON histories and native IDs remain independently readable through conversation ports.
- Gateway/WebSocket and OpenClaw queued delivery semantics are unaffected; Project/Meeting provider ports remain outside SSE ownership.

## Confirmed findings resolved

1. **`ProviderRunBridge` still executed HTTP/SSE framing and cursor loops.** Runtime run and conversation routes now call a dedicated transport adapter over repository/journal APIs.
2. **Run replay did not consume `Last-Event-ID`.** The transport now uses the maximum valid header/query cursor and retains exact terminal frames.
3. **Terminal fallback and recovery-only payloads could bypass the journal sanitizer.** Every transport frame now passes through the same bounded sensitive-value/path sanitizer before serialization.
4. **A pending-approval or history-recovery read failure could terminate the whole conversation stream.** These optional recovery sources now degrade independently while indexed live event replay continues.
5. **Restart/late-callback behavior lacked direct transport coverage.** Tests prove run/event state is non-durable, persisted conversation state remains visible, and a stale generation cannot recreate or overwrite a cleared/reused run.
6. **Provider failure isolation was only implicit.** A malformed failing provider and an unrelated healthy provider now execute concurrently and reach independent terminal events.
7. **Indexed replay still deep-copied payloads while holding the journal lock.** The journal now selects immutable event references under lock and performs copy-on-read after release, preserving caller isolation while bounding publisher/replay contention.

## Regression and performance evidence

- Isolated HTTP/SSE/repository/coordinator/provider/WebSocket/Feishu Python group: **226 passed**, with two existing `lark_oapi` deprecation warnings.
- Direct script suites for chat history/session, Provider boundaries, Hermes Desktop/Platform/plugin, and OpenClaw auth passed.
- Browser-static/JavaScript compatibility checks: **12/12 passed**.
- Characterization manifest: **21/21 passed**.
- Fixed 1/20/100 run and 10/1,000/4,000 event comparison passed every call-count, retention, replay-count, and p95 bound. The 4,000-event/100-scope fixture replays exactly 40 indexed target events; reference selection held the lock for approximately 1.75 microseconds in that fixture, while the 4,000-event single-run extreme remained below 0.09 ms of measured selection lock time. Deep copying occurs after release.
- Python compilation, generated-inventory reproducibility, `git diff --check`, and strict OpenSpec validation passed.
- CDP UI/performance tests require the browser candidate and are intentionally deferred to Section 8, where the application will be started only through `start.sh --browser`.

## Deferred cleanup already scoped by Section 7

- Compatibility-only `ProviderRunBridge` stream method bodies and the unreachable legacy Hermes Desktop SSE executor remain as zero-runtime-caller code until the single final caller-inventory cleanup. Live routes already bypass them; Section 7 removes the symbols and updates the approved delegate inventory together.
