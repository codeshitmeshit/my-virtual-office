## 1. Proof and Characterization

- [x] 1.1 Add a focused route-hydration test proving `server_routes.agent_bridges` resolves Codex, Hermes, and Claude Code run-start/run-events handlers to the authoritative `server.py` implementations before serving normal routes.
- [x] 1.2 Add or update static checks so obsolete Provider run authorities are forbidden in `server.py` and `server_services/agent_bridges.py`, including `ProviderRunBridge`, `PROVIDER_RUN_BRIDGE`, `CLAUDE_CODE_STREAM_RUNS`, `_CODEX_RUN_IDEMPOTENCY`, and `_PROVIDER_RUN_IDEMPOTENCY`.
- [x] 1.3 Search and document any direct import callers of `server_services.agent_bridges`; migrate test expectations to the hydrated route path or current Provider services.

## 2. Legacy Bridge Cleanup

- [x] 2.1 Remove obsolete bridge exports, aliases, maps, helper wrappers, and copied in-memory run authority implementations from `server_services/agent_bridges.py`.
- [x] 2.2 Replace stale module-split test markers that require `class ProviderRunBridge` with markers for current boundaries: hydrated delegation, `ProviderRunCoordinator`, `ProviderEventJournal`, and `PROVIDER_SSE_TRANSPORT.stream_run`.
- [x] 2.3 Verify Codex, Hermes, and Claude Code run start/events/stop/cancel behavior still goes through the current coordinator, journal, approval service, and SSE transport without resurrecting local queues.

## 3. Hot-Path Performance Refinement

- [x] 3.1 Add a baseline comparison run for the current deterministic Codex chat performance harness and capture per-event callback duration, journal publish latency, sanitize/copy counts where practical, and p50/p95/max timing.
- [x] 3.2 Introduce a private internal event-publication path for already-sanitized Codex fast-path payloads while keeping the public journal publish API fully sanitizing.
- [x] 3.3 Add redaction, payload-bound, terminal-dedupe, run index, conversation index, SSE replay, and reconnect tests for the internal publication path.
- [x] 3.4 Reduce telemetry locking for high-frequency transient fragments when it can be done without losing required first-event, first-fragment, terminal, busy, bypass, and forced-flush counters.

## 4. Regression and Evidence

- [x] 4.1 Run focused Python tests for Provider events, Provider runs, Provider SSE transport, Provider service boundaries, Codex fast path, Codex bridge, Codex runs SSE, and route split behavior.
- [x] 4.2 Run focused JavaScript/static checks for Codex runs bridge, Claude Code runs SSE, Provider chat SSE, and server/frontend module split.
- [x] 4.3 Re-run the deterministic Codex chat fast-path performance harness with the same fixture identity and publish before/after evidence.
- [x] 4.4 Run strict OpenSpec validation for `optimize-chat-performance-cleanup` and record the command/result with the focused test evidence.
- [x] 4.5 Record any unverified real-Provider, browser-CDP, or environment-gated checks without claiming they passed.
