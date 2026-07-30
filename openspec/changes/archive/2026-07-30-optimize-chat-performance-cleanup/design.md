## Context

The active chat route path no longer uses the old in-memory `ProviderRunBridge`. `server_routes.agent_bridges` imports `server_services.agent_bridges`, calls `_hydrate()`, and then invokes handlers that are identical to the authoritative `server.py` handlers. Runtime identity checks show the hydrated Codex, Hermes, and Claude Code run-start and run-events handlers resolve to `server.py` functions, while `server.py` itself does not define `ProviderRunBridge` or `PROVIDER_RUN_BRIDGE`.

Despite that, `server_services/agent_bridges.py` still contains a copied legacy bridge implementation and old run/idempotency maps. Some static module-split tests even require `class ProviderRunBridge` as a marker. This creates a stale architecture signal: the current system says the repository/journal/coordinator/SSE transport are the only Provider run authorities, but one split module still exposes obsolete names.

The active Codex fast path already removed the dominant latency sources: per-event activity JSON rewrites, communication progress rewrites, and fixed terminal sleeps. Remaining event costs are smaller and are concentrated around duplicate payload sanitation/copying, generic journal publication, and high-frequency telemetry updates.

## Goals / Non-Goals

**Goals:**

- Remove bridge code that is proven unreachable from normal routed chat/run APIs.
- Make static tests enforce the current Provider run authorities rather than stale compatibility markers.
- Keep route hydration explicit and covered so future refactors cannot accidentally call stale service-local handlers.
- Reduce duplicate per-event work in the active Codex fast path with measurable fixture evidence.
- Preserve all durable chat, approval, terminal, history, cancellation, thread mapping, and SSE replay behavior.

**Non-Goals:**

- Remove all legacy compatibility behavior across the repository.
- Rewrite `server_services/agent_bridges.py` into fully independent service ownership in this change.
- Change the public chat UI, public HTTP route shapes, or Provider event names.
- Persist every transient reasoning/delta fragment after restart.
- Optimize model inference, cold startup, real credentials, or external network latency.

## Decisions

### 1. Treat proof-of-unused as a deletion gate

Before deleting bridge remnants, add or update tests that prove the normal route path hydrates to the authoritative handlers:

- Codex `/api/codex/runs` and `/api/codex/runs/{id}/events`;
- Hermes `/api/hermes/runs` and `/api/hermes/runs/{id}/events`;
- Claude Code `/api/claude-code/runs` and `/api/claude-code/runs/{id}/events`.

The proof must check function identity or an equivalent explicit delegation boundary, not just string markers. Once this is covered, old service-local run-start/run-events implementations can be removed or converted to thin delegations.

### 2. Remove obsolete run authority names from the split module

`server_services/agent_bridges.py` should no longer export or define:

- `ProviderRunBridge`;
- `PROVIDER_RUN_BRIDGE`;
- `CLAUDE_CODE_STREAM_RUNS` and its lock alias;
- `_CODEX_RUN_IDEMPOTENCY` and `_PROVIDER_RUN_IDEMPOTENCY` maps;
- helper functions that only wrap the obsolete bridge.

Any test currently requiring those symbols as module-split markers must be changed to require current architecture markers, such as hydrated handler delegation, `ProviderRunCoordinator`, `ProviderEventJournal`, `PROVIDER_SSE_TRANSPORT.stream_run`, or the absence of obsolete authorities.

### 3. Keep compatibility routes but not compatibility authorities

Public routes and request/response bodies remain compatible. The change removes stale internal authorities, not user-facing endpoints. If a compatibility function name remains necessary for a route or existing test, it should delegate to the authoritative implementation rather than maintaining independent state.

Direct import users of `server_services.agent_bridges` outside the routed server path are not treated as an authoritative runtime. If a test or script depends on a service-local implementation, it should be migrated to the routed/hydrated path or to the current provider services.

### 4. Add an internal trusted-event path cautiously

The current Codex event flow may sanitize/copy the same event in both `CodexEventFastPath.process_event` and `ProviderEventJournal.publish`. Introduce a narrow internal DTO or journal method for already-bounded Provider payloads. The default public `publish` method keeps sanitization as defense in depth.

The trusted path must be private to the server-side fast path, must not accept HTTP payloads directly, and must preserve bounded payload shape, event names, sequence assignment, terminal dedupe, indexes, and replay results.

### 5. Preserve durable/key event ordering over raw speed

Transient reasoning, deltas, tool progress, and replaceable live activity may use reduced-copy/coalesced handling. Durable/key events still require strong ordering:

- accepted user message;
- approval request/resolution;
- final assistant reply;
- cancellation/failure/completion terminal;
- thread/conversation mapping;
- durable replay surface.

If an optimization makes this boundary ambiguous, keep the slower current path for that event class.

### 6. Treat telemetry as sampled or stage-based in high-frequency paths

High-frequency transient events do not need to acquire telemetry locks on every fragment. Record first native event, first displayable fragment, journal publication, terminal, and forced/bypass counters exactly. Consider sampling or class-level counters for later transient fragments. Diagnostics remain content-free and bounded.

### 7. Measure before and after using the existing deterministic fixtures

Use the existing Codex fast-path performance harness as the primary comparison, with the same warmups, measured turns, fake local app-server, existing thread, and event volume. Report p50/p95/max and operation counts. The expected gain is incremental; the acceptance criterion is no regression plus measurable reduction in per-event overhead or callback duration.

## Risks / Trade-offs

- **[A direct import path still uses service-local handlers]** → Add route-hydration identity tests, search direct imports, and either migrate callers or retain only thin delegations.
- **[Static tests still encode stale architecture]** → Update them in the same change so they fail on obsolete authorities and pass on current boundaries.
- **[Trusted payload path weakens redaction]** → Restrict it to payloads produced by the Codex fast-path sanitizer, add canary tests, and keep public journal sanitization unchanged.
- **[Small performance changes are lost in noise]** → Use deterministic fixtures, operation counts, and callback duration distributions rather than relying on one wall-clock sample.
- **[Cleanup touches broad legacy file]** → Keep edits scoped to bridge authority removal and test markers; do not opportunistically refactor unrelated chat/provider helpers.

## Migration Plan

1. Add route hydration and obsolete-authority characterization tests.
2. Remove stale bridge symbols and copied run authority code from `server_services/agent_bridges.py`, or replace required exported names with thin delegations that do not own state.
3. Update module-split/static tests to enforce the new boundary and absence of obsolete bridge authorities.
4. Introduce a private already-sanitized event publication path with focused redaction, replay, terminal dedupe, and SSE tests.
5. Adjust telemetry for high-frequency transient fragments if tests and measurements show a clear benefit.
6. Run focused Provider/Codex bridge suites and deterministic performance comparison.
7. Record evidence, caveats, and any deferred cleanup candidates.
