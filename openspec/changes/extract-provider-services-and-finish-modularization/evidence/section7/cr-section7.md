# Section 7 whole-group code review

## Verdict

Section 7 is accepted for progression to release-readiness work. The final runtime ownership inventory contains one run repository, one event journal, one coordinator, one conversation service, and one approval service. No obsolete bridge registry, idempotency map, active-run projection, approval compatibility map, or per-run event queue remains in a Provider run path.

## Dependency and authority review

- `ProviderRunRepository` is the sole in-process run and idempotency authority; `ProviderEventJournal` is the sole event cursor, replay index, retention, and terminal-event authority.
- Provider adapters call capability ports and emit normalized adapter events. They do not mutate repository/journal internals.
- `ProviderSSETransport` only reads repository/journal/recovery projections and owns HTTP framing, cursor parsing, heartbeat, and disconnect behavior. Static boundary tests forbid business mutation in this delegate.
- Conversation/native-ID/history and approval state have one service boundary each. Existing persisted file formats and provider-native identifiers are preserved.
- OpenClaw remains queued-delivery only and creates neither synthetic run records nor SSE semantics.
- Pending app-server requests are bounded at 1,000 and pending Codex approvals at 100; capacity exhaustion fails closed before an untracked request is sent.

## Confirmed findings resolved

1. **Obsolete runtime authorities and orchestration helpers remained reachable as compatibility projections.** `ProviderRunBridge`, parallel run/idempotency views, legacy active-run maps, approval compatibility views, and the connection-owned Hermes Desktop SSE executor were removed. Callers now use the repository, journal, coordinator, approval service, conversation service, and transport directly.
2. **Hermes cancellation still depended on a compatibility active-run map.** The repository now provides a scoped `find_active` snapshot query and cancellation uses it without exposing mutable internals.
3. **Compatibility run metadata retained legacy event queues.** Codex, Claude Code, Hermes API, and Hermes Desktop run metadata no longer allocate or publish to per-run queues. The final whole-suite review found and removed the last Desktop `queue.Queue()` entry.
4. **Pending approval/request maps had no explicit capacity fence.** Both app-server boundaries now reject at a fixed limit; tests prove no native send occurs after capacity is reached.
5. **The generated caller/writer inventory was stale after final cleanup.** All five artifacts were regenerated and reproduce byte-for-byte under `--check`.
6. **A cron regression test could not run independently because it imported the server with the production `/data` default.** The test now establishes an isolated temporary `VO_STATUS_DIR` before import; product behavior is unchanged.
7. **A merged-change static assertion still required a removed completion helper.** It now asserts the actual coordinator ownership and absence of a legacy Desktop event queue.

## Performance evidence

- Fixed run fixtures retained exactly 1/20/100 runs, launched exactly 1/20/100 adapters, and emitted exactly one terminal event per run. Coordinator start median/p95 at 100 runs were approximately 161/268 microseconds, with zero active handles after completion.
- Fixed event fixtures published and replayed exactly 10/1,000/4,000 events. Retention stopped at 4,000; the 4,000-event selection-lock upper bound was approximately 0.099 ms and publish median/p95 were approximately 16.5/21.4 microseconds.
- The baseline comparison passed every adapter-launch, terminal-count, registered-run, retention, replay-count, publish-p95, and run-p95 gate. No duplicate terminal, extra provider call, unbounded retention, or unrelated-scope serialization was observed.
- Approval load registered 1,000 records across 10 scopes, resolved 100 with exactly 100 provider calls, and retained 900 pending records; registration median/p95 were approximately 28.3/45.5 microseconds.
- Conversation load retained at most 500 messages per scope, performed exactly one adapter call for each of 100 queued OpenClaw deliveries, and created zero synthetic run records.
- Provider, Project Execution, Meeting, Feishu, history, approval, cancellation, and notification call compatibility is covered by the 21-command characterization manifest and the focused regression suites; notification failure remains isolated from provider completion.

## Regression evidence

- **77** isolated Python test/script files passed. Isolated execution avoids global environment/state contamination while covering Provider, Project Execution, Meeting, Feishu, approval, cancellation, conversation, persistence, WebSocket, concurrency, performance, and security paths.
- **23/23** JavaScript static checks and **12/12** pure JavaScript/DOM tests passed.
- Characterization manifest: **21/21 passed**.
- Generated inventory reproducibility, Python compilation, `git diff --check`, and strict OpenSpec validation passed.
- The live-only workflow tests, CDP UI/performance tests, and external credential paths are deliberately classified as release acceptance rather than silently skipped. Section 8 runs them only after starting the candidate through `start.sh`/`start.sh --browser`; unavailable external credentials use local/fake adapters and are recorded as manual-only gaps.

## Review conclusion

No blocking correctness, security, data-consistency, ownership, or performance finding remains in the Section 7 candidate. The remaining work is documentation plus start-script-only live acceptance and rollback rehearsal, not additional Provider authority cleanup.
